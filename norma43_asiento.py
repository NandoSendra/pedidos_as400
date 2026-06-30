import re
from datetime import date

from csv_asiento import CSVAsientoError, decodificar_csv


LONGITUD_REGISTRO = 80

TIPOS_REGISTRO_NORMA43 = frozenset({"11", "22", "23", "24", "33", "88"})

CONCEPTOS_COMUNES = {
    "01": "Talones reintegro",
    "02": "Abonarés entrega ingresos",
    "03": "Talones ingreso",
    "04": "Giros transferencias",
    "05": "Giros recibidos",
    "06": "Giros traspasados",
    "07": "Giros recibidos oficina",
    "08": "Ampliación giros",
    "09": "Intereses",
    "10": "Devolución recibos",
    "11": "Recibos domiciliados",
    "12": "Pagos por cuenta",
    "13": "Pagos cheques",
    "14": "Devoluciones cheques",
    "15": "Suscripción dividendos",
    "16": "Liquidación intereses",
    "17": "Líneas descuento",
    "18": "Liquidación comisiones",
    "19": "Correcciones",
    "20": "Correcciones comisiones",
    "21": "Devolución impagados",
    "22": "Devolución recibos",
    "23": "Devolución domiciliados",
    "24": "Confirming",
    "25": "Domiciliados recibidos",
    "26": "Domiciliados devueltos",
    "27": "Cobro recibos",
    "28": "Cobro recibos devueltos",
    "29": "Cobro recibos domiciliados",
    "30": "Cobro recibos domiciliados devueltos",
    "31": "Cobro recibos domiciliados impagados",
    "32": "Cobro recibos domiciliados impagados devueltos",
    "33": "Cobro recibos domiciliados impagados devueltos",
    "34": "Cobro recibos domiciliados impagados devueltos",
    "35": "Cobro recibos domiciliados impagados devueltos",
    "36": "Cobro recibos domiciliados impagados devueltos",
    "37": "Cobro recibos domiciliados impagados devueltos",
    "38": "Cobro recibos domiciliados impagados devueltos",
    "39": "Cobro recibos domiciliados impagados devueltos",
    "40": "Cobro recibos domiciliados impagados devueltos",
    "41": "Cobro recibos domiciliados impagados devueltos",
    "42": "Cobro recibos domiciliados impagados devueltos",
    "43": "Cobro recibos domiciliados impagados devueltos",
    "44": "Cobro recibos domiciliados impagados devueltos",
    "45": "Cobro recibos domiciliados impagados devueltos",
    "46": "Cobro recibos domiciliados impagados devueltos",
    "47": "Cobro recibos domiciliados impagados devueltos",
    "48": "Cobro recibos domiciliados impagados devueltos",
    "49": "Cobro recibos domiciliados impagados devueltos",
    "50": "Cobro recibos domiciliados impagados devueltos",
    "51": "Cobro recibos domiciliados impagados devueltos",
    "52": "Cobro recibos domiciliados impagados devueltos",
    "53": "Cobro recibos domiciliados impagados devueltos",
    "54": "Cobro recibos domiciliados impagados devueltos",
    "55": "Cobro recibos domiciliados impagados devueltos",
    "56": "Cobro recibos domiciliados impagados devueltos",
    "57": "Cobro recibos domiciliados impagados devueltos",
    "58": "Cobro recibos domiciliados impagados devueltos",
    "59": "Cobro recibos domiciliados impagados devueltos",
    "60": "Cobro recibos domiciliados impagados devueltos",
    "61": "Cobro recibos domiciliados impagados devueltos",
    "62": "Cobro recibos domiciliados impagados devueltos",
    "63": "Cobro recibos domiciliados impagados devueltos",
    "64": "Cobro recibos domiciliados impagados devueltos",
    "65": "Cobro recibos domiciliados impagados devueltos",
    "66": "Cobro recibos domiciliados impagados devueltos",
    "67": "Cobro recibos domiciliados impagados devueltos",
    "68": "Cobro recibos domiciliados impagados devueltos",
    "69": "Cobro recibos domiciliados impagados devueltos",
    "70": "Cobro recibos domiciliados impagados devueltos",
    "71": "Cobro recibos domiciliados impagados devueltos",
    "72": "Cobro recibos domiciliados impagados devueltos",
    "73": "Cobro recibos domiciliados impagados devueltos",
    "74": "Cobro recibos domiciliados impagados devueltos",
    "75": "Cobro recibos domiciliados impagados devueltos",
    "76": "Cobro recibos domiciliados impagados devueltos",
    "77": "Cobro recibos domiciliados impagados devueltos",
    "78": "Cobro recibos domiciliados impagados devueltos",
    "79": "Cobro recibos domiciliados impagados devueltos",
    "80": "Cobro recibos domiciliados impagados devueltos",
    "81": "Cobro recibos domiciliados impagados devueltos",
    "82": "Cobro recibos domiciliados impagados devueltos",
    "83": "Cobro recibos domiciliados impagados devueltos",
    "84": "Cobro recibos domiciliados impagados devueltos",
    "85": "Cobro recibos domiciliados impagados devueltos",
    "86": "Cobro recibos domiciliados impagados devueltos",
    "87": "Cobro recibos domiciliados impagados devueltos",
    "88": "Cobro recibos domiciliados impagados devueltos",
    "89": "Cobro recibos domiciliados impagados devueltos",
    "90": "Cobro recibos domiciliados impagados devueltos",
    "91": "Cobro recibos domiciliados impagados devueltos",
    "92": "Cobro recibos domiciliados impagados devueltos",
    "93": "Cobro recibos domiciliados impagados devueltos",
    "94": "Cobro recibos domiciliados impagados devueltos",
    "95": "Cobro recibos domiciliados impagados devueltos",
    "96": "Cobro recibos domiciliados impagados devueltos",
    "97": "Cobro recibos domiciliados impagados devueltos",
    "98": "Cobro recibos domiciliados impagados devueltos",
    "99": "Otros conceptos",
}


