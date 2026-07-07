import json
import re
import time
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock

import requests
from urllib.parse import urlencode

from config import Config
from empresas_store import contabilidad_base_url, endpoint_path

from as400_api_cuentas import normalizar_registro_cuenta
from cuenta_tipos import enriquecer_cuenta

# crear_asiento est? en el mismo SRVPGM/WS que pedidos (swagger PEDIDOS)
CONTABILIDAD_OPERACIONES = frozenset({"cuentas"})
_STATUS_LOCK = Lock()
_AS400_STATUS = {
    "servicios": {},
    "operaciones": {},
    "errores_recientes": deque(maxlen=25),
}


def _ahora_iso():
    return datetime.now(timezone.utc).isoformat()


def _servicio_operacion(operacion):
    return "contabilidad" if operacion in CONTABILIDAD_OPERACIONES else "pedidos"


def _estado_inicial(nombre):
    return {
        "nombre": nombre,
        "estado": "sin_datos",
        "ultima_ok": "",
        "ultimo_error": "",
        "ultimo_error_fecha": "",
        "ultima_respuesta_ms": None,
        "total_ok": 0,
        "total_error": 0,
        "empresa_id": "",
        "empresa_nombre": "",
        "operacion": "",
    }


def _registrar_estado_as400(empresa, operacion, ok, respuesta_ms, error=""):
    ahora = _ahora_iso()
    servicio = _servicio_operacion(operacion)
    empresa_id = str((empresa or {}).get("id") or "default")
    empresa_nombre = str((empresa or {}).get("nombre") or empresa_id)

    with _STATUS_LOCK:
        for clave, nombre in (
            (servicio, servicio),
            (operacion, operacion),
        ):
            store = (
                _AS400_STATUS["servicios"]
                if clave == servicio
                else _AS400_STATUS["operaciones"]
            )
            estado = store.setdefault(clave, _estado_inicial(nombre))
            estado["estado"] = "ok" if ok else "error"
            estado["ultima_respuesta_ms"] = respuesta_ms
            estado["empresa_id"] = empresa_id
            estado["empresa_nombre"] = empresa_nombre
            estado["operacion"] = operacion

            if ok:
                estado["ultima_ok"] = ahora
                estado["total_ok"] += 1
            else:
                estado["ultimo_error"] = error
                estado["ultimo_error_fecha"] = ahora
                estado["total_error"] += 1

        if not ok:
            _AS400_STATUS["errores_recientes"].appendleft({
                "fecha": ahora,
                "servicio": servicio,
                "operacion": operacion,
                "empresa_id": empresa_id,
                "empresa_nombre": empresa_nombre,
                "respuesta_ms": respuesta_ms,
                "error": str(error or "")[:500],
            })


def get_as400_status():
    with _STATUS_LOCK:
        return {
            "servicios": deepcopy(_AS400_STATUS["servicios"]),
            "operaciones": deepcopy(_AS400_STATUS["operaciones"]),
            "errores_recientes": list(_AS400_STATUS["errores_recientes"]),
        }


class AS400ApiError(Exception):
    pass


def _success_ok(value):
    if value is None:
        return False

    if value is True or value is False:
        return value is True

    texto = str(value).strip().lower()
    return texto in {"1", "true", "y", "yes", "s", "si", "s?"}


def _normalizar_fecha_as400(fecha):
    if fecha is None:
        return ""

    texto = str(fecha).strip()

    if not texto or texto in ("0", "00000000"):
        return ""

    return texto


def _primer_valor_articulo(articulo, *claves, default=None):
    for clave in claves:
        valor = articulo.get(clave)

        if valor is not None and str(valor).strip() != "":
            return valor

    return default


def _entero_respuesta_articulos(data, salida, articulos):
    for valor in (
        salida.get("numArticulos"),
        salida.get("lineas_salida"),
        data.get("numArticulos"),
        data.get("lineas_salida"),
    ):
        try:
            return int(valor)
        except (TypeError, ValueError):
            continue

    return len(articulos)


