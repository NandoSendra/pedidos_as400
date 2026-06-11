import requests
from urllib.parse import urlencode

from config import Config
from empresas_store import endpoint_path


class AS400ApiError(Exception):
    pass


def _success_ok(value):
    return value in (True, "1", 1, "true", "True")


def _normalizar_fecha_as400(fecha):
    if fecha is None:
        return ""

    texto = str(fecha).strip()

    if not texto or texto in ("0", "00000000"):
        return ""

    return texto


def _normalizar_articulo(articulo):
    articulo = dict(articulo)

    if articulo.get("precio") is None:
        articulo["precio"] = 0

    for campo in ("stockOtros", "reservado", "pendiente"):
        if articulo.get(campo) is None:
            articulo[campo] = 0

    articulo["fecha_ultimo"] = _normalizar_fecha_as400(
        articulo.get("fecha_ultimo")
    )
    articulo["fecha_ultimo_consumo"] = _normalizar_fecha_as400(
        articulo.get("fecha_ultimo_consumo")
    )

    return articulo


def _get_auth(empresa):
    usuario = empresa.get("api_user") or Config.AS400_API_USER
    password = empresa.get("api_password") or Config.AS400_API_PASSWORD

    if usuario and password:
        return (usuario, password)

    return None


def _build_url(empresa, endpoint, params=None):
    base_url = str(empresa.get("base_url", "")).rstrip("/")
    url = f"{base_url}/{endpoint.lstrip('/')}"

    if params:
        query = urlencode(params)
        separador = "&" if "?" in url else "?"
        url = f"{url}{separador}{query}"

    return url


def _request(empresa, method, operacion, params=None, **kwargs):
    if not empresa or not empresa.get("base_url"):
        raise AS400ApiError("No hay empresa configurada para la petición")

    endpoint = endpoint_path(empresa, operacion)
    url = _build_url(empresa, endpoint, params)

    try:
        response = requests.request(
            method=method,
            url=url,
            auth=_get_auth(empresa),
            timeout=20,
            **kwargs
        )

    except requests.RequestException as e:
        raise AS400ApiError(f"No se pudo conectar con el AS/400: {e}")

    if response.status_code >= 400:
        mensaje = response.text.strip() or f"Error HTTP {response.status_code}"
        raise AS400ApiError(mensaje)

    try:
        data = response.json()
    except ValueError:
        raise AS400ApiError(
            f"El AS/400 no devolvió JSON válido: {response.text}"
        )

    if data.get("success") is False:
        raise AS400ApiError(data.get("mensaje", "Error devuelto por AS/400"))

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
        raise AS400ApiError("La fecha de análisis no es válida")

    return texto


def obtener_articulos(empresa, proveedor_codigo, fechaAnalisis=None):
    """
    GET /articulos?proveedor={codigo}&fechaAnalisis={aaaammdd}
    """
    proveedor = str(proveedor_codigo).strip()

    if not proveedor:
        raise AS400ApiError("Falta el código de proveedor")

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
    try:
        num_articulos = int(salida.get("numArticulos", len(articulos)))
    except (TypeError, ValueError):
        num_articulos = len(articulos)

    num_articulos = min(num_articulos, len(articulos))

    return [_normalizar_articulo(articulo) for articulo in articulos[:num_articulos]]


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
        raise AS400ApiError("Falta el código de artículo")

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