def _normalizar_linea(linea):
    linea = linea.rstrip("\r\n")

    if len(linea) < LONGITUD_REGISTRO:
        linea = linea.ljust(LONGITUD_REGISTRO)

    return linea[:LONGITUD_REGISTRO]


def _extraer_registros(texto):
    texto = str(texto or "").replace("\r\n", "\n").replace("\r", "\n")
    lineas = [linea for linea in texto.split("\n") if linea.strip()]

    if (
        len(lineas) == 1
        and len(lineas[0]) > LONGITUD_REGISTRO
        and lineas[0][:2] in TIPOS_REGISTRO_NORMA43
    ):
        contenido = lineas[0]
        registros = []

        for indice in range(0, len(contenido), LONGITUD_REGISTRO):
            trozo = contenido[indice:indice + LONGITUD_REGISTRO]

            if trozo.strip():
                registros.append((_normalizar_linea(trozo), indice // LONGITUD_REGISTRO + 1))

        return registros

    registros = []

    for numero, linea in enumerate(lineas, start=1):
        registros.append((_normalizar_linea(linea), numero))

    return registros


def es_fichero_norma43(texto):
    registros = _extraer_registros(texto)

    if len(registros) < 2:
        return False

    tipos = [linea[:2] for linea, _ in registros[:30]]
    validos = sum(1 for tipo in tipos if tipo in TIPOS_REGISTRO_NORMA43)

    if validos < 2:
        return False

    return validos / len(tipos) >= 0.6


def _parsear_fecha_aammdd(texto):
    texto = str(texto or "").strip()

    if len(texto) != 6 or not texto.isdigit():
        return ""

    aa = int(texto[:2])
    mm = int(texto[2:4])
    dd = int(texto[4:6])
    anio = 2000 + aa if aa < 80 else 1900 + aa

    try:
        return date(anio, mm, dd).isoformat()
    except ValueError:
        return ""


def _parsear_importe_norma43(texto):
    texto = str(texto or "").strip()

    if not texto.isdigit():
        return None

    importe = round(int(texto) / 100, 2)

    if importe <= 0:
        return None

    return importe


def _etiqueta_concepto(codigo_comun, codigo_propio):
    comun = CONCEPTOS_COMUNES.get(codigo_comun, f"Concepto {codigo_comun}")

    if codigo_propio.strip():
        return f"{comun} ({codigo_propio.strip()})"

    return comun


def _parsear_registro_11(linea):
    return {
        "entidad": linea[2:6].strip(),
        "oficina": linea[6:10].strip(),
        "numero_cuenta": linea[10:20].strip(),
        "fecha_inicial": _parsear_fecha_aammdd(linea[20:26]),
        "fecha_final": _parsear_fecha_aammdd(linea[26:32]),
        "saldo_inicial_signo": linea[32:33].strip(),
        "saldo_inicial": _parsear_importe_norma43(linea[33:47]),
        "divisa": linea[47:50].strip(),
        "modalidad": linea[50:51].strip(),
        "nombre_cliente": linea[51:77].strip(),
    }


def _parsear_registro_22(linea):
    signo = linea[27:28].strip()
    importe = _parsear_importe_norma43(linea[28:42])

    if importe is None:
        return None

    tipo_movimiento = "cargo" if signo == "1" else "abono"

    return {
        "oficina_origen": linea[6:10].strip(),
        "fecha_operacion": _parsear_fecha_aammdd(linea[10:16]),
        "fecha_valor": _parsear_fecha_aammdd(linea[16:22]),
        "concepto_comun": linea[22:24].strip(),
        "concepto_propio": linea[24:27].strip(),
        "tipo_movimiento": tipo_movimiento,
        "importe": importe,
        "numero_documento": linea[42:52].strip(),
        "referencia1": linea[52:64].strip(),
        "referencia2": linea[64:80].strip(),
        "concepto": _etiqueta_concepto(linea[22:24], linea[24:27]),
        "complementos": [],
    }


def _parsear_registro_23(linea):
    return [
        linea[4:42].strip(),
        linea[42:80].strip(),
    ]


def _descripcion_movimiento(movimiento):
    partes = [movimiento.get("concepto", "")]

    for complemento in movimiento.get("complementos", []):
        if complemento:
            partes.append(complemento)

    if movimiento.get("referencia2"):
        partes.append(movimiento["referencia2"])

    referencia1 = str(movimiento.get("referencia1", "")).strip()

    if referencia1 and referencia1.strip("0"):
        partes.append(referencia1)

    return " | ".join(parte for parte in partes if parte)


def _parsear_cuentas_norma43(registros):
    cuentas = []
    cuenta_actual = None
    movimiento_actual = None

    for linea, numero_linea in registros:
        tipo = linea[:2]

        if tipo == "11":
            cuenta_actual = _parsear_registro_11(linea)
            cuenta_actual["movimientos"] = []
            cuentas.append(cuenta_actual)
            movimiento_actual = None
            continue

        if cuenta_actual is None:
            if tipo in {"22", "23", "24", "33"}:
                raise CSVAsientoError(
                    f"Línea {numero_linea}: movimiento sin cabecera de cuenta (registro 11)"
                )
            continue

        if tipo == "22":
            movimiento = _parsear_registro_22(linea)

            if movimiento is None:
                continue

            cuenta_actual["movimientos"].append(movimiento)
            movimiento_actual = movimiento
            continue

        if tipo == "23" and movimiento_actual is not None:
            for complemento in _parsear_registro_23(linea):
                if complemento:
                    movimiento_actual["complementos"].append(complemento)
            continue

        if tipo == "33":
            cuenta_actual = None
            movimiento_actual = None

    movimientos = []

    for cuenta in cuentas:
        for movimiento in cuenta.get("movimientos", []):
            movimiento["descripcion"] = _descripcion_movimiento(movimiento)
            movimiento["cuenta_bancaria"] = {
                "entidad": cuenta.get("entidad", ""),
                "oficina": cuenta.get("oficina", ""),
                "numero_cuenta": cuenta.get("numero_cuenta", ""),
                "nombre_cliente": cuenta.get("nombre_cliente", ""),
            }
            movimientos.append(movimiento)

    if not movimientos:
        raise CSVAsientoError("El fichero Norma 43 no contiene movimientos (registros 22)")

    return cuentas, movimientos


def buscar_cuenta_contable_banco(cuentas, cabecera, cuenta_banco=None):
    cuenta_banco = str(cuenta_banco or "").strip()

    if cuenta_banco:
        return cuenta_banco

    entidad = str(cabecera.get("entidad", "")).strip()
    oficina = str(cabecera.get("oficina", "")).strip()
    numero = str(cabecera.get("numero_cuenta", "")).strip()
    patrones = [
        f"{entidad}{oficina}{numero}",
        f"{entidad}{oficina}",
        numero,
        numero.lstrip("0"),
    ]
    candidatas = [
        cuenta
        for cuenta in cuentas or []
        if str(cuenta.get("codigo", "")).startswith("572")
    ]

    for cuenta in candidatas:
        codigo = str(cuenta.get("codigo", ""))
        nombre = str(cuenta.get("nombre", "")).upper()

        for patron in patrones:
            if not patron:
                continue

            if patron in codigo or patron in nombre:
                return codigo

    if len(candidatas) == 1:
        return str(candidatas[0].get("codigo", "")).strip()

    return None


def sugerir_cuentas_contables_banco(cuentas, cabecera, limite=5):
    entidad = str(cabecera.get("entidad", "")).strip()
    oficina = str(cabecera.get("oficina", "")).strip()
    numero = str(cabecera.get("numero_cuenta", "")).strip()
    nombre_cliente = str(cabecera.get("nombre_cliente", "")).strip().upper()
    patrones = [
        f"{entidad}{oficina}{numero}",
        f"{entidad}{oficina}",
        numero,
        numero.lstrip("0"),
        entidad,
        nombre_cliente,
    ]
    candidatas = []

    for cuenta in cuentas or []:
        codigo = str(cuenta.get("codigo", "")).strip()

        if not codigo.startswith("572"):
            continue

        nombre = str(cuenta.get("nombre", "")).strip()
        texto = f"{codigo} {nombre}".upper()
        puntuacion = 1

        for patron in patrones:
            patron = str(patron or "").strip().upper()

            if not patron:
                continue

            if patron in texto:
                puntuacion += 10 if len(patron) >= 8 else 4

        candidatas.append({
            "codigo": codigo,
            "nombre": nombre,
            "puntuacion": puntuacion,
        })

    candidatas.sort(key=lambda item: (-item["puntuacion"], item["codigo"]))

    return candidatas[:limite]


def _debe_haber_contable_banco(tipo_movimiento):
    # Cargo bancario (sale dinero) -> Haber en cuenta 572
    # Abono bancario (entra dinero) -> Debe en cuenta 572
    return "H" if tipo_movimiento == "cargo" else "D"


def movimientos_a_lineas_banco(movimientos, cuenta_banco):
    lineas = []

    for movimiento in movimientos:
        if not cuenta_banco:
            continue

        lineas.append({
            "cuenta": cuenta_banco,
            "fecha": movimiento.get("fecha_operacion") or movimiento.get("fecha_valor") or "",
            "importe": movimiento["importe"],
            "debe_haber": _debe_haber_contable_banco(movimiento["tipo_movimiento"]),
            "concepto": movimiento.get("descripcion") or movimiento.get("concepto", ""),
        })

    return lineas


def resumen_norma43_para_ia(cuentas, movimientos, max_movimientos=40):
    lineas = [
        "Extracto bancario Norma 43:",
        f"Cuentas bancarias: {len(cuentas)}",
        "",
    ]

    for indice, cuenta in enumerate(cuentas, start=1):
        lineas.append(
            "Cuenta {idx}: entidad {entidad} oficina {oficina} número {numero} "
            "({nombre})".format(
                idx=indice,
                entidad=cuenta.get("entidad", ""),
                oficina=cuenta.get("oficina", ""),
                numero=cuenta.get("numero_cuenta", ""),
                nombre=cuenta.get("nombre_cliente", ""),
            )
        )

    lineas.append("")
    lineas.append("Movimientos bancarios:")

    for indice, movimiento in enumerate(movimientos[:max_movimientos], start=1):
        tipo = "Cargo" if movimiento["tipo_movimiento"] == "cargo" else "Abono"
        cuenta = movimiento.get("cuenta_bancaria", {})
        lineas.append(
            "Mov {idx}: {fecha} | {tipo} {importe:.2f} EUR | "
            "Cuenta {entidad}-{oficina}-{numero} | {descripcion}".format(
                idx=indice,
                fecha=movimiento.get("fecha_operacion") or movimiento.get("fecha_valor", ""),
                tipo=tipo,
                importe=movimiento["importe"],
                entidad=cuenta.get("entidad", ""),
                oficina=cuenta.get("oficina", ""),
                numero=cuenta.get("numero_cuenta", ""),
                descripcion=movimiento.get("descripcion", ""),
            )
        )

    if len(movimientos) > max_movimientos:
        lineas.append(f"... ({len(movimientos) - max_movimientos} movimientos más)")

    lineas.append("")
    lineas.append(
        "Contabiliza cada movimiento con su contrapartida (cliente, proveedor, "
        "gasto, etc.) y la cuenta de banco 572 correspondiente."
    )

    return "\n".join(lineas)


def parsear_norma43_asiento(contenido, cuenta_banco=None, cuentas_plan=None):
    texto = decodificar_csv(contenido)
    registros = _extraer_registros(texto)

    if not es_fichero_norma43(texto):
        raise CSVAsientoError("El fichero no tiene formato Norma 43 reconocible")

    cuentas, movimientos = _parsear_cuentas_norma43(registros)
    cuenta_contable = None

    if cuentas:
        cuenta_contable = buscar_cuenta_contable_banco(
            cuentas_plan,
            cuentas[0],
            cuenta_banco=cuenta_banco,
        )

    lineas = movimientos_a_lineas_banco(movimientos, cuenta_contable)
    sugerencias_banco = (
        sugerir_cuentas_contables_banco(cuentas_plan, cuentas[0])
        if cuentas
        else []
    )
    errores = []

    if movimientos and not cuenta_contable:
        errores.append({
            "fila": None,
            "mensaje": "No se pudo identificar la cuenta contable 572 del banco",
        })

    return {
        "formato": "norma43",
        "modo": "lineas" if lineas else "datos",
        "lineas": lineas,
        "num_filas": len(movimientos),
        "num_movimientos": len(movimientos),
        "cuentas_bancarias": cuentas,
        "cuenta_banco": cuenta_contable,
        "encabezados": [
            "fecha",
            "tipo",
            "importe",
            "concepto",
            "referencia",
        ],
        "delimitador": None,
        "resumen": resumen_norma43_para_ia(cuentas, movimientos),
        "movimientos": movimientos,
        "diagnostico": {
            "columnas_detectadas": [
                {"campo": "fecha", "columna": "fecha", "indice": 0},
                {"campo": "importe", "columna": "importe", "indice": 2},
                {"campo": "concepto", "columna": "concepto", "indice": 3},
            ],
            "filas_total": len(movimientos),
            "filas_validas": len(lineas),
            "filas_descartadas": len(movimientos) - len(lineas),
            "errores": errores,
            "cuentas_no_encontradas": [],
            "previsualizacion": [
                {
                    "fila": indice,
                    "estado": "ok" if cuenta_contable else "sin_cuenta_banco",
                    "mensaje": "" if cuenta_contable else "Falta cuenta bancaria 572",
                    "linea": lineas[indice - 1] if cuenta_contable and indice <= len(lineas) else None,
                    "movimiento": movimiento,
                }
                for indice, movimiento in enumerate(movimientos[:12], start=1)
            ],
            "carga_parcial": bool(lineas and len(lineas) < len(movimientos)),
            "cuenta_banco": cuenta_contable,
            "sugerencias_cuenta_banco": sugerencias_banco,
            "cuentas_bancarias": cuentas,
        },
    }