def _normalizar_articulo(articulo):
    articulo = dict(articulo)

    if articulo.get("precio") is None:
        articulo["precio"] = 0

    stock_otros = _primer_valor_articulo(
        articulo,
        "stockOtros",
        "stock_otros",
        "stockotros",
        default=0,
    )
    consumo_diario = _primer_valor_articulo(
        articulo,
        "Consumo_Diario",
        "consumo_diario",
        "consumoDiario",
        default=0,
    )

    articulo["stockOtros"] = stock_otros
    articulo["Consumo_Diario"] = consumo_diario
    articulo["consumo_diario"] = consumo_diario

    for campo in ("stock", "reservado", "pendiente"):
        if articulo.get(campo) is None:
            articulo[campo] = 0

    articulo["fecha_ultimo"] = _normalizar_fecha_as400(
        _primer_valor_articulo(
            articulo,
            "fecha_ultimo",
            "fechaUltimo",
        )
    )
    articulo["fecha_ultimo_consumo"] = _normalizar_fecha_as400(
        _primer_valor_articulo(
            articulo,
            "fecha_ultimo_consumo",
            "fechaUltimoConsumo",
        )
    )

    return articulo


def _get_auth(empresa):
    usuario = empresa.get("api_user") or Config.AS400_API_USER
    password = empresa.get("api_password") or Config.AS400_API_PASSWORD

    if usuario and password:
        return (usuario, password)

    return None


def _resolve_base_url(empresa, operacion):
    if operacion in CONTABILIDAD_OPERACIONES:
        return contabilidad_base_url(empresa)

    return str(empresa.get("base_url", "")).strip().rstrip("/") or None


def _build_url(empresa, endpoint, params=None, operacion=None):
    base_url = _resolve_base_url(empresa, operacion)

    if not base_url:
        raise AS400ApiError("No hay URL base configurada para la petici?n")

    url = f"{base_url}/{endpoint.lstrip('/')}"

    if params:
        query = urlencode(params)
        separador = "&" if "?" in url else "?"
        url = f"{url}{separador}{query}"

    return url


def _parse_json_response(response):
    try:
        return response.json()
    except ValueError:
        texto = response.text.replace("\x1e", "").replace("\x1d", "")
        texto = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", texto)

        try:
            return json.loads(texto)
        except ValueError:
            raise AS400ApiError(
                f"El AS/400 no devolvi? JSON v?lido: {response.text[:500]}"
            )


def _request(empresa, method, operacion, params=None, **kwargs):
    if not empresa:
        raise AS400ApiError("No hay empresa configurada para la petici?n")

    if not _resolve_base_url(empresa, operacion):
        raise AS400ApiError("No hay empresa configurada para la petici?n")

    endpoint = endpoint_path(empresa, operacion)
    url = _build_url(empresa, endpoint, params, operacion=operacion)
    inicio = time.perf_counter()

    def respuesta_ms():
        return int(round((time.perf_counter() - inicio) * 1000))

    try:
        response = requests.request(
            method=method,
            url=url,
            auth=_get_auth(empresa),
            timeout=60,
            **kwargs
        )

    except requests.RequestException as e:
        mensaje = f"No se pudo conectar con el AS/400: {e}"
        _registrar_estado_as400(empresa, operacion, False, respuesta_ms(), mensaje)
        raise AS400ApiError(mensaje)

    if response.status_code >= 400:
        mensaje = response.text.strip() or f"Error HTTP {response.status_code}"
        try:
            error_json = response.json()
        except ValueError:
            error_json = None

        if isinstance(error_json, dict):
            salida_error = error_json.get("salida")
            if isinstance(salida_error, dict) and salida_error.get("mensaje"):
                mensaje = str(salida_error["mensaje"]).strip()
            elif error_json.get("mensaje"):
                mensaje = str(error_json["mensaje"]).strip()

        _registrar_estado_as400(empresa, operacion, False, respuesta_ms(), mensaje)
        raise AS400ApiError(mensaje)

    try:
        data = _parse_json_response(response)
    except AS400ApiError as error:
        _registrar_estado_as400(empresa, operacion, False, respuesta_ms(), str(error))
        raise
    except ValueError:
        mensaje = f"El AS/400 no devolvi? JSON v?lido: {response.text[:500]}"
        _registrar_estado_as400(empresa, operacion, False, respuesta_ms(), mensaje)
        raise AS400ApiError(mensaje)

    if data.get("success") is False:
        mensaje = data.get("mensaje", "Error devuelto por AS/400")
        _registrar_estado_as400(empresa, operacion, False, respuesta_ms(), mensaje)
        raise AS400ApiError(mensaje)

    _registrar_estado_as400(empresa, operacion, True, respuesta_ms())
    return data


def _fecha_analisis_por_defecto():
    import calendar
    from datetime import date

    hoy = date.today()
    ano = hoy.year
    mes = hoy.month - 3

    if mes <= 0:
        mes += 12
        ano -= 1

    dia = min(hoy.day, calendar.monthrange(ano, mes)[1])
    return date(ano, mes, dia).strftime("%Y%m%d")


def normalizar_fecha_analisis(fecha):
    texto = str(fecha or "").strip().replace("-", "")

    if not texto:
        return _fecha_analisis_por_defecto()

    if len(texto) != 8 or not texto.isdigit():
        raise AS400ApiError("La fecha de an?lisis no es v?lida")

    return texto


def obtener_articulos(empresa, proveedor_codigo, fechaAnalisis=None):
    """
    GET /articulos?proveedor={codigo}&fechaAnalisis={aaaammdd}
    """
    proveedor = str(proveedor_codigo).strip()

    if not proveedor:
        raise AS400ApiError("Falta el c?digo de proveedor")

    data = _request(
        empresa,
        "GET",
        "articulos",
        params={
            "proveedor": proveedor,
            "fechaAnalisis": normalizar_fecha_analisis(fechaAnalisis),
        },
    )
    salida = data.get("salida", data)
    articulos = salida.get("articulos", [])
    num_articulos = _entero_respuesta_articulos(data, salida, articulos)

    num_articulos = min(num_articulos, len(articulos))
    normalizados = []

    for articulo in articulos[:num_articulos]:
        normalizado = _normalizar_articulo(articulo)

        if not str(normalizado.get("codigo") or "").strip():
            continue

        normalizados.append(normalizado)

    return normalizados


def _normalizar_almacen(almacen):
    return {
        "codigoAlmacen": almacen.get("codigoAlmacen"),
        "nombreAlmacen": str(almacen.get("nombreAlmacen", "")).strip(),
        "stock1": almacen.get("stock1", 0),
        "abr1": str(almacen.get("abr1", "")).strip(),
        "stock2": almacen.get("stock2", 0),
        "abr2": str(almacen.get("abr2", "")).strip(),
        "factor": almacen.get("factor", 0),
        "stock3": almacen.get("stock3", 0),
        "abr3": str(almacen.get("abr3", "")).strip(),
        "factor1": almacen.get("factor1", 0),
    }


def obtener_stocks(empresa, codigo_articulo):
    """
    GET /stocks?codigoArticulo={codigo}
    """
    codigo = str(codigo_articulo or "").strip()

    if not codigo:
        raise AS400ApiError("Falta el c?digo de art?culo")

    data = _request(
        empresa,
        "GET",
        "stocks",
        params={"codigoArticulo": codigo},
    )
    salida = data.get("salida", data)

    if not _success_ok(salida.get("success")):
        raise AS400ApiError(salida.get("mensaje", "Error obteniendo stocks"))

    almacenes = salida.get("almacenes", [])

    try:
        num_almacenes = int(salida.get("numAlmacenes", len(almacenes)))
    except (TypeError, ValueError):
        num_almacenes = len(almacenes)

    num_almacenes = min(num_almacenes, len(almacenes))
    validos = []

    for almacen in almacenes[:num_almacenes]:
        registro = _normalizar_almacen(almacen)

        if int(registro.get("codigoAlmacen") or 0) <= 0:
            continue

        if not registro.get("nombreAlmacen"):
            continue

        validos.append(registro)

    return validos


def obtener_articulo_por_codigo(empresa, codigo, proveedor_codigo):
    for articulo in obtener_articulos(empresa, proveedor_codigo):
        if articulo["codigo"] == codigo:
            return articulo

    return None


def obtener_proveedores(empresa):
    data = _request(empresa, "GET", "proveedores")

    salida = data.get("salida", data)

    if not _success_ok(salida.get("success")):
        raise AS400ApiError("Error obteniendo proveedores")

    proveedores = salida.get("proveedores", [])

    try:
        num_proveedores = int(salida.get("numProveedores", len(proveedores)))
    except (TypeError, ValueError):
        num_proveedores = len(proveedores)

    num_proveedores = min(num_proveedores, len(proveedores))

    return proveedores[:num_proveedores]


def _normalizar_cuenta(cuenta):
    return normalizar_registro_cuenta(cuenta)


def _extraer_lista_cuentas(data):
    salida = data.get("salida")

    if isinstance(salida, dict) and salida.get("cuentas") is not None:
        return salida.get("cuentas", [])

    if data.get("IAERP_Get_cuentas_R") is not None:
        return data.get("IAERP_Get_cuentas_R", [])

    for valor in data.values():
        if isinstance(valor, list):
            return valor

    return []


def obtener_cuentas(empresa):
    data = _request(empresa, "GET", "cuentas")

    salida = data.get("salida")

    if isinstance(salida, dict) and salida.get("cuentas") is None:
        if not _success_ok(salida.get("success")):
            raise AS400ApiError("Error obteniendo cuentas contables")

    cuentas = _extraer_lista_cuentas(data)

    if isinstance(salida, dict) and salida.get("cuentas") is not None:
        try:
            num_cuentas = int(salida.get("numCuentas", len(cuentas)))
        except (TypeError, ValueError):
            num_cuentas = len(cuentas)

        cuentas = cuentas[:num_cuentas]

    validas = []

    for cuenta in cuentas:
        normalizada = _normalizar_cuenta(cuenta)

        if normalizada["codigo"]:
            validas.append(enriquecer_cuenta(normalizada))

    return validas


def crear_pedido(empresa, proveedor_codigo, usuario, carrito):
    lineas = [
        {
            "codigo_articulo": str(item["codigo"]).strip(),
            "cantidad": float(item["cantidad"]),
            "codigoUm": int(item["codigoUm"])
        }
        for item in carrito
    ]

    payload = {
        "cliente": int(proveedor_codigo),
        "usuario": usuario,
        "numLineasIn": len(lineas),
        "lineas": lineas
    }

    data = _request(empresa, "POST", "crear_pedido", json=payload)

    salida = data.get("salida", data)

    if salida.get("success") not in (True, "1", 1, "true", "True"):
        raise AS400ApiError(
            salida.get("mensaje", "Error creando pedido")
        )

    return {
        "success": True,
        "numero_pedido": salida.get("numero_pedido"),
        "mensaje": salida.get("mensaje", "Pedido creado correctamente")
    }


def normalizar_fecha_asiento(fecha):
    texto = str(fecha or "").strip().replace("-", "")

    if not texto:
        raise AS400ApiError("Falta la fecha del asiento")

    if len(texto) != 8 or not texto.isdigit():
        raise AS400ApiError("La fecha del asiento no es v?lida")

    return texto


def normalizar_debe_haber(valor):
    texto = str(valor or "").strip().upper()

    if texto in ("D", "DEBE"):
        return "D"

    if texto in ("H", "HABER"):
        return "H"

    raise AS400ApiError("Debe/Haber debe ser D o H")


def crear_asiento_contable(empresa, usuario, lineas):
    lineas_payload = []

    for linea in lineas:
        lineas_payload.append({
            "cuenta": str(linea["cuenta"]).strip(),
            "fecha": normalizar_fecha_asiento(linea["fecha"]),
            "importe": float(linea["importe"]),
            "debe_haber": normalizar_debe_haber(linea["debe_haber"]),
            "concepto": str(linea["concepto"]).strip(),
        })

    payload = {
        "usuario": str(usuario or "").strip()[:20],
        "numLineasIn": len(lineas_payload),
        "lineas": lineas_payload,
    }

    data = _request(empresa, "POST", "crear_asiento", json=payload)

    salida = data.get("salida", data)

    if not _success_ok(salida.get("success")):
        raise AS400ApiError(
            salida.get("mensaje", "Error creando asiento contable")
        )

    return {
        "success": True,
        "numero_asiento": salida.get("numero_asiento"),
        "mensaje": salida.get("mensaje", "Asiento creado correctamente"),
    }
