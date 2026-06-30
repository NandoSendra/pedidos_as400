import json
import re
import unicodedata
from datetime import date

import requests

from asientos_ejemplos_store import list_ejemplos_por_empresa
from config import Config
from cuenta_tipos import (
    cuenta_utilizable_ia,
    formatear_cuenta_para_ia,
    puntuar_busqueda_cuenta,
    resolver_codigo_cuenta,
    tipos_cuenta_esperados,
)


class AIAsientoError(Exception):
    pass


STOPWORDS = frozenset({
    "por", "el", "la", "los", "las", "de", "del", "al", "en", "con", "que", "un",
    "una", "uno", "para", "desde", "hasta", "como", "sin", "sobre", "entre",
    "euro", "euros", "pago", "pague", "pagar", "pagamos", "cobro", "cobrar",
    "asiento", "contabilizar", "importe", "total", "mes", "del", "the",
})

TERCERO_STOPWORDS = frozenset({
    "cliente", "proveedor", "factura", "fatura", "venta", "ventas", "compra",
    "compras", "base", "imponible", "iva", "repercutido", "soportado", "banco",
    "cobro", "pago", "nomina", "nominas", "gasto", "gastos", "amortizacion",
    "provision", "confirming", "contado", "interno", "albaran", "facturacion",
})

TIPOS_ASIENTO = (
    {
        "id": "confirming",
        "etiqueta": "Confirming",
        "palabras": (
            "confirming", "confirmings", "descuento confirming",
            "anticipo confirming", "linea confirming",
        ),
        "prefijos": {"400", "401", "410", "411", "520", "572", "573"},
        "plantilla": (
            "Confirming / pago aplazado a proveedor: suele ser Debe proveedor (400/410) "
            "y Haber banco/confirming (572/520). Si es liquidación de confirming, "
            "ajusta al proveedor y banco indicados en el texto."
        ),
    },
    {
        "id": "nomina",
        "etiqueta": "Nóminas",
        "palabras": (
            "nomina", "nominas", "nomina mes", "sueldo", "sueldos", "salario",
            "salarios", "payroll", "seguridad social", "ss empresa", "irpf",
            "retencion", "retenciones", "embargo", "anticipo nomina",
        ),
        "prefijos": {"640", "642", "465", "475", "476", "572", "570"},
        "plantilla": (
            "Nómina: Debe gastos de personal (640x) y SS empresa (642x); "
            "Haber empleados (465x), SS acreedora (476x), IRPF (475x). "
            "Si hay pago bancario de nómina: Debe 465 / Haber 572."
        ),
    },
    {
        "id": "factura_venta",
        "etiqueta": "Factura de venta",
        "palabras": (
            "factura de venta", "factura venta", "fatura de venta", "fatura venta",
            "facturamos", "factura cliente", "base imponible", "venta a", "factura a",
            "emitimos factura", "ingreso por venta", "iva repercutido",
        ),
        "prefijos": {"430", "431", "432", "700", "701", "705", "477", "572"},
        "plantilla": (
            "Factura de venta con IVA: 3 líneas habituales — "
            "Debe cliente (430/431) por el TOTAL (base + cuota IVA); "
            "Haber ventas/ingresos (700/705) por la BASE imponible; "
            "Haber IVA repercutido (477) por la CUOTA de IVA. "
            "Elige la cuenta 477 del listado cuyo nombre coincida con el % de IVA "
            "(ej. 21% → IVA REPERCUTIDO 21%). "
            "No uses cuentas 477 de intracomunitario o terceros países salvo que el texto lo indique."
        ),
    },
    {
        "id": "factura_compra",
        "etiqueta": "Factura de compra",
        "palabras": (
            "factura de compra", "factura compra", "fatura compra", "factura proveedor",
            "compra a", "recibimos factura", "gasto factura", "proveedor factura",
            "iva soportado",
        ),
        "prefijos": {"400", "401", "410", "600", "601", "602", "621", "622", "629", "472", "572"},
        "plantilla": (
            "Factura de compra con IVA: Debe gasto/compra (600/602/621/629) por BASE; "
            "Debe IVA soportado (472) por CUOTA; Haber proveedor (400/410) por TOTAL. "
            "Elige la cuenta 472 del listado que coincida con el % de IVA "
            "(ej. 21% → IVA SOPORTADO 21%)."
        ),
    },
    {
        "id": "cobro",
        "etiqueta": "Cobro",
        "palabras": (
            "cobro", "cobrar", "cobramos", "ingreso banco", "recibimos",
            "abono en cuenta", "entrada en banco",
        ),
        "prefijos": {"430", "431", "432", "572", "570", "571"},
        "plantilla": (
            "Cobro de cliente: Debe banco/tesorería (572); Haber cliente (430/431)."
        ),
    },
    {
        "id": "pago",
        "etiqueta": "Pago",
        "palabras": (
            "pago", "pague", "pagar", "pagamos", "transferencia", "transferir",
            "domiciliacion", "domiciliación", "orden de pago",
        ),
        "prefijos": {"400", "401", "410", "411", "465", "572", "570", "571"},
        "plantilla": (
            "Pago a tercero: Debe acreedor/proveedor/empleado (400/410/465); "
            "Haber banco/tesorería (572)."
        ),
    },
    {
        "id": "gasto",
        "etiqueta": "Gasto / ticket",
        "palabras": (
            "ticket", "tickets", "gasto sin factura", "justificante", "recibo",
            "compra contado", "gasto corriente",
        ),
        "prefijos": {"629", "621", "622", "600", "572", "570"},
        "plantilla": (
            "Gasto menor o ticket: Debe gasto (629/621/622); Haber caja/banco (572/570) "
            "si se paga al contado."
        ),
    },
    {
        "id": "amortizacion",
        "etiqueta": "Amortización",
        "palabras": (
            "amortizacion", "amortización", "amortizar", "cuota amortizacion",
        ),
        "prefijos": {"681", "280", "281"},
        "plantilla": (
            "Amortización: Debe dotación (681); Haber amortización acumulada (281/280)."
        ),
    },
    {
        "id": "provision",
        "etiqueta": "Provisión",
        "palabras": (
            "provision", "provisión", "provisionar", "deterioro", "ajuste valoracion",
        ),
        "prefijos": {"681", "690", "693", "490", "593"},
        "plantilla": (
            "Provisión o deterioro: Debe gasto (681/690/693); Haber provisión (49x/59x)."
        ),
    },
    {
        "id": "banco",
        "etiqueta": "Operación bancaria",
        "palabras": (
            "banco", "santander", "bbva", "caixabank", "caixa", "sabadell",
            "bankia", "bankinter", "popular", "banco popular",
            "cuenta corriente", "tesoreria", "tesorería",
        ),
        "prefijos": {"572", "570", "571", "573", "520"},
        "plantilla": (
            "Si interviene un banco, usa la cuenta de tesorería del listado cuyo nombre "
            "coincida con ese banco. No uses préstamos (170x) salvo que el texto lo indique."
        ),
    },
)

TIPOS_ASIENTO_POR_ID = {tipo["id"]: tipo for tipo in TIPOS_ASIENTO}

PROVEEDORES_LOCAL = frozenset({"ollama", "local", "openai_compatible"})

PROVEEDORES_NUBE = frozenset({"openai", "groq", "google", "claude"})

DEFAULTS_PROVEEDOR = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "modelo": None,
        "etiqueta": "OpenAI (nube)",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "modelo": "llama-3.1-8b-instant",
        "etiqueta": "Groq (nube)",
    },
    "google": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "modelo": "gemini-2.0-flash",
        "etiqueta": "Google Gemini (nube)",
    },
    "claude": {
        "base_url": "https://api.anthropic.com/v1",
        "modelo": "claude-sonnet-4-20250514",
        "etiqueta": "Anthropic Claude (nube)",
    },
}


def ai_asiento_disponible():
    if not Config.AI_ASIENTO_ENABLED:
        return False

    if _proveedor_ia() in PROVEEDORES_LOCAL:
        return bool(Config.AI_ASIENTO_BASE_URL)

    return bool(_api_key_ia())


def ai_asiento_info():
    proveedor = _proveedor_ia()
    defaults = DEFAULTS_PROVEEDOR.get(proveedor, {})

    etiquetas_locales = {
        "ollama": "Ollama (local)",
        "local": "Modelo local",
        "openai_compatible": "API compatible OpenAI",
    }

    return {
        "proveedor": proveedor,
        "proveedor_etiqueta": defaults.get("etiqueta") or etiquetas_locales.get(proveedor, proveedor),
        "modelo": _modelo_ia(),
        "base_url": _base_url_ia() if proveedor not in PROVEEDORES_NUBE else "",
    }


def _proveedor_ia():
    proveedor = (Config.AI_ASIENTO_PROVIDER or "openai").strip().lower()

    if proveedor in {"gemini", "google_ai", "googleai"}:
        return "google"

    if proveedor in {"anthropic", "claude_ai"}:
        return "claude"

    return proveedor


def _api_key_ia():
    if Config.AI_ASIENTO_API_KEY:
        return Config.AI_ASIENTO_API_KEY

    proveedor = _proveedor_ia()

    if proveedor == "openai":
        return Config.OPENAI_API_KEY

    if proveedor == "groq":
        return Config.GROQ_API_KEY

    if proveedor == "google":
        return Config.GEMINI_API_KEY

    if proveedor == "claude":
        return Config.ANTHROPIC_API_KEY

    return ""


def _modelo_ia():
    if Config.AI_ASIENTO_MODEL:
        return Config.AI_ASIENTO_MODEL

    proveedor = _proveedor_ia()
    defaults = DEFAULTS_PROVEEDOR.get(proveedor, {})

    if defaults.get("modelo"):
        return defaults["modelo"]

    if proveedor in PROVEEDORES_LOCAL:
        return "llama3.2"

    return Config.OPENAI_MODEL


def _base_url_ia():
    proveedor = _proveedor_ia()
    personalizada = str(Config.AI_ASIENTO_BASE_URL or "").strip().rstrip("/")

    if proveedor in PROVEEDORES_LOCAL:
        return personalizada

    defaults = DEFAULTS_PROVEEDOR.get(proveedor, {})
    return str(defaults.get("base_url", "")).strip().rstrip("/")


def _url_completions():
    if _proveedor_ia() == "openai" and not Config.AI_ASIENTO_BASE_URL:
        return "https://api.openai.com/v1/chat/completions"

    base = _base_url_ia()

    if not base:
        raise AIAsientoError("Falta configurar AI_ASIENTO_BASE_URL para el proveedor de IA")

    if base.endswith("/chat/completions"):
        return base

    return f"{base}/chat/completions"


def _headers_ia():
    headers = {"Content-Type": "application/json"}
    api_key = _api_key_ia()

    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    return headers


def _soporta_json_estricto():
    return _proveedor_ia() in {"openai", "groq", "google"}


def _llamar_modelo(messages):
    payload = {
        "model": _modelo_ia(),
        "temperature": 0.1,
        "messages": messages,
    }

    if _soporta_json_estricto():
        payload["response_format"] = {"type": "json_object"}

    if _proveedor_ia() == "claude":
        payload["max_tokens"] = 4096

    try:
        timeout = Config.AI_ASIENTO_TIMEOUT

        if _proveedor_ia() in PROVEEDORES_LOCAL and timeout < 90:
            timeout = 90

        response = requests.post(
            _url_completions(),
            headers=_headers_ia(),
            json=payload,
            timeout=timeout,
        )
    except requests.RequestException as error:
        raise AIAsientoError(f"No se pudo contactar con la IA: {error}") from error

    if response.status_code >= 400:
        mensaje = response.text.strip() or f"Error HTTP {response.status_code}"
        raise AIAsientoError(f"Error del servicio de IA: {mensaje}")

    try:
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as error:
        raise AIAsientoError("Respuesta de IA inesperada") from error


def _normalizar_texto(texto):
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(
        caracter for caracter in texto
        if not unicodedata.combining(caracter)
    )
    return texto.lower().strip()


def _tokens_descripcion(descripcion):
    texto = _normalizar_texto(descripcion)
    tokens = re.findall(r"[a-z0-9]+", texto)

    return [
        token for token in tokens
        if len(token) >= 3 and token not in STOPWORDS and not token.isdigit()
    ]


def _parsear_importe_locale(texto):
    valor = re.sub(r"[€$\s]", "", str(texto or "").strip())

    if not valor:
        return None

    negativo = valor.startswith("-")
    valor = valor.lstrip("-")

    try:
        if re.fullmatch(r"\d+", valor):
            importe = float(valor)
        elif "," in valor and "." in valor:
            if valor.rfind(",") > valor.rfind("."):
                valor = valor.replace(".", "").replace(",", ".")
            else:
                valor = valor.replace(",", "")
            importe = float(valor)
        elif "," in valor:
            entero, decimal = valor.split(",", 1)

            if len(decimal) <= 2:
                importe = float(f"{entero}.{decimal}")
            else:
                importe = float(valor.replace(",", ""))
        elif "." in valor:
            entero, decimal = valor.split(".", 1)

            if len(decimal) == 3 and decimal.isdigit():
                importe = float(valor.replace(".", ""))
            else:
                importe = float(valor)
        else:
            importe = float(valor)
    except ValueError:
        return None

    if negativo:
        importe = -abs(importe)

    return round(importe, 2) if importe > 0 else None


def _extraer_nombre_tercero(descripcion):
    texto = _texto_para_analisis(descripcion)
    patrones = (
        r"factura\s+compra\s+proveedor\s+(.+?)\s*,\s*base",
        r"factura\s+venta\s+cliente\s+(.+?)\s*,\s*base",
        r"factura\s+compra\s+(?:proveedor\s+)?(.+?)\s*,\s*base",
        r"factura\s+venta\s+(?:cliente\s+)?(.+?)\s*,\s*base",
        r"factura\s+de\s+(?:la\s+)?compra\s+de\s+(.+?)\s+(?:de|por|importe|base|iva|\d)",
        r"factura\s+de\s+(?:la\s+)?compra\s+(?:a|al?\s+proveedor\s+)?(.+?)\s+(?:de|por|importe|base|iva|\d)",
        r"factura\s+a\s+(.+?)\s+(?:de|por|importe|base|iva|\d)",
        r"factura\s+de\s+venta\s+(?:a|al?\s+cliente\s+)?(.+?)\s+(?:de|por|importe|base|iva|\d)",
        r"venta\s+a\s+(.+?)\s+(?:de|por|importe|base|iva|\d)",
        r"cobro\s+(?:de|del?\s+cliente\s+)?(.+?)\s+(?:de|por|importe|\d)",
        r"pago\s+a\s+(.+?)\s+(?:de|por|importe|\d)",
        r"compra\s+a\s+(.+?)\s+(?:de|por|importe|base|iva|\d)",
        r"factura\s+de\s+(?!compra\b|venta\b)(.+?)\s+(?:de|por|importe|base|iva|\d)",
    )

    for patron in patrones:
        coincidencia = re.search(patron, texto)

        if not coincidencia:
            continue

        nombre = coincidencia.group(1).strip(" .,-")

        if len(nombre) >= 3 and nombre not in TERCERO_STOPWORDS:
            return nombre

    return ""


def _extraer_nombre_tercero_cuadre(descripcion):
    texto = _texto_para_analisis(descripcion)
    patrones = (
        r"(?:cuadr|equilibr|compens)\w*\s+(?:el\s+asiento\s+)?(?:en\s+)?"
        r"(?:la\s+cuenta\s+de\s+)?(?:proveedor|cliente|banco|acreedor)\s+(.+)",
        r"(?:cuadr|equilibr|compens)\w*\s+(?:el\s+asiento\s+)?en\s+(.+)",
    )

    for patron in patrones:
        coincidencia = re.search(patron, texto)

        if not coincidencia:
            continue

        nombre = _limpiar_nombre_tercero_anadir(coincidencia.group(1).strip(" .,-"))

        if len(nombre) >= 2 and nombre not in TERCERO_STOPWORDS:
            return nombre

    return _extraer_nombre_tercero(descripcion)


def _tokens_tercero(descripcion):
    nombre = _extraer_nombre_tercero(descripcion)

    if nombre:
        return _tokens_nombre_tercero(nombre)

    return [
        token for token in _tokens_descripcion(descripcion)
        if token not in TERCERO_STOPWORDS
    ]


def _prefijo_cuenta(codigo):
    codigo = str(codigo or "").strip()

    if len(codigo) >= 3:
        return codigo[:3]

    return codigo


def _texto_para_analisis(descripcion):
    return _normalizar_texto(
        str(descripcion or "")
        .replace("fatura", "factura")
        .replace("anade", "añade")
        .replace("anadir", "añadir")
    )


def _extraer_tipo_iva(descripcion):
    texto = _texto_para_analisis(descripcion)

    coincidencia = re.search(r"(\d{1,2})\s*%", texto)

    if coincidencia:
        return int(coincidencia.group(1))

    coincidencia = re.search(r"(?:iva|al)\s*(\d{1,2})\b", texto)

    if coincidencia:
        return int(coincidencia.group(1))

    return None


def _extraer_base_imponible(descripcion):
    texto = _texto_para_analisis(descripcion)
    patrones = (
        r"base(?:\s+imponible)?\s+([\d.,]+)\s*(?:€|euros?)?",
        r"base(?:\s+imponible)?\s+([\d.,]+)\s*\+\s*iva",
        r"base imponible(?: de)?\s*([\d.,]+)",
        r"(\d+(?:[.,]\d+)?)\s*euros?\s*(?:de base|base imponible)",
        r"(\d+(?:[.,]\d+)?)\s*euros?\s+al\s+\d",
        r"(?:de|por)\s*([\d.,]+)\s*euros?",
    )

    for patron in patrones:
        coincidencia = re.search(patron, texto)

        if coincidencia:
            importe = _parsear_importe_locale(coincidencia.group(1))

            if importe is not None:
                return importe

    return None


def _calcular_importes_factura(descripcion):
    base = _extraer_base_imponible(descripcion)
    tipo_iva = _extraer_tipo_iva(descripcion)

    if base is None or tipo_iva is None:
        return None

    cuota = round(base * tipo_iva / 100, 2)
    total = round(base + cuota, 2)

    return {
        "base": base,
        "tipo_iva": tipo_iva,
        "cuota_iva": cuota,
        "total": total,
    }


def _buscar_cuenta_iva(cuentas, naturaleza, porcentaje):
    if porcentaje is None:
        return None

    prefijo = "477" if naturaleza == "repercutido" else "472"
    clave_nombre = "repercutido" if naturaleza == "repercutido" else "soportado"
    codigo_ideal = f"{prefijo}00000{porcentaje:02d}"

    for cuenta in cuentas:
        if not cuenta_utilizable_ia(cuenta):
            continue

        if cuenta.get("codigo") == codigo_ideal:
            return cuenta

        if cuenta.get("iva_porcentaje") == porcentaje and cuenta.get("tipo") in {
            "iva_repercutido" if naturaleza == "repercutido" else "iva_soportado",
        }:
            return cuenta

    mejor = None
    mejor_puntuacion = -999

    for cuenta in cuentas:
        if not cuenta_utilizable_ia(cuenta):
            continue

        if cuenta.get("iva_porcentaje") == porcentaje and cuenta.get("tipo") in {
            "iva_repercutido" if naturaleza == "repercutido" else "iva_soportado",
        }:
            puntuacion = 50
        else:
            nombre = _normalizar_texto(cuenta.get("nombre", ""))

            if clave_nombre not in nombre:
                continue

            if f"{porcentaje}%" not in nombre and not re.search(
                rf"\b{porcentaje}\b", nombre
            ):
                continue

            puntuacion = 0

            if re.search(rf"iva {clave_nombre} {porcentaje}%", nombre):
                puntuacion += 40

            if cuenta["codigo"].startswith(f"{prefijo}00000"):
                puntuacion += 15

        if cuenta.get("subtipo") in {
            "intracomunitario", "inversion_sujeto_pasivo", "especial",
        }:
            puntuacion -= 25

        if cuenta.get("generica"):
            puntuacion -= 10

        if puntuacion > mejor_puntuacion:
            mejor_puntuacion = puntuacion
            mejor = cuenta

    return mejor


def _puntuar_nombre_tercero(nombre, tokens, palabras_clave=""):
    return puntuar_busqueda_cuenta(
        {
            "nombre": nombre,
            "tercero_nombre": "",
            "palabras_clave": palabras_clave,
        },
        tokens,
    )


def _tokens_nombre_tercero(texto):
    return [
        token for token in _tokens_tercero(texto)
        if not token.isdigit()
    ]


def _buscar_cuenta_tercero(cuentas, texto_nombre, lado_preferido=None):
    tokens = _tokens_nombre_tercero(texto_nombre)

    if not tokens:
        return None

    mejor = None
    mejor_puntuacion = 0
    prefijos = ("430", "431", "432", "400", "401", "410", "411", "465", "629", "640")

    for cuenta in cuentas:
        codigo = str(cuenta.get("codigo", ""))

        if not cuenta_utilizable_ia(cuenta):
            continue

        if not codigo.startswith(prefijos):
            continue

        puntuacion = puntuar_busqueda_cuenta(cuenta, tokens)

        if cuenta.get("generica"):
            puntuacion -= 20

        if lado_preferido and cuenta.get("debe_haber_habitual") == lado_preferido:
            puntuacion += 10

        if codigo.startswith("430"):
            puntuacion += 4

        if puntuacion > mejor_puntuacion:
            mejor_puntuacion = puntuacion
            mejor = cuenta

    return mejor if mejor_puntuacion >= 12 else None


def _buscar_mejor_cuenta_proveedor(cuentas, tokens):
    tokens_tercero = [
        token for token in tokens
        if token not in TERCERO_STOPWORDS and not token.isdigit()
    ]

    if not tokens_tercero:
        return None

    mejor = None
    mejor_puntuacion = 0

    for cuenta in cuentas:
        codigo = str(cuenta.get("codigo", ""))

        if not cuenta_utilizable_ia(cuenta):
            continue

        if not codigo.startswith(("400", "401", "410", "411")):
            continue

        puntuacion = puntuar_busqueda_cuenta(cuenta, tokens_tercero)

        if cuenta.get("generica"):
            puntuacion -= 20

        if puntuacion > mejor_puntuacion:
            mejor_puntuacion = puntuacion
            mejor = cuenta

    return mejor if mejor_puntuacion >= 12 else None


def _buscar_cuenta_cliente_descripcion(cuentas, descripcion):
    nombre_tercero = _extraer_nombre_tercero(descripcion)

    if nombre_tercero:
        cuenta = _buscar_cuenta_tercero(cuentas, nombre_tercero, lado_preferido="D")

        if cuenta:
            return cuenta

    return _buscar_mejor_cuenta_cliente(cuentas, _tokens_tercero(descripcion))


def _buscar_cuenta_proveedor_descripcion(cuentas, descripcion):
    nombre_tercero = _extraer_nombre_tercero(descripcion)

    if nombre_tercero:
        cuenta = _buscar_cuenta_tercero(cuentas, nombre_tercero, lado_preferido="H")

        if cuenta:
            return cuenta

    return _buscar_mejor_cuenta_proveedor(cuentas, _tokens_tercero(descripcion))


def _buscar_cuenta_gasto_compra(cuentas, descripcion):
    tokens = _tokens_tercero(descripcion)
    mejor = None
    mejor_puntuacion = 0
    prefijos_gasto = ("600", "601", "602", "621", "622", "629")

    for cuenta in cuentas:
        codigo = str(cuenta.get("codigo", ""))

        if not cuenta_utilizable_ia(cuenta) or not codigo.startswith(prefijos_gasto):
            continue

        puntuacion = puntuar_busqueda_cuenta(cuenta, tokens)

        if cuenta.get("tipo") in {"compra_gasto", "servicios", "otros_gastos"}:
            puntuacion += 8

        if cuenta.get("generica"):
            puntuacion -= 15

        if puntuacion > mejor_puntuacion:
            mejor_puntuacion = puntuacion
            mejor = cuenta

    if mejor and mejor_puntuacion >= 12:
        return mejor

    palabras_compra = ("compra", "mercader", "material", "aprovision", "existenc")
    mejor_fallback = None
    mejor_puntuacion_fallback = -1

    for prefijo in ("600", "602", "601", "621", "629"):
        for cuenta in cuentas:
            codigo = str(cuenta.get("codigo", ""))

            if not cuenta_utilizable_ia(cuenta) or not codigo.startswith(prefijo):
                continue

            if cuenta.get("generica"):
                continue

            nombre = _normalizar_texto(cuenta.get("nombre", ""))
            puntuacion = sum(
                10 for palabra in palabras_compra if palabra in nombre
            )

            if cuenta.get("tipo") in {"compra_gasto", "servicios"}:
                puntuacion += 6

            if puntuacion > mejor_puntuacion_fallback:
                mejor_puntuacion_fallback = puntuacion
                mejor_fallback = cuenta

    if mejor_fallback:
        return mejor_fallback

    for prefijo in ("602", "600", "621", "629"):
        for cuenta in cuentas:
            codigo = str(cuenta.get("codigo", ""))

            if (
                cuenta_utilizable_ia(cuenta)
                and codigo.startswith(prefijo)
                and not cuenta.get("generica")
            ):
                return cuenta

    return None


def _intentar_asiento_factura_rapida(descripcion, cuentas, fecha):
    importes = _calcular_importes_factura(descripcion)

    if not importes:
        return None

    tipos = _detectar_tipo_operacion(descripcion)
    es_venta = "factura_venta" in tipos
    es_compra = "factura_compra" in tipos

    if es_venta and es_compra:
        texto = _texto_para_analisis(descripcion)

        if re.search(r"factura\s+a\s+", texto):
            es_compra = False
        elif re.search(r"factura\s+de\s+(?:la\s+)?compra", texto):
            es_venta = False
        elif re.search(r"factura\s+de\s+(?:venta|cliente)", texto):
            es_compra = False
        else:
            return None

    if es_venta:
        cuenta_cliente = _buscar_cuenta_cliente_descripcion(cuentas, descripcion)
        cuenta_ventas = _buscar_cuenta_ventas(cuentas)
        cuenta_iva = _buscar_cuenta_iva(
            cuentas,
            "repercutido",
            importes["tipo_iva"],
        )

        if not cuenta_cliente or not cuenta_ventas or not cuenta_iva:
            return None

        tercero = (
            cuenta_cliente.get("tercero_nombre")
            or cuenta_cliente.get("nombre", "")
        )[:40]

        return {
            "modo": "reemplazar",
            "explicacion": (
                f"Factura de venta a {tercero}: Debe cliente "
                f"{importes['total']:.2f} € (base {importes['base']:.2f} + "
                f"IVA {importes['cuota_iva']:.2f})."
            ),
            "lineas": [
                {
                    "cuenta": cuenta_cliente["codigo"],
                    "fecha": fecha,
                    "importe": importes["total"],
                    "debe_haber": "D",
                    "concepto": f"Factura venta {tercero}",
                },
                {
                    "cuenta": cuenta_ventas["codigo"],
                    "fecha": fecha,
                    "importe": importes["base"],
                    "debe_haber": "H",
                    "concepto": f"Base imponible {importes['tipo_iva']}%",
                },
                {
                    "cuenta": cuenta_iva["codigo"],
                    "fecha": fecha,
                    "importe": importes["cuota_iva"],
                    "debe_haber": "H",
                    "concepto": f"IVA repercutido {importes['tipo_iva']}%",
                },
            ],
            "tipos_operacion": ["Factura de venta"],
        }

    if es_compra:
        cuenta_proveedor = _buscar_cuenta_proveedor_descripcion(cuentas, descripcion)
        cuenta_gasto = _buscar_cuenta_gasto_compra(cuentas, descripcion)
        cuenta_iva = _buscar_cuenta_iva(
            cuentas,
            "soportado",
            importes["tipo_iva"],
        )

        if not cuenta_proveedor or not cuenta_gasto or not cuenta_iva:
            return None

        tercero = (
            cuenta_proveedor.get("tercero_nombre")
            or cuenta_proveedor.get("nombre", "")
        )[:40]

        return {
            "modo": "reemplazar",
            "explicacion": (
                f"Factura de compra de {tercero}: Haber proveedor "
                f"{importes['total']:.2f} € (base {importes['base']:.2f} + "
                f"IVA {importes['cuota_iva']:.2f})."
            ),
            "lineas": [
                {
                    "cuenta": cuenta_gasto["codigo"],
                    "fecha": fecha,
                    "importe": importes["base"],
                    "debe_haber": "D",
                    "concepto": f"Compra {tercero}",
                },
                {
                    "cuenta": cuenta_iva["codigo"],
                    "fecha": fecha,
                    "importe": importes["cuota_iva"],
                    "debe_haber": "D",
                    "concepto": f"IVA soportado {importes['tipo_iva']}%",
                },
                {
                    "cuenta": cuenta_proveedor["codigo"],
                    "fecha": fecha,
                    "importe": importes["total"],
                    "debe_haber": "H",
                    "concepto": f"Factura compra {tercero}",
                },
            ],
            "tipos_operacion": ["Factura de compra"],
        }

    return None


def intentar_asiento_norma43_rapida(movimientos, cuentas, cuenta_banco, fecha=None):
    from norma43_asiento import _debe_haber_contable_banco

    cuenta_banco = str(cuenta_banco or "").strip()

    if not cuenta_banco or not movimientos:
        return None

    if cuenta_banco not in {str(cuenta.get("codigo", "")).strip() for cuenta in cuentas}:
        return None

    lineas = []
    fecha_default = _normalizar_fecha_sugerida(fecha)
    emparejados = 0

    for movimiento in movimientos:
        try:
            importe = round(float(movimiento.get("importe", 0)), 2)
        except (TypeError, ValueError):
            continue

        if importe <= 0:
            continue

        concepto = str(
            movimiento.get("descripcion")
            or movimiento.get("concepto", "")
        ).strip()
        tipo_movimiento = movimiento.get("tipo_movimiento", "")
        dh_banco = _debe_haber_contable_banco(tipo_movimiento)
        dh_contra = "H" if dh_banco == "D" else "D"
        fecha_linea = _normalizar_fecha_sugerida(
            movimiento.get("fecha_operacion")
            or movimiento.get("fecha_valor")
            or fecha
        )

        if tipo_movimiento == "abono":
            cuenta_contra = _buscar_cuenta_tercero(cuentas, concepto, lado_preferido="H")
        else:
            cuenta_contra = _buscar_cuenta_tercero(cuentas, concepto, lado_preferido="D")

            if not cuenta_contra:
                cuenta_contra = _buscar_cuenta_gasto_compra(cuentas, concepto)

        if not cuenta_contra:
            continue

        concepto_linea = concepto[:80] if concepto else "Movimiento bancario"
        emparejados += 1

        lineas.append({
            "cuenta": cuenta_banco,
            "fecha": fecha_linea,
            "importe": importe,
            "debe_haber": dh_banco,
            "concepto": concepto_linea,
        })
        lineas.append({
            "cuenta": cuenta_contra["codigo"],
            "fecha": fecha_linea,
            "importe": importe,
            "debe_haber": dh_contra,
            "concepto": concepto_linea,
        })

    if emparejados == 0:
        return None

    return {
        "modo": "reemplazar",
        "explicacion": (
            f"Extracto Norma 43: {emparejados} movimiento(s) contabilizado(s) "
            f"con cuenta banco {cuenta_banco} y contrapartida por tercero/gasto."
        ),
        "lineas": lineas,
        "tipos_operacion": ["Banco / tesorería"],
    }


def _parsear_importe_texto(texto):
    return _parsear_importe_locale(texto)


_VERBO_ANADIR = r"(?:anade|añade|agrega|suma|incrementa|pon)"
_IMPORTE = r"(\d+(?:[.,]\d+)?)\s*(?:€|euros?)?"
_LADO_DEBE = r"(?:al|en el)\s+debe"
_LADO_HABER = r"(?:al|en el)\s+haber"


def _extraer_lado_explicito(descripcion):
    texto = _texto_para_analisis(descripcion)

    if re.search(rf"{_LADO_HABER}\b", texto):
        return "H"

    if re.search(rf"{_LADO_DEBE}\b", texto):
        return "D"

    return None

PATRONES_ANADIR_DEBE = (
    re.compile(
        rf"{_VERBO_ANADIR}\s+{_IMPORTE}\s+(?:a|para)\s+(.+?)\s+{_LADO_DEBE}\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"{_VERBO_ANADIR}\s+{_IMPORTE}\s+{_LADO_DEBE}\s+(?:a|para|de)\s+(.+)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"{_LADO_DEBE}\s+(?:a|para|de)\s+(.+?)\s+{_VERBO_ANADIR}\s+{_IMPORTE}",
        re.IGNORECASE,
    ),
)

PATRONES_ANADIR_HABER = (
    re.compile(
        rf"{_VERBO_ANADIR}\s+{_IMPORTE}\s+(?:a|para)\s+(.+?)\s+{_LADO_HABER}\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"{_VERBO_ANADIR}\s+{_IMPORTE}\s+{_LADO_HABER}\s+(?:a|para|de)\s+(.+)",
        re.IGNORECASE,
    ),
)


def _detectar_modo_edicion(descripcion, lineas_actuales):
    if not lineas_actuales:
        return "reemplazar"

    texto = _texto_para_analisis(descripcion)

    palabras_modificar = (
        "modifica", "modificar", "cambia", "cambiar", "corrige", "corregir",
        "actualiza", "actualizar", "sustituye", "sustituir", "edita", "editar",
    )
    palabras_anadir = (
        "añade", "agrega", "suma", "incrementa", "añadir", "agregar",
        "sumar", "incorpora", "agrega linea", "añade linea", "anade",
    )
    palabras_cuadrar = (
        "cuadra", "cuadrar", "equilibra", "equilibrar", "compensa", "compensar",
    )
    palabras_conservar = (
        "sin eliminar", "no elimines", "no borres", "no quites", "no eliminar",
        "manten", "mantiene", "conserva", "conservar", "deja el asiento",
        "al asiento existente", "al asiento actual", "sin borrar",
    )

    if any(palabra in texto for palabra in palabras_modificar):
        return "modificar"

    if any(
        palabra in texto
        for palabra in palabras_anadir + palabras_cuadrar + palabras_conservar
    ):
        return "añadir"

    if re.search(r"\bpon\b", texto):
        return "añadir"

    return "reemplazar"


_ORDINALES_LINEA = {
    "primera": 1,
    "primer": 1,
    "primero": 1,
    "1a": 1,
    "segunda": 2,
    "segundo": 2,
    "2a": 2,
    "tercera": 3,
    "tercer": 3,
    "tercero": 3,
    "3a": 3,
    "cuarta": 4,
    "cuarto": 4,
    "4a": 4,
    "quinta": 5,
    "quinto": 5,
    "5a": 5,
    "ultima": -1,
    "ultimo": -1,
}


def _es_solicitud_eliminar_asiento(texto):
    if any(
        frase in texto
        for frase in (
            "no elimines", "no borres", "no quites", "no eliminar",
            "sin eliminar", "sin borrar",
        )
    ):
        return False

    patrones = (
        r"\b(?:elimina|eliminar|borra|borrar|quita|quitar|vacia|vaciar|limpia|limpiar)"
        r"\s+(?:el\s+)?asiento\b",
        r"\b(?:elimina|eliminar|borra|borrar|quita|quitar)"
        r"\s+(?:todas?\s+)?(?:las?\s+)?(?:lineas?|apuntes?|filas?)\b",
    )

    return any(re.search(patron, texto) for patron in patrones)


def _intentar_eliminar_asiento_rapida(descripcion, lineas_actuales, fecha):
    texto = _texto_para_analisis(descripcion)

    if not _es_solicitud_eliminar_asiento(texto):
        return None

    if not lineas_actuales:
        return {
            "accion": "info",
            "modo": "info",
            "explicacion": "El asiento ya está vacío.",
            "lineas": [],
        }

    return {
        "modo": "vaciar",
        "explicacion": "Se han eliminado todas las líneas del asiento.",
        "lineas": [],
        "tipos_operacion": ["Edición"],
    }


def _es_solicitud_modificar_linea(texto):
    return bool(
        re.search(
            r"\b(?:modifica|modificar|cambia|cambiar|corrige|corregir|actualiza|"
            r"actualizar|sustituye|sustituir|edita|editar)\b",
            texto,
        )
    )


def _extraer_indice_linea(descripcion, num_lineas):
    texto = _texto_para_analisis(descripcion)

    coincidencia = re.search(
        r"\b(?:la\s+)?(?:linea|apunte|fila)\s+(\d+)\b",
        texto,
    )

    if coincidencia:
        return int(coincidencia.group(1))

    coincidencia = re.search(
        r"\b(?:la\s+)?(primera|primer[ao]?|segund[ao]?|tercer[ao]?|cuart[ao]?|"
        r"quint[ao]?|ultim[ao]?|1a|2a|3a|4a|5a)\s+(?:linea|apunte|fila)\b",
        texto,
    )

    if coincidencia:
        clave = coincidencia.group(1)

        if clave.isdigit():
            return int(clave)

        return _ORDINALES_LINEA.get(clave, None)

    coincidencia = re.search(
        r"\b(?:linea|apunte|fila)\s+"
        r"(primera|primer[ao]?|segund[ao]?|tercer[ao]?|cuart[ao]?|quint[ao]?|ultim[ao]?)\b",
        texto,
    )

    if coincidencia:
        return _ORDINALES_LINEA.get(coincidencia.group(1))

    return None


def _extraer_importe_modificacion(descripcion):
    texto = _texto_para_analisis(descripcion)
    patrones = (
        r"\bpon\s+(\d+(?:[.,]\d+)?)\s*(?:€|euros?)?",
        r"\b(?:importe|cantidad)\s+(?:de|a|en)?\s*(\d+(?:[.,]\d+)?)\s*(?:€|euros?)?",
        r"\b(?:de|a)\s+(\d+(?:[.,]\d+)?)\s*(?:€|euros?)\b",
    )

    for patron in patrones:
        coincidencia = re.search(patron, texto)

        if coincidencia:
            importe = _parsear_importe_locale(coincidencia.group(1))

            if importe is not None and importe > 0:
                return importe

    return None


def _extraer_cuenta_modificacion(descripcion, cuentas):
    texto = _texto_para_analisis(descripcion)
    patrones = (
        r"\bpon(?:er)?\s+(?:la\s+)?cuenta\s+(.+?)(?:\s+y\s+|\s*,\s*|$)",
        r"\bcambia(?:r)?\s+(?:la\s+)?cuenta\s+(?:a|por|de)\s+(.+)",
    )

    for patron in patrones:
        coincidencia = re.search(patron, texto)

        if not coincidencia:
            continue

        nombre = coincidencia.group(1).strip(" .,-")

        if len(nombre) < 2:
            continue

        if nombre.isdigit():
            for cuenta in cuentas:
                if str(cuenta.get("codigo", "")).strip() == nombre:
                    return cuenta

        cuenta = _buscar_cuenta_tercero(cuentas, nombre)

        if cuenta:
            return cuenta

        cuenta = _buscar_cuenta_proveedor_descripcion(cuentas, nombre)

        if cuenta:
            return cuenta

        return _buscar_cuenta_cliente_descripcion(cuentas, nombre)

    return None


def _extraer_lado_modificacion(descripcion):
    texto = _texto_para_analisis(descripcion)

    if re.search(r"\bpon(?:er)?\s+(?:al|en el)\s+haber\b", texto):
        return "H"

    if re.search(r"\bpon(?:er)?\s+(?:al|en el)\s+debe\b", texto):
        return "D"

    if re.search(r"\bcambia(?:r)?\s+(?:a|al|en el)\s+haber\b", texto):
        return "H"

    if re.search(r"\bcambia(?:r)?\s+(?:a|al|en el)\s+debe\b", texto):
        return "D"

    return None


def _intentar_modificar_linea_rapida(descripcion, lineas_actuales, cuentas, fecha):
    texto = _texto_para_analisis(descripcion)

    if not _es_solicitud_modificar_linea(texto) or not lineas_actuales:
        return None

    indice = _extraer_indice_linea(descripcion, len(lineas_actuales))

    if indice is None:
        return {
            "accion": "pregunta",
            "modo": "pregunta",
            "explicacion": (
                "Indica qué línea quieres modificar, por ejemplo: "
                "«modifica la primera línea y pon 2000 euros» o "
                "«cambia la línea 2 al haber»."
            ),
            "pregunta": "¿Qué línea del asiento quieres modificar?",
            "lineas": [],
        }

    if indice == -1:
        indice = len(lineas_actuales)
    elif indice < 1 or indice > len(lineas_actuales):
        return {
            "accion": "pregunta",
            "modo": "pregunta",
            "explicacion": (
                f"El asiento tiene {len(lineas_actuales)} línea(s) y pediste modificar "
                f"la línea {indice}. Indica un número entre 1 y {len(lineas_actuales)}."
            ),
            "pregunta": f"¿Cuál de las {len(lineas_actuales)} líneas quieres modificar?",
            "lineas": [],
        }

    importe = _extraer_importe_modificacion(descripcion)
    cuenta = _extraer_cuenta_modificacion(descripcion, cuentas)
    lado = _extraer_lado_modificacion(descripcion)

    if importe is None and cuenta is None and lado is None:
        return {
            "accion": "pregunta",
            "modo": "pregunta",
            "explicacion": (
                f"Indica qué cambiar en la línea {indice}, por ejemplo: "
                f"«pon 2000 euros», «pon la cuenta Mercadona» o «pon al haber»."
            ),
            "pregunta": "¿Qué quieres cambiar en esa línea?",
            "lineas": [],
        }

    lineas = [dict(linea) for linea in lineas_actuales]
    linea = lineas[indice - 1]
    cambios = []

    if importe is not None:
        linea["importe"] = round(importe, 2)
        cambios.append(f"importe {importe:.2f} €")

    if cuenta is not None:
        linea["cuenta"] = cuenta["codigo"]
        nombre = cuenta.get("tercero_nombre") or cuenta.get("nombre", "")
        cambios.append(f"cuenta {cuenta['codigo']} ({nombre})")

    if lado is not None:
        linea["debe_haber"] = lado
        cambios.append("Debe" if lado == "D" else "Haber")

    return {
        "modo": "reemplazar",
        "explicacion": (
            f"Se modifica la línea {indice}: {', '.join(cambios)}. "
            "El resto del asiento se mantiene igual."
        ),
        "lineas": lineas,
        "tipos_operacion": ["Edición"],
    }


def _normalizar_lineas_actuales(lineas, fecha_default):
    normalizadas = []

    for linea in lineas or []:
        cuenta = str(linea.get("cuenta", "")).strip()

        if not cuenta:
            continue

        try:
            importe = round(float(linea.get("importe", 0)), 2)
        except (TypeError, ValueError):
            continue

        if importe <= 0:
            continue

        debe_haber = str(linea.get("debe_haber", "")).strip().upper()

        if debe_haber not in {"D", "H"}:
            continue

        concepto = str(linea.get("concepto", "")).strip() or "Línea existente"
        fecha = _normalizar_fecha_sugerida(linea.get("fecha") or fecha_default)

        normalizadas.append({
            "cuenta": cuenta,
            "fecha": fecha,
            "importe": importe,
            "debe_haber": debe_haber,
            "concepto": concepto,
        })

    return normalizadas


def _formatear_lineas_actuales_prompt(lineas):
    if not lineas:
        return ""

    filas = [
        "ASIENTO ACTUAL (conservar estas líneas salvo instrucción explícita de borrarlas):",
    ]

    for indice, linea in enumerate(lineas, start=1):
        filas.append(
            f"{indice}. {linea['cuenta']} | {linea['importe']:.2f} | "
            f"{linea['debe_haber']} | {linea['concepto']}"
        )

    return "\n".join(filas)


def _balance_lineas(lineas):
    total_debe = 0.0
    total_haber = 0.0

    for linea in lineas:
        if linea["debe_haber"] == "D":
            total_debe += linea["importe"]
        else:
            total_haber += linea["importe"]

    return round(total_debe, 2), round(total_haber, 2)


def _buscar_cuenta_en_lineas_actuales(cuentas, lineas, prefijos):
    indice = {str(cuenta.get("codigo", "")).strip(): cuenta for cuenta in cuentas}

    for linea in lineas:
        codigo = str(linea.get("cuenta", "")).strip()
        cuenta = indice.get(codigo)

        if cuenta and codigo.startswith(prefijos):
            return cuenta

    return None


_PREFIJOS_CUADRE = {
    "proveedor": ("400", "401", "410", "411"),
    "cliente": ("430", "431", "432"),
    "banco": ("572", "570", "571", "573"),
}


def _nombre_cuenta_display(cuenta):
    codigo = str(cuenta.get("codigo", "")).strip()
    nombre = (cuenta.get("tercero_nombre") or cuenta.get("nombre") or "").strip()
    return f"{codigo} ({nombre})" if nombre else codigo


def _listar_cuentas_cuadre_en_lineas(cuentas, lineas):
    indice = {str(cuenta.get("codigo", "")).strip(): cuenta for cuenta in cuentas}
    por_tipo = {}
    vistos = set()

    for linea in lineas:
        codigo = str(linea.get("cuenta", "")).strip()

        if not codigo or codigo in vistos:
            continue

        for tipo, prefijos in _PREFIJOS_CUADRE.items():
            if not codigo.startswith(prefijos):
                continue

            cuenta = indice.get(codigo) or {
                "codigo": codigo,
                "nombre": str(linea.get("concepto", "")).strip() or codigo,
            }
            por_tipo.setdefault(tipo, []).append(cuenta)
            vistos.add(codigo)
            break

    return por_tipo


def _respuesta_feedback_cuadre(accion, explicacion, pregunta=""):
    return {
        "accion": accion,
        "modo": accion,
        "explicacion": explicacion,
        "pregunta": pregunta or explicacion,
        "lineas": [],
    }


def _formatear_opciones_cuentas(cuentas, tipo=None):
    lineas = []

    for cuenta in cuentas:
        etiqueta = _nombre_cuenta_display(cuenta)
        lineas.append(f"- {etiqueta}" + (f" ({tipo})" if tipo else ""))

    return "\n".join(lineas)


def _resolver_cuenta_cuadre(
    cuentas,
    descripcion,
    lineas,
    tipo_explicito,
    cuentas_en_lineas,
    lado,
):
    if tipo_explicito:
        lista_tipo = cuentas_en_lineas.get(tipo_explicito, [])

        if len(lista_tipo) == 1:
            return lista_tipo[0], ""

        if len(lista_tipo) > 1:
            opciones = _formatear_opciones_cuentas(lista_tipo)
            return None, (
                f"Hay varias cuentas de {tipo_explicito} en el asiento:\n"
                f"{opciones}\n"
                f"Indica cuál usar, por ejemplo: "
                f"«cuadra en la cuenta de {tipo_explicito} ...»."
            )

        cuenta = _buscar_cuenta_para_cuadre(
            cuentas,
            descripcion,
            lineas,
            tipo_explicito,
            lado,
        )

        if cuenta:
            return cuenta, ""

        nombre = _extraer_nombre_tercero_cuadre(descripcion)

        if nombre:
            return None, (
                f"No encuentro una cuenta de {tipo_explicito} que coincida con «{nombre}». "
                f"Prueba con el código exacto o revisa el nombre en el plan de cuentas."
            )

        return None, (
            f"No hay cuenta de {tipo_explicito} en el asiento. "
            f"Indica el nombre o el código, por ejemplo: "
            f"«cuadra en {tipo_explicito} Cartonajes»."
        )

    todas_en_lineas = [
        (tipo, cuenta)
        for tipo, lista in cuentas_en_lineas.items()
        for cuenta in lista
    ]

    if len(todas_en_lineas) == 1:
        return todas_en_lineas[0][1], ""

    if len(todas_en_lineas) > 1:
        tipos_presentes = list(cuentas_en_lineas.keys())

        if len(tipos_presentes) == 1:
            tipo = tipos_presentes[0]
            lista = cuentas_en_lineas[tipo]
            opciones = _formatear_opciones_cuentas(lista)
            return None, (
                f"Hay varias cuentas de {tipo} en el asiento:\n"
                f"{opciones}\n"
                f"¿En cuál quieres cuadrar? Escribe por ejemplo: "
                f"«cuadra en {tipo} ...»."
            )

        lineas_opciones = []

        for tipo, lista in cuentas_en_lineas.items():
            for cuenta in lista:
                lineas_opciones.append(f"- {_nombre_cuenta_display(cuenta)} ({tipo})")

        opciones = "\n".join(lineas_opciones)
        return None, (
            "Hay varias cuentas de tercero o banco en el asiento:\n"
            f"{opciones}\n"
            "¿En cuál quieres cuadrar? Escribe por ejemplo: "
            "«cuadra en la cuenta de proveedor» o «cuadra en cliente Mercadona»."
        )

    return None, (
        "No veo cuenta de proveedor, cliente ni banco en las líneas actuales. "
        "Indica dónde cuadrar, por ejemplo: "
        "«cuadra en la cuenta de proveedor Cartonajes» o «cuadra en banco»."
    )


def _detectar_tipo_cuenta_cuadre(texto):
    if re.search(r"proveedor|acreedor|\b40[01]\b|\b41[01]\b", texto):
        return "proveedor"

    if re.search(r"cliente|\b43[012]\b", texto):
        return "cliente"

    if re.search(r"banco|tesorer|\b57[0123]\b", texto):
        return "banco"

    return None


def _buscar_cuenta_para_cuadre(cuentas, descripcion, lineas, tipo_cuenta, lado):
    prefijos = _PREFIJOS_CUADRE.get(tipo_cuenta, ())

    if prefijos:
        cuenta = _buscar_cuenta_en_lineas_actuales(cuentas, lineas, prefijos)

        if cuenta:
            return cuenta

    texto_busqueda = " ".join(
        [descripcion] + [str(linea.get("concepto", "")) for linea in lineas]
    )
    nombre = _extraer_nombre_tercero_cuadre(texto_busqueda)

    if nombre:
        if tipo_cuenta == "proveedor":
            cuenta = _buscar_cuenta_tercero(cuentas, nombre, lado_preferido=lado)

            if cuenta:
                return cuenta

            return _buscar_cuenta_proveedor_descripcion(cuentas, nombre)

        if tipo_cuenta == "cliente":
            cuenta = _buscar_cuenta_tercero(cuentas, nombre, lado_preferido=lado)

            if cuenta:
                return cuenta

            return _buscar_cuenta_cliente_descripcion(cuentas, nombre)

        if tipo_cuenta == "banco":
            return _buscar_cuenta_tercero(cuentas, nombre, lado_preferido=lado)

    if tipo_cuenta == "proveedor":
        nombre = _extraer_nombre_tercero_cuadre(descripcion)

        if nombre:
            return _buscar_cuenta_proveedor_descripcion(cuentas, descripcion)

        return None

    if tipo_cuenta == "cliente":
        nombre = _extraer_nombre_tercero_cuadre(descripcion)

        if nombre:
            return _buscar_cuenta_cliente_descripcion(cuentas, descripcion)

        return None

    if tipo_cuenta == "banco":
        nombre = _extraer_nombre_tercero_cuadre(descripcion)

        if nombre:
            return _buscar_cuenta_tercero(cuentas, nombre, lado_preferido=lado)

        return None

    return None


def _es_solicitud_cuadrar(texto):
    return any(
        palabra in texto
        for palabra in (
            "cuadra", "cuadrar", "equilibra", "equilibrar", "compensa", "compensar",
        )
    )


def _intentar_cuadrar_asiento(descripcion, lineas_actuales, cuentas, fecha):
    texto = _texto_para_analisis(descripcion)

    if not _es_solicitud_cuadrar(texto):
        return None

    if not lineas_actuales:
        return _respuesta_feedback_cuadre(
            "pregunta",
            "No hay líneas en el asiento.",
            "Añade al menos una línea antes de cuadrar.",
        )

    total_debe, total_haber = _balance_lineas(lineas_actuales)
    diferencia = round(abs(total_debe - total_haber), 2)

    if diferencia < 0.02:
        return _respuesta_feedback_cuadre(
            "info",
            f"El asiento ya cuadra: debe {total_debe:.2f} € = haber {total_haber:.2f} €.",
        )

    lado = "H" if total_debe > total_haber else "D"
    tipo_explicito = _detectar_tipo_cuenta_cuadre(texto)
    cuentas_en_lineas = _listar_cuentas_cuadre_en_lineas(cuentas, lineas_actuales)
    cuenta, mensaje_pregunta = _resolver_cuenta_cuadre(
        cuentas,
        descripcion,
        lineas_actuales,
        tipo_explicito,
        cuentas_en_lineas,
        lado,
    )

    if not cuenta:
        return _respuesta_feedback_cuadre(
            "pregunta",
            (
                f"El asiento descuadra {diferencia:.2f} € "
                f"(debe {total_debe:.2f} €, haber {total_haber:.2f} €).\n"
                f"{mensaje_pregunta}"
            ),
            mensaje_pregunta,
        )

    etiqueta_lado = "Haber" if lado == "H" else "Debe"
    nombre_cuenta = cuenta.get("tercero_nombre") or cuenta.get("nombre", "")

    return {
        "accion": "aplicar",
        "modo": "añadir",
        "explicacion": (
            f"El asiento descuadra {diferencia:.2f} € "
            f"(debe {total_debe:.2f} €, haber {total_haber:.2f} €). "
            f"Lo cuadro añadiendo {diferencia:.2f} € al {etiqueta_lado} "
            f"en {_nombre_cuenta_display(cuenta)}."
        ),
        "lineas": [{
            "cuenta": cuenta["codigo"],
            "fecha": fecha,
            "importe": diferencia,
            "debe_haber": lado,
            "concepto": f"Ajuste cuadre {nombre_cuenta[:40]}",
        }],
    }


def _limpiar_nombre_tercero_anadir(nombre):
    nombre = str(nombre or "").strip()
    nombre = re.sub(
        r"\s+(?:al|en el)\s+(?:debe|haber)\s*$",
        "",
        nombre,
        flags=re.IGNORECASE,
    )
    return re.split(r"\s*,\s*|\s+no\s+", nombre, maxsplit=1)[0].strip()


def _intentar_anadir_linea_rapida(descripcion, lineas_actuales, cuentas, fecha):
    texto = _texto_para_analisis(descripcion)

    for patron in PATRONES_ANADIR_DEBE:
        coincidencia = patron.search(texto)

        if not coincidencia:
            continue

        grupos = coincidencia.groups()

        if _parsear_importe_texto(grupos[0]) is not None:
            importe = _parsear_importe_texto(grupos[0])
            nombre = grupos[1]
        else:
            nombre = grupos[0]
            importe = _parsear_importe_texto(grupos[1])

        if importe is None:
            continue

        nombre = _limpiar_nombre_tercero_anadir(nombre)

        cuenta = _buscar_cuenta_tercero(cuentas, nombre, lado_preferido="D")

        if not cuenta:
            cuenta = _buscar_cuenta_cliente_descripcion(cuentas, nombre)

        if not cuenta:
            continue

        return {
            "modo": "añadir",
            "explicacion": (
                f"Se añade al Debe {importe:.2f} € en "
                f"{cuenta['codigo']} ({cuenta['nombre']}). "
                "Las líneas existentes se mantienen."
            ),
            "lineas": [{
                "cuenta": cuenta["codigo"],
                "fecha": fecha,
                "importe": importe,
                "debe_haber": "D",
                "concepto": f"Ajuste Debe {cuenta['nombre'][:40]}",
            }],
        }

    for patron in PATRONES_ANADIR_HABER:
        coincidencia = patron.search(texto)

        if not coincidencia:
            continue

        importe = _parsear_importe_texto(coincidencia.group(1))

        if importe is None:
            continue

        nombre = _limpiar_nombre_tercero_anadir(coincidencia.group(2))

        cuenta = _buscar_cuenta_tercero(cuentas, nombre, lado_preferido="H")

        if not cuenta:
            cuenta = _buscar_cuenta_proveedor_descripcion(cuentas, nombre)

        if not cuenta:
            continue

        return {
            "modo": "añadir",
            "explicacion": (
                f"Se añade al Haber {importe:.2f} € en "
                f"{cuenta['codigo']} ({cuenta['nombre']}). "
                "Las líneas existentes se mantienen."
            ),
            "lineas": [{
                "cuenta": cuenta["codigo"],
                "fecha": fecha,
                "importe": importe,
                "debe_haber": "H",
                "concepto": f"Ajuste Haber {cuenta['nombre'][:40]}",
            }],
        }

    return None


def _es_solicitud_anadir_base_iva(texto):
    return (
        re.search(r"(?:anade|agrega|suma|incrementa|pon)\b", texto)
        and "base" in texto
    )


def _inferir_naturaleza_factura(descripcion, cuentas, lineas):
    texto = _texto_para_analisis(descripcion)

    if any(
        palabra in texto
        for palabra in ("venta", "cliente", "repercutido", "vendemos", "cobro")
    ):
        return "venta"

    if any(
        palabra in texto
        for palabra in ("compra", "proveedor", "gasto", "soportado", "compramos")
    ):
        return "compra"

    cuentas_en_lineas = _listar_cuentas_cuadre_en_lineas(cuentas, lineas or [])

    if cuentas_en_lineas.get("cliente") and not cuentas_en_lineas.get("proveedor"):
        return "venta"

    if cuentas_en_lineas.get("proveedor") and not cuentas_en_lineas.get("cliente"):
        return "compra"

    for linea in lineas or []:
        codigo = str(linea.get("cuenta", "")).strip()

        if codigo.startswith(("700", "701", "705", "706", "708", "709", "740", "477")):
            return "venta"

        if codigo.startswith(("600", "601", "602", "621", "622", "629", "472")):
            return "compra"

    return "compra"


def _intentar_anadir_base_iva_rapida(descripcion, lineas_actuales, cuentas, fecha):
    texto = _texto_para_analisis(descripcion)

    if not _es_solicitud_anadir_base_iva(texto):
        return None

    importes = _calcular_importes_factura(descripcion)

    if not importes:
        return None

    lado_explicito = _extraer_lado_explicito(descripcion)

    if lado_explicito == "D":
        naturaleza = "compra"
    elif lado_explicito == "H":
        naturaleza = "venta"
    else:
        naturaleza = _inferir_naturaleza_factura(
            descripcion,
            cuentas,
            lineas_actuales,
        )

    mantener = bool(lineas_actuales)
    modo = "añadir" if mantener else "reemplazar"
    sufijo = " Las líneas existentes se mantienen." if mantener else ""
    etiqueta_lado = "Debe" if naturaleza == "compra" else "Haber"

    if naturaleza == "venta":
        cuenta_ventas = _buscar_cuenta_ventas(cuentas)
        cuenta_iva = _buscar_cuenta_iva(
            cuentas,
            "repercutido",
            importes["tipo_iva"],
        )

        if not cuenta_ventas or not cuenta_iva:
            return None

        return {
            "modo": modo,
            "explicacion": (
                f"Se añaden al {etiqueta_lado} líneas de base {importes['base']:.2f} € + "
                f"IVA repercutido {importes['cuota_iva']:.2f} € "
                f"({importes['tipo_iva']}%).{sufijo}"
            ),
            "lineas": [
                {
                    "cuenta": cuenta_ventas["codigo"],
                    "fecha": fecha,
                    "importe": importes["base"],
                    "debe_haber": "H",
                    "concepto": f"Base imponible venta {importes['tipo_iva']}%",
                },
                {
                    "cuenta": cuenta_iva["codigo"],
                    "fecha": fecha,
                    "importe": importes["cuota_iva"],
                    "debe_haber": "H",
                    "concepto": f"IVA repercutido {importes['tipo_iva']}%",
                },
            ],
            "tipos_operacion": ["Factura de venta"],
        }

    cuenta_gasto = _buscar_cuenta_gasto_compra(cuentas, descripcion)
    cuenta_iva = _buscar_cuenta_iva(
        cuentas,
        "soportado",
        importes["tipo_iva"],
    )

    if not cuenta_gasto or not cuenta_iva:
        return None

    return {
        "modo": modo,
        "explicacion": (
            f"Se añaden al {etiqueta_lado} líneas de base {importes['base']:.2f} € + "
            f"IVA soportado {importes['cuota_iva']:.2f} € "
            f"({importes['tipo_iva']}%).{sufijo}"
        ),
        "lineas": [
            {
                "cuenta": cuenta_gasto["codigo"],
                "fecha": fecha,
                "importe": importes["base"],
                "debe_haber": "D",
                "concepto": f"Base imponible compra {importes['tipo_iva']}%",
            },
            {
                "cuenta": cuenta_iva["codigo"],
                "fecha": fecha,
                "importe": importes["cuota_iva"],
                "debe_haber": "D",
                "concepto": f"IVA soportado {importes['tipo_iva']}%",
            },
        ],
        "tipos_operacion": ["Factura de compra"],
    }


def _buscar_mejor_cuenta_cliente(cuentas, tokens):
    tokens_tercero = [
        token for token in tokens
        if token not in TERCERO_STOPWORDS and not token.isdigit()
    ]

    if not tokens_tercero:
        return None

    mejor = None
    mejor_puntuacion = 0

    for cuenta in cuentas:
        codigo = str(cuenta.get("codigo", ""))

        if not cuenta_utilizable_ia(cuenta):
            continue

        if not codigo.startswith(("430", "431", "432")):
            continue

        puntuacion = puntuar_busqueda_cuenta(cuenta, tokens_tercero)

        if cuenta.get("generica"):
            puntuacion -= 20

        if puntuacion > mejor_puntuacion:
            mejor_puntuacion = puntuacion
            mejor = cuenta
        elif (
            puntuacion == mejor_puntuacion
            and mejor
            and codigo.startswith("430")
            and not str(mejor.get("codigo", "")).startswith("430")
        ):
            mejor = cuenta

    return mejor if mejor_puntuacion >= 12 else None


def _buscar_cuenta_ventas(cuentas):
    for cuenta in cuentas:
        nombre = _normalizar_texto(cuenta.get("nombre", ""))
        codigo = str(cuenta.get("codigo", ""))

        if codigo.startswith("700") and "venta" in nombre:
            return cuenta

    for cuenta in cuentas:
        if str(cuenta.get("codigo", "")).startswith("700"):
            return cuenta

    return None


_NOMBRES_BANCO = (
    "bankinter", "santander", "bbva", "caixabank", "caixa", "sabadell",
    "bankia", "popular", "banco popular",
    "ing", "kutxabank", "unicaja", "abanca", "ibercaja",
)


def _tokens_banco_en_texto(descripcion):
    texto = _texto_para_analisis(descripcion)
    tokens = []

    for nombre in sorted(_NOMBRES_BANCO, key=len, reverse=True):
        if re.search(rf"\b{re.escape(nombre)}\b", texto):
            tokens.append(nombre)

    if tokens:
        return tokens

    coincidencia = re.search(
        r"\bconfirming\s+por\s+([a-z0-9]+)",
        texto,
    )

    if coincidencia:
        candidato = coincidencia.group(1).strip()

        if candidato not in TERCERO_STOPWORDS and candidato not in {"de", "del", "la", "el"}:
            return [candidato]

    coincidencia = re.search(r"\bpor\s+([a-z0-9]+)\s+(?:de\s+)?\d", texto)

    if coincidencia:
        candidato = coincidencia.group(1).strip()

        if candidato not in TERCERO_STOPWORDS and candidato not in {"de", "del", "la", "el"}:
            return [candidato]

    return []


def _buscar_cuenta_banco_descripcion(cuentas, descripcion):
    tokens = _tokens_banco_en_texto(descripcion)

    if not tokens:
        return None

    mejor = None
    mejor_puntuacion = 0

    for cuenta in cuentas:
        codigo = str(cuenta.get("codigo", ""))

        if not cuenta_utilizable_ia(cuenta):
            continue

        if not codigo.startswith(("572", "570", "571", "573")):
            continue

        puntuacion = puntuar_busqueda_cuenta(cuenta, tokens)

        if cuenta.get("generica"):
            puntuacion -= 15

        if puntuacion > mejor_puntuacion:
            mejor_puntuacion = puntuacion
            mejor = cuenta

    return mejor if mejor_puntuacion >= 8 else None


def _buscar_cuenta_banco_por_texto(cuentas, texto_banco):
    return _buscar_cuenta_banco_descripcion(cuentas, texto_banco)


def _extraer_nombre_tercero_pago(descripcion):
    texto = _texto_para_analisis(descripcion)
    patrones = (
        r"\bal?\s+(?:proveedor|acreedor)\s+(.+?)$",
        r"\bal?\s+(?:proveedor|acreedor)\s+(.+?)\s+por\b",
        r"\bal?\s+cliente\s+(.+?)$",
        r"\bpago\s+(?:a|al?)\s+(.+?)\s+por\s+(?:transferencia|banco)\b",
        r"\bpaga(?:r)?\s+(.+?)\s+por\s+(?:transferencia|banco)\b",
        r"\btransferencia\s+(?:a|al?)\s+(?:proveedor\s+)?(.+?)\s+por\b",
    )

    for patron in patrones:
        coincidencia = re.search(patron, texto)

        if not coincidencia:
            continue

        nombre = coincidencia.group(1).strip(" .,-")

        for banco in _NOMBRES_BANCO:
            nombre = re.sub(rf"\s+{re.escape(banco)}.*", "", nombre)

        nombre = re.sub(r"\s+por\s+.*", "", nombre).strip()

        if len(nombre) >= 2 and nombre not in TERCERO_STOPWORDS:
            return nombre

    return ""


def _intentar_pago_transferencia_rapida(descripcion, cuentas, fecha):
    texto = _texto_para_analisis(descripcion)

    if not re.search(
        r"\b(paga|pagar|pago|pague|pagamos|transferencia|transferir)\b",
        texto,
    ):
        return None

    if re.search(
        r"\b(traspasa|traspaso|traspasar|remesa|confirming)\b",
        texto,
    ):
        return None

    importe = _extraer_base_imponible(descripcion)

    if importe is None:
        coincidencia = re.search(r"\b([\d.,]+)\s*(?:€|euros?)?\b", texto)

        if coincidencia:
            importe = _parsear_importe_locale(coincidencia.group(1))

    if importe is None or importe <= 0:
        return None

    cuenta_banco = None
    coincidencia_banco = re.search(
        r"\b(?:del?|desde|por)\s+(.+?)\s+al?\s+(?:proveedor|acreedor|cliente)\b",
        texto,
    )

    if coincidencia_banco:
        cuenta_banco = _buscar_cuenta_banco_por_texto(
            cuentas,
            coincidencia_banco.group(1),
        )

    if not cuenta_banco:
        cuenta_banco = _buscar_cuenta_banco_descripcion(cuentas, descripcion)

    if not cuenta_banco:
        return {
            "accion": "pregunta",
            "modo": "pregunta",
            "explicacion": (
                f"Pago de {importe:.2f} € detectado, pero no encuentro la cuenta del banco. "
                "Indica el banco, por ejemplo: «pago por transferencia del Sabadell "
                "al proveedor X»."
            ),
            "pregunta": "¿Qué cuenta de banco (572) debo usar?",
            "lineas": [],
        }

    nombre_tercero = _extraer_nombre_tercero_pago(descripcion)

    if not nombre_tercero:
        return {
            "accion": "pregunta",
            "modo": "pregunta",
            "explicacion": (
                f"Pago de {importe:.2f} € por {_nombre_cuenta_display(cuenta_banco)}, "
                "pero falta el tercero. Indica proveedor o cliente, por ejemplo: "
                "«pago al proveedor Pont Emballage por transferencia del Sabadell»."
            ),
            "pregunta": "¿A qué proveedor o cliente es el pago?",
            "lineas": [],
        }

    tercero_forzado = None

    if re.search(r"\bcliente\b", texto):
        tercero_forzado = "cliente"
    elif re.search(r"\bproveedor\b|\bacreedor\b", texto):
        tercero_forzado = "proveedor"

    cuenta_proveedor = _buscar_cuenta_proveedor_descripcion(cuentas, nombre_tercero)
    cuenta_cliente = _buscar_cuenta_cliente_descripcion(cuentas, nombre_tercero)

    if tercero_forzado == "proveedor":
        cuenta_tercero = cuenta_proveedor
    elif tercero_forzado == "cliente":
        cuenta_tercero = cuenta_cliente
    else:
        if (
            cuenta_proveedor
            and cuenta_cliente
            and cuenta_proveedor.get("codigo") != cuenta_cliente.get("codigo")
        ):
            opciones = "\n".join([
                f"- {_nombre_cuenta_display(cuenta_proveedor)} (proveedor)",
                f"- {_nombre_cuenta_display(cuenta_cliente)} (cliente)",
            ])
            return {
                "accion": "pregunta",
                "modo": "pregunta",
                "explicacion": (
                    f"Hay dos cuentas posibles para «{nombre_tercero}»:\n"
                    f"{opciones}\n"
                    "Indica si es cliente o proveedor."
                ),
                "pregunta": "¿Es cliente o proveedor?",
                "lineas": [],
            }

        cuenta_tercero = cuenta_proveedor or cuenta_cliente

    if not cuenta_tercero:
        return {
            "accion": "pregunta",
            "modo": "pregunta",
            "explicacion": (
                f"No encuentro cuenta para «{nombre_tercero}». "
                "Revisa el nombre en el plan o indica el código."
            ),
            "pregunta": "¿Qué cuenta de tercero debo usar?",
            "lineas": [],
        }

    nombre_tercero_cuenta = (
        cuenta_tercero.get("tercero_nombre")
        or cuenta_tercero.get("nombre", "")
    )[:40]
    nombre_banco = (
        cuenta_banco.get("tercero_nombre")
        or cuenta_banco.get("nombre", "")
    )[:40]

    return {
        "modo": "reemplazar",
        "explicacion": (
            f"Pago por transferencia: {importe:.2f} € a {nombre_tercero_cuenta} "
            f"desde {nombre_banco}."
        ),
        "lineas": [
            {
                "cuenta": cuenta_tercero["codigo"],
                "fecha": fecha,
                "importe": importe,
                "debe_haber": "D",
                "concepto": f"Pago {nombre_tercero_cuenta}",
            },
            {
                "cuenta": cuenta_banco["codigo"],
                "fecha": fecha,
                "importe": importe,
                "debe_haber": "H",
                "concepto": f"Transferencia {nombre_banco}",
            },
        ],
        "tipos_operacion": ["Pago", "Banco"],
    }


def _buscar_cuenta_confirming_deuda(cuentas, descripcion):
    tokens_banco = _tokens_banco_en_texto(descripcion)
    mejor = None
    mejor_puntuacion = 0

    for cuenta in cuentas:
        codigo = str(cuenta.get("codigo", ""))

        if not cuenta_utilizable_ia(cuenta):
            continue

        if not codigo.startswith(("520", "521")):
            continue

        nombre = _normalizar_texto(
            f"{cuenta.get('nombre', '')} {cuenta.get('palabras_clave', '')}"
        )

        if "confirming" not in nombre:
            continue

        puntuacion = 20

        if tokens_banco:
            puntuacion += sum(10 for token in tokens_banco if token in nombre)

        if puntuacion > mejor_puntuacion:
            mejor_puntuacion = puntuacion
            mejor = cuenta

    return mejor


def _extraer_proveedor_confirming(descripcion):
    texto = _texto_para_analisis(descripcion)
    patrones = (
        r"confirming\s+(?:a|al?|de|del?|proveedor)\s+(.+?)(?:\s+por\s+|\s+de\s+\d|$)",
        r"proveedor\s+(.+?)\s+confirming",
        r"confirming\s+(.+?)\s+por\s+(?:bankinter|santander|bbva|caixa|banco)",
    )

    for patron in patrones:
        coincidencia = re.search(patron, texto)

        if not coincidencia:
            continue

        nombre = coincidencia.group(1).strip(" .,-")

        for banco in _NOMBRES_BANCO:
            nombre = re.sub(rf"\s+{banco}.*", "", nombre)

        nombre = re.sub(r"\s+por\s+.*", "", nombre).strip()

        if len(nombre) >= 2 and nombre not in TERCERO_STOPWORDS:
            return nombre

    nombre = _extraer_nombre_tercero(descripcion)

    if not nombre:
        return ""

    for banco in _NOMBRES_BANCO:
        if banco in nombre:
            return ""

    return nombre


def _intentar_asiento_confirming_rapida(descripcion, cuentas, fecha):
    texto = _texto_para_analisis(descripcion)

    if "confirming" not in texto:
        return None

    importe = _extraer_base_imponible(descripcion)

    if importe is None:
        coincidencia = re.search(
            r"(?:de|por|importe)\s+(\d+(?:[.,]\d+)?)\s*(?:€|euros?)?",
            texto,
        )

        if coincidencia:
            importe = _parsear_importe_locale(coincidencia.group(1))

    if importe is None or importe <= 0:
        return None

    cuenta_banco = _buscar_cuenta_banco_descripcion(cuentas, descripcion)
    nombre_proveedor = _extraer_proveedor_confirming(descripcion)
    cuenta_proveedor = None

    if nombre_proveedor:
        cuenta_proveedor = _buscar_cuenta_proveedor_descripcion(
            cuentas,
            nombre_proveedor,
        )

    if not cuenta_banco:
        return {
            "accion": "pregunta",
            "modo": "pregunta",
            "explicacion": (
                f"Confirming de {importe:.2f} € detectado, pero no encuentro la cuenta "
                "de banco en el plan. Indica el banco, por ejemplo: "
                "«confirming por Bankinter de 1000 euros»."
            ),
            "pregunta": "¿Qué cuenta de banco o confirming debo usar?",
            "lineas": [],
        }

    nombre_banco = cuenta_banco.get("tercero_nombre") or cuenta_banco.get("nombre", "")

    if cuenta_proveedor:
        nombre_prov = (
            cuenta_proveedor.get("tercero_nombre")
            or cuenta_proveedor.get("nombre", "")
        )

        return {
            "modo": "reemplazar",
            "explicacion": (
                f"Confirming: pago a {nombre_prov} por {importe:.2f} € "
                f"vía {nombre_banco}."
            ),
            "lineas": [
                {
                    "cuenta": cuenta_proveedor["codigo"],
                    "fecha": fecha,
                    "importe": importe,
                    "debe_haber": "D",
                    "concepto": f"Confirming {nombre_prov[:40]}",
                },
                {
                    "cuenta": cuenta_banco["codigo"],
                    "fecha": fecha,
                    "importe": importe,
                    "debe_haber": "H",
                    "concepto": f"Confirming {nombre_banco[:40]}",
                },
            ],
            "tipos_operacion": ["Confirming"],
        }

    cuenta_confirming = _buscar_cuenta_confirming_deuda(cuentas, descripcion)

    if cuenta_confirming:
        nombre_conf = cuenta_confirming.get("nombre", "")

        return {
            "modo": "reemplazar",
            "explicacion": (
                f"Confirming por {importe:.2f} €: Debe {nombre_conf}, "
                f"Haber {nombre_banco}."
            ),
            "lineas": [
                {
                    "cuenta": cuenta_confirming["codigo"],
                    "fecha": fecha,
                    "importe": importe,
                    "debe_haber": "D",
                    "concepto": f"Confirming {nombre_conf[:40]}",
                },
                {
                    "cuenta": cuenta_banco["codigo"],
                    "fecha": fecha,
                    "importe": importe,
                    "debe_haber": "H",
                    "concepto": f"Confirming {nombre_banco[:40]}",
                },
            ],
            "tipos_operacion": ["Confirming"],
        }

    return {
        "accion": "pregunta",
        "modo": "pregunta",
        "explicacion": (
            f"Confirming de {importe:.2f} € por {nombre_banco}, pero falta el proveedor. "
            "Indica el proveedor, por ejemplo: "
            "«confirming proveedor Cartonajes por Bankinter de 1000 euros»."
        ),
        "pregunta": "¿A qué proveedor corresponde el confirming?",
        "lineas": [],
    }


def _intentar_liquidar_remesa_rapida(descripcion, cuentas, fecha):
    """
    Frases tipo:
    - "Liquida una remesa de Miguel Sardina de 1000 euros por banco popular"
    - "Liquidar remesa proveedor X por banco Y importe 1000"
    """
    texto = _texto_para_analisis(descripcion)

    if not re.search(r"\b(remesa|remesas)\b", texto):
        return None

    if not re.search(r"\b(liquida|liquidar|liquidacion|liquidación)\b", texto):
        return None

    coincidencia = re.search(
        r"\b(?:remesa)\s+de\s+(.+?)\s+(?:de|por|importe)\s+([\d.,]+)\b",
        texto,
    )
    proveedor_texto = ""
    importe = None

    if coincidencia:
        proveedor_texto = coincidencia.group(1).strip(" .,-")
        importe = _parsear_importe_locale(coincidencia.group(2))
    else:
        coincidencia = re.search(
            r"\b(?:remesa)\s+(?:cliente|proveedor|acreedor)\s+(.+?)\s+(?:de|por|importe)\s+([\d.,]+)\b",
            texto,
        )

        if coincidencia:
            proveedor_texto = coincidencia.group(1).strip(" .,-")
            importe = _parsear_importe_locale(coincidencia.group(2))
        else:
        # Fallback: intenta extraer importe y tercero por heurística
            importe = _extraer_base_imponible(descripcion)
            proveedor_texto = _extraer_nombre_tercero_cuadre(descripcion) or _extraer_nombre_tercero(descripcion)

    if importe is None or importe <= 0:
        return None

    cuenta_banco = _buscar_cuenta_banco_descripcion(cuentas, descripcion)

    if not cuenta_banco:
        return {
            "accion": "pregunta",
            "modo": "pregunta",
            "explicacion": (
                f"Remesa detectada por {importe:.2f} €, pero no encuentro la cuenta del banco. "
                "Indica el banco tal como aparece en el plan (p. ej. «por banco Popular»)."
            ),
            "pregunta": "¿Qué cuenta de banco (572) debo usar?",
            "lineas": [],
        }

    # El tercero puede ser cliente o proveedor. Si es ambiguo, preguntar.
    tercero_forzado = None
    if re.search(r"\bcliente\b", texto):
        tercero_forzado = "cliente"
    elif re.search(r"\bproveedor\b|\bacreedor\b", texto):
        tercero_forzado = "proveedor"

    cuenta_proveedor = (
        _buscar_cuenta_proveedor_descripcion(cuentas, proveedor_texto)
        if proveedor_texto
        else None
    )
    cuenta_cliente = (
        _buscar_cuenta_cliente_descripcion(cuentas, proveedor_texto)
        if proveedor_texto
        else None
    )

    if tercero_forzado == "proveedor":
        cuenta_tercero = cuenta_proveedor
    elif tercero_forzado == "cliente":
        cuenta_tercero = cuenta_cliente
    else:
        if cuenta_proveedor and cuenta_cliente and cuenta_proveedor.get("codigo") != cuenta_cliente.get("codigo"):
            opciones = "\n".join(
                [
                    f"- {_nombre_cuenta_display(cuenta_proveedor)} (proveedor)",
                    f"- {_nombre_cuenta_display(cuenta_cliente)} (cliente)",
                ]
            )
            return {
                "accion": "pregunta",
                "modo": "pregunta",
                "explicacion": (
                    f"Encuentro dos cuentas posibles para «{proveedor_texto}»:\n"
                    f"{opciones}\n"
                    "¿Cuál quieres usar? Escribe por ejemplo: "
                    "«liquida remesa CLIENTE Miguel Sardina ...» o "
                    "«liquida remesa PROVEEDOR Miguel Sardina ...»."
                ),
                "pregunta": "¿Es cliente o proveedor?",
                "lineas": [],
            }

        cuenta_tercero = cuenta_proveedor or cuenta_cliente

    if not cuenta_tercero:
        return {
            "accion": "pregunta",
            "modo": "pregunta",
            "explicacion": (
                f"Remesa por {importe:.2f} € vía {_nombre_cuenta_display(cuenta_banco)}, "
                "pero no encuentro el proveedor. Indica el nombre o el código, por ejemplo: "
                "«liquida remesa proveedor Miguel Sardina ...»."
            ),
            "pregunta": "¿A qué tercero corresponde la remesa?",
            "lineas": [],
        }

    nombre_prov = (
        cuenta_tercero.get("tercero_nombre")
        or cuenta_tercero.get("nombre", "")
    )[:40]
    nombre_banco = (
        cuenta_banco.get("tercero_nombre")
        or cuenta_banco.get("nombre", "")
    )[:40]

    return {
        "modo": "reemplazar",
        "explicacion": (
            f"Liquidación de remesa: pago a {nombre_prov} por {importe:.2f} € "
            f"vía {nombre_banco}."
        ),
        "lineas": [
            {
                "cuenta": cuenta_tercero["codigo"],
                "fecha": fecha,
                "importe": importe,
                "debe_haber": "D",
                "concepto": f"Remesa {nombre_prov}",
            },
            {
                "cuenta": cuenta_banco["codigo"],
                "fecha": fecha,
                "importe": importe,
                "debe_haber": "H",
                "concepto": f"Remesa {nombre_banco}",
            },
        ],
        "tipos_operacion": ["Pago", "Banco"],
    }


def _intentar_traspaso_entre_bancos_rapida(descripcion, cuentas, fecha):
    texto = _texto_para_analisis(descripcion)

    if not re.search(r"\b(traspasa|traspaso|traspasar)\b", texto):
        return None

    # Importe
    coincidencia = re.search(r"\b([\d.,]+)\s*(?:€|euros?)?\b", texto)
    importe = _parsear_importe_locale(coincidencia.group(1)) if coincidencia else None

    if importe is None or importe <= 0:
        return None

    # Origen / destino
    # Ej: "del sabadell al bankinter"
    m = re.search(r"\bdel?\s+(.+?)\s+al?\s+(.+?)(?:\s|$)", texto)
    origen_txt = ""
    destino_txt = ""

    if m:
        origen_txt = m.group(1).strip(" .,-")
        destino_txt = m.group(2).strip(" .,-")
    else:
        # fallback: usa bancos detectados
        bancos = _tokens_banco_en_texto(descripcion)
        if len(bancos) >= 2:
            origen_txt, destino_txt = bancos[0], bancos[1]

    if not origen_txt or not destino_txt:
        return {
            "accion": "pregunta",
            "modo": "pregunta",
            "explicacion": (
                "Para traspasos necesito origen y destino, por ejemplo: "
                "«traspasa 1000 euros del Sabadell al Bankinter»."
            ),
            "pregunta": "¿De qué banco a qué banco es el traspaso?",
            "lineas": [],
        }

    def buscar_banco_por_nombre(nombre_banco):
        tokens = _tokens_banco_en_texto(nombre_banco) or [
            token for token in re.split(r"[^a-z0-9]+", _texto_para_analisis(nombre_banco))
            if token and token not in TERCERO_STOPWORDS
        ]

        mejor = None
        mejor_puntuacion = 0

        for cuenta in cuentas:
            codigo = str(cuenta.get("codigo", ""))

            if not cuenta_utilizable_ia(cuenta):
                continue

            if not codigo.startswith(("572", "570", "571", "573")):
                continue

            puntuacion = puntuar_busqueda_cuenta(cuenta, tokens)

            if cuenta.get("generica"):
                puntuacion -= 15

            if puntuacion > mejor_puntuacion:
                mejor_puntuacion = puntuacion
                mejor = cuenta

        return mejor if mejor_puntuacion >= 8 else None

    cuenta_origen = buscar_banco_por_nombre(origen_txt)
    cuenta_destino = buscar_banco_por_nombre(destino_txt)

    if not cuenta_origen or not cuenta_destino:
        faltan = []
        if not cuenta_origen:
            faltan.append(f"origen («{origen_txt}»)")
        if not cuenta_destino:
            faltan.append(f"destino («{destino_txt}»)")
        return {
            "accion": "pregunta",
            "modo": "pregunta",
            "explicacion": (
                "No encuentro la cuenta de banco "
                + " y ".join(faltan)
                + ". Indica el nombre tal como aparece en el plan (cuentas 572/570/571)."
            ),
            "pregunta": "¿Qué cuentas bancarias debo usar para el traspaso?",
            "lineas": [],
        }

    if str(cuenta_origen.get("codigo")) == str(cuenta_destino.get("codigo")):
        return {
            "accion": "pregunta",
            "modo": "pregunta",
            "explicacion": (
                f"El banco origen y destino parecen ser la misma cuenta ({_nombre_cuenta_display(cuenta_origen)}). "
                "Indica dos cuentas distintas."
            ),
            "pregunta": "¿Cuál es la cuenta destino?",
            "lineas": [],
        }

    nombre_origen = (
        cuenta_origen.get("tercero_nombre")
        or cuenta_origen.get("nombre", "")
    )[:40]
    nombre_destino = (
        cuenta_destino.get("tercero_nombre")
        or cuenta_destino.get("nombre", "")
    )[:40]

    return {
        "modo": "reemplazar",
        "explicacion": (
            f"Traspaso bancario: {importe:.2f} € de {nombre_origen} a {nombre_destino}."
        ),
        "lineas": [
            {
                "cuenta": cuenta_destino["codigo"],
                "fecha": fecha,
                "importe": importe,
                "debe_haber": "D",
                "concepto": f"Traspaso desde {nombre_origen}",
            },
            {
                "cuenta": cuenta_origen["codigo"],
                "fecha": fecha,
                "importe": importe,
                "debe_haber": "H",
                "concepto": f"Traspaso a {nombre_destino}",
            },
        ],
        "tipos_operacion": ["Banco"],
    }


def _inyectar_cuentas_prioritarias(descripcion, cuentas, tipos_operacion, seleccionadas):
    prioritarias = []
    tokens = _tokens_descripcion(descripcion)
    tokens_tercero = _tokens_tercero(descripcion)
    porcentaje_iva = _extraer_tipo_iva(descripcion) or 21

    if "factura_venta" in tipos_operacion:
        cuenta_cliente = _buscar_cuenta_cliente_descripcion(cuentas, descripcion)

        if cuenta_cliente:
            prioritarias.append(cuenta_cliente)

        cuenta_iva = _buscar_cuenta_iva(cuentas, "repercutido", porcentaje_iva)

        if cuenta_iva:
            prioritarias.append(cuenta_iva)

        cuenta_ventas = _buscar_cuenta_ventas(cuentas)

        if cuenta_ventas:
            prioritarias.append(cuenta_ventas)

    if "factura_compra" in tipos_operacion:
        cuenta_proveedor = _buscar_cuenta_proveedor_descripcion(cuentas, descripcion)

        if cuenta_proveedor:
            prioritarias.append(cuenta_proveedor)

        cuenta_gasto = _buscar_cuenta_gasto_compra(cuentas, descripcion)

        if cuenta_gasto:
            prioritarias.append(cuenta_gasto)

        cuenta_iva = _buscar_cuenta_iva(cuentas, "soportado", porcentaje_iva)

        if cuenta_iva:
            prioritarias.append(cuenta_iva)

    if not prioritarias:
        return seleccionadas

    fusionadas = []
    vistos = set()

    for cuenta in prioritarias + seleccionadas:
        codigo = cuenta["codigo"]

        if codigo in vistos:
            continue

        vistos.add(codigo)
        fusionadas.append(cuenta)

    return fusionadas


def _detalle_cuenta_fiscal(cuenta):
    detalle = f"{cuenta['codigo']} | {cuenta['nombre']}"

    if cuenta.get("debe_haber_habitual"):
        lado = "Debe" if cuenta["debe_haber_habitual"] == "D" else "Haber"
        detalle += f" ({lado} habitual)"

    if cuenta.get("rol_factura"):
        roles = {
            "base": "base imponible",
            "cuota_iva": "cuota IVA",
            "total": "total factura",
        }
        detalle += f" [{roles.get(cuenta['rol_factura'], cuenta['rol_factura'])}]"

    if cuenta.get("iva_porcentaje") is not None:
        detalle += f" — IVA {cuenta['iva_porcentaje']}%"

    return detalle


def _resumen_fiscal_prompt(descripcion, cuentas, tipos_operacion):
    importes = _calcular_importes_factura(descripcion)

    if not importes:
        return ""

    lineas = [
        "CÁLCULO FISCAL DETECTADO:",
        f"- Base imponible: {importes['base']:.2f}",
        f"- Tipo IVA: {importes['tipo_iva']}%",
        f"- Cuota IVA: {importes['cuota_iva']:.2f}",
        f"- Total factura: {importes['total']:.2f}",
    ]

    if "factura_venta" in tipos_operacion:
        cuenta_iva = _buscar_cuenta_iva(cuentas, "repercutido", importes["tipo_iva"])

        if cuenta_iva:
            lineas.append(
                "- Cuenta IVA repercutido recomendada: "
                f"{_detalle_cuenta_fiscal(cuenta_iva)}"
            )

        cuenta_cliente = _buscar_cuenta_cliente_descripcion(cuentas, descripcion)

        if cuenta_cliente:
            lineas.append(
                "- Cuenta cliente recomendada: "
                f"{_detalle_cuenta_fiscal(cuenta_cliente)}"
            )

        cuenta_ventas = _buscar_cuenta_ventas(cuentas)

        if cuenta_ventas:
            lineas.append(
                "- Cuenta ventas recomendada: "
                f"{_detalle_cuenta_fiscal(cuenta_ventas)}"
            )

        lineas.append(
            f"- Asiento esperado: Debe cliente {importes['total']:.2f}; "
            f"Haber ventas {importes['base']:.2f}; "
            f"Haber IVA repercutido {importes['cuota_iva']:.2f}"
        )

    if "factura_compra" in tipos_operacion:
        cuenta_iva = _buscar_cuenta_iva(cuentas, "soportado", importes["tipo_iva"])

        if cuenta_iva:
            lineas.append(
                "- Cuenta IVA soportado recomendada: "
                f"{_detalle_cuenta_fiscal(cuenta_iva)}"
            )

        cuenta_proveedor = _buscar_cuenta_proveedor_descripcion(cuentas, descripcion)

        if cuenta_proveedor:
            lineas.append(
                "- Cuenta proveedor recomendada: "
                f"{_detalle_cuenta_fiscal(cuenta_proveedor)}"
            )

        cuenta_gasto = _buscar_cuenta_gasto_compra(cuentas, descripcion)

        if cuenta_gasto:
            lineas.append(
                "- Cuenta gasto/compra recomendada: "
                f"{_detalle_cuenta_fiscal(cuenta_gasto)}"
            )

        lineas.append(
            f"- Asiento esperado: Debe gasto {importes['base']:.2f}; "
            f"Debe IVA soportado {importes['cuota_iva']:.2f}; "
            f"Haber proveedor {importes['total']:.2f}"
        )

    return "\n".join(lineas)


def _seleccionar_ejemplos_similares(descripcion, empresa_id, limite=5):
    ejemplos = list_ejemplos_por_empresa(empresa_id)

    if not ejemplos:
        return []

    tokens = set(_tokens_descripcion(descripcion))
    tipos = set(_detectar_tipo_operacion(descripcion))
    puntuadas = []

    for ejemplo in ejemplos:
        score = 0
        descripcion_ejemplo = str(ejemplo.get("descripcion", ""))
        tokens_ejemplo = set(_tokens_descripcion(descripcion_ejemplo))

        score += len(tokens & tokens_ejemplo) * 12

        for token in tokens:
            if token in _normalizar_texto(descripcion_ejemplo):
                score += 4

        tipos_ejemplo = set(ejemplo.get("tipos_operacion") or [])

        score += len(tipos & tipos_ejemplo) * 18

        for cuenta in ejemplo.get("lineas", []):
            nombre_cuenta = _normalizar_texto(cuenta.get("concepto", ""))

            for token in tokens:
                if token in nombre_cuenta:
                    score += 3

        if score > 0:
            puntuadas.append((score, ejemplo))

    if not puntuadas and ejemplos:
        ejemplos_ordenados = sorted(
            ejemplos,
            key=lambda item: item.get("actualizado") or item.get("creado") or "",
            reverse=True,
        )
        return ejemplos_ordenados[:limite]

    puntuadas.sort(key=lambda item: item[0], reverse=True)

    return [ejemplo for _, ejemplo in puntuadas[:limite]]


def _formatear_ejemplos_prompt(ejemplos):
    if not ejemplos:
        return ""

    lineas = [
        "EJEMPLOS REALES APRENDIDOS DE ESTA EMPRESA "
        "(prioriza el mismo criterio de cuentas, importes y Debe/Haber):",
    ]

    for indice, ejemplo in enumerate(ejemplos, start=1):
        lineas.append(f"\nEjemplo {indice}: {ejemplo.get('descripcion', '')}")

        for linea in ejemplo.get("lineas", []):
            lineas.append(
                f"  - {linea['cuenta']} | {linea['importe']:.2f} | "
                f"{linea['debe_haber']} | {linea['concepto']}"
            )

    return "\n".join(lineas)


def _detectar_tipo_operacion(descripcion):
    texto = _texto_para_analisis(descripcion)
    detectados = []

    for tipo in TIPOS_ASIENTO:
        if any(palabra in texto for palabra in tipo["palabras"]):
            detectados.append(tipo["id"])

    if "factura" in texto or "base imponible" in texto:
        if (
            "factura_venta" not in detectados
            and re.search(r"factura\s+a\s+", texto)
        ):
            detectados.insert(0, "factura_venta")

        if (
            "factura_compra" not in detectados
            and re.search(r"factura\s+de\s+(?:la\s+)?compra", texto)
        ):
            detectados.insert(0, "factura_compra")

        if (
            "factura_compra" not in detectados
            and re.search(r"factura\s+de\s+", texto)
            and not re.search(r"factura\s+de\s+(?:venta|cliente)", texto)
        ):
            detectados.insert(0, "factura_compra")

        if (
            "factura_venta" not in detectados
            and any(
                palabra in texto
                for palabra in ("venta", "cliente", "vendemos", "cobro", "repercutido")
            )
        ):
            detectados.insert(0, "factura_venta")

        if (
            "factura_compra" not in detectados
            and any(
                palabra in texto
                for palabra in ("compra", "proveedor", "gasto", "recibimos", "soportado")
            )
        ):
            detectados.insert(0, "factura_compra")

    if "iva" in texto:
        if "factura_venta" not in detectados and any(
            palabra in texto for palabra in ("venta", "cliente", "cobro", "repercutido")
        ):
            detectados.insert(0, "factura_venta")

        if "factura_compra" not in detectados and any(
            palabra in texto for palabra in ("compra", "proveedor", "soportado", "gasto")
        ):
            detectados.insert(0, "factura_compra")

    vistos = set()
    ordenados = []

    for tipo_id in detectados:
        if tipo_id not in vistos:
            vistos.add(tipo_id)
            ordenados.append(tipo_id)

    return ordenados or ["general"]


def _prefijos_para_tipos(tipos_operacion):
    prefijos = set()

    for tipo_id in tipos_operacion:
        tipo = TIPOS_ASIENTO_POR_ID.get(tipo_id)

        if tipo:
            prefijos.update(tipo["prefijos"])

    return prefijos


def _guia_tipos_asiento(tipos_operacion):
    lineas = []

    for tipo_id in tipos_operacion:
        tipo = TIPOS_ASIENTO_POR_ID.get(tipo_id)

        if tipo:
            lineas.append(f"- {tipo['etiqueta']}: {tipo['plantilla']}")

    if not lineas:
        lineas.append(
            "- Operación general: identifica terceros, bancos e importes en el plan "
            "contable y propón un asiento cuadrado."
        )

    return "\n".join(lineas)


def _puntuar_cuenta(cuenta, tokens, descripcion_norm, tipos_operacion):
    if not cuenta_utilizable_ia(cuenta):
        return -999

    nombre = _normalizar_texto(cuenta.get("nombre", ""))
    codigo = str(cuenta.get("codigo", "")).strip()
    prefijo = _prefijo_cuenta(codigo)
    prefijos_tipo = _prefijos_para_tipos(tipos_operacion)
    score = 0

    for token in tokens:
        if token in nombre:
            score += 12

        if token in codigo:
            score += 4

        if any(token in palabra for palabra in re.split(r"[^a-z0-9]+", nombre)):
            score += 8

        palabras_clave = _normalizar_texto(cuenta.get("palabras_clave", ""))

        if palabras_clave and token in palabras_clave:
            score += 14

    coincidencias = sum(
        1 for token in tokens
        if token in nombre
        or any(token in palabra for palabra in re.split(r"[^a-z0-9]+", nombre))
    )

    if coincidencias >= 2:
        score += 18 * (coincidencias - 1)

    if tokens and all(token in nombre for token in tokens[:3]):
        score += 30

    if prefijo in prefijos_tipo:
        score += 10

    tipo_cuenta = cuenta.get("tipo", "")
    tipos_esperados = tipos_cuenta_esperados(tipos_operacion)

    if tipo_cuenta and tipo_cuenta in tipos_esperados:
        score += 18

    if tipo_cuenta in {"iva_repercutido_especial", "iva_soportado_especial"}:
        if not any(
            termino in descripcion_norm
            for termino in ("intracom", "intrac", "invers", "tercer", "3o", "3º")
        ):
            score -= 12

    if tipo_cuenta == "capital" and tipos_operacion:
        score -= 8

    if cuenta.get("generica"):
        score -= 12

    porcentaje_iva = _extraer_tipo_iva(descripcion_norm)

    if (
        porcentaje_iva is not None
        and cuenta.get("iva_porcentaje") == porcentaje_iva
        and tipo_cuenta in {"iva_repercutido", "iva_soportado"}
    ):
        score += 25

    if "factura_venta" in tipos_operacion:
        if cuenta.get("tipo") == "cliente" and cuenta.get("debe_haber_habitual") == "D":
            score += 12

        if cuenta.get("tipo") == "ventas" and cuenta.get("debe_haber_habitual") == "H":
            score += 12

        if (
            cuenta.get("rol_factura") == "cuota_iva"
            and cuenta.get("debe_haber_habitual") == "H"
        ):
            score += 15

    if "factura_compra" in tipos_operacion:
        if cuenta.get("tipo") == "proveedor" and cuenta.get("debe_haber_habitual") == "H":
            score += 12

        if (
            cuenta.get("rol_factura") == "cuota_iva"
            and cuenta.get("debe_haber_habitual") == "D"
        ):
            score += 15

    if prefijo in {"472", "477"} and any(
        tipo in tipos_operacion for tipo in ("factura_compra", "factura_venta")
    ):
        score += 12

    if "factura_venta" in tipos_operacion:
        if prefijo.startswith("430") or prefijo.startswith("431"):
            score += 14

        if prefijo.startswith("400") or prefijo.startswith("401"):
            score -= 6

        if prefijo == "477" and "repercut" in nombre:
            score += 20

    if "factura_compra" in tipos_operacion:
        if prefijo.startswith("400") or prefijo.startswith("410"):
            score += 8

        if prefijo == "472" and "soport" in nombre:
            score += 20

    if "nomina" in tipos_operacion and prefijo in {"640", "642", "465", "475", "476"}:
        score += 8

    if "confirming" in tipos_operacion and prefijo in {"400", "401", "410", "520", "572"}:
        score += 6

    if "banco" in tipos_operacion and any(
        termino in nombre
        for termino in (
            "banco", "bbva", "santander", "caixa", "sabadell", "bankia", "bankinter",
            "popular",
        )
    ):
        score += 8

    if "pago" in tipos_operacion and "banco" in tipos_operacion:
        if prefijo in {"170", "174"} and any(
            termino in nombre for termino in ("prestamo", "ptmo", "leasing", "fin.inm")
        ):
            score -= 30

        if prefijo in {"520", "570", "571", "572", "573"}:
            score += 10

    return score


def _seleccionar_cuentas_relevantes(descripcion, cuentas, max_cuentas=120):
    tokens = _tokens_descripcion(descripcion)
    descripcion_norm = _normalizar_texto(descripcion)
    tipos_operacion = _detectar_tipo_operacion(descripcion)

    if not tokens:
        return cuentas[:max_cuentas], tipos_operacion, []

    puntuadas = []

    for cuenta in cuentas:
        score = _puntuar_cuenta(cuenta, tokens, descripcion_norm, tipos_operacion)

        if score > 0:
            puntuadas.append((score, cuenta))

    puntuadas.sort(key=lambda item: (-item[0], item[1]["codigo"]))

    seleccionadas = []
    vistos = set()

    for _, cuenta in puntuadas:
        codigo = cuenta["codigo"]

        if codigo in vistos:
            continue

        vistos.add(codigo)
        seleccionadas.append(cuenta)

        if len(seleccionadas) >= max_cuentas:
            break

    if len(seleccionadas) < 20:
        for token in tokens:
            for cuenta in cuentas:
                codigo = cuenta["codigo"]

                if codigo in vistos:
                    continue

                nombre = _normalizar_texto(cuenta.get("nombre", ""))

                if token in nombre:
                    seleccionadas.append(cuenta)
                    vistos.add(codigo)

                if len(seleccionadas) >= max_cuentas:
                    break

            if len(seleccionadas) >= max_cuentas:
                break

    seleccionadas = _inyectar_cuentas_prioritarias(
        descripcion,
        cuentas,
        tipos_operacion,
        seleccionadas or cuentas[:max_cuentas],
    )[:max_cuentas]

    return (
        seleccionadas,
        tipos_operacion,
        tokens,
    )


def _formatear_plan_cuentas(cuentas):
    return "\n".join(
        formatear_cuenta_para_ia(cuenta)
        for cuenta in cuentas
        if cuenta_utilizable_ia(cuenta)
    )


def _reglas_sistema():
    tipos_conocidos = ", ".join(tipo["etiqueta"] for tipo in TIPOS_ASIENTO)

    reglas = [
        "Eres un contable experto en España.",
        "Conoces asientos de: " + tipos_conocidos + ".",
        "Propón asientos cuadrados (debe = haber) usando EXCLUSIVAMENTE cuentas del listado.",
        "Cada cuenta del listado incluye metadatos del ERP: tipo, IVA %, rol en factura "
        "(base/cuota/total), Debe/Haber habitual, masas PyG/Balance y palabras clave. "
        "Usa esos metadatos para elegir la cuenta correcta en cada línea del asiento. "
        "Prioriza cuentas cuyo IVA % coincida con el de la operación. "
        "Evita cuentas genéricas o marcadas como INACTIVA.",
        "Los códigos de cuenta son exactos, sin inventar ni acortar.",
        "En el JSON, el campo cuenta debe contener SOLO el código numérico "
        "(ej. 4300048018), nunca el nombre ni los metadatos del listado.",
        "Si el usuario menciona un tercero (persona o empresa), elige la cuenta cuyo nombre "
        "coincida mejor con TODAS las palabras relevantes del tercero.",
        "Si hay varias cuentas parecidas, prioriza la que incluya más coincidencias del nombre.",
        "En facturas con IVA incluido, calcula base imponible e IVA (21% salvo que el texto indique otro).",
        "No uses cuentas de préstamo (170x, 174x) para pagos o cobros ordinarios.",
        "No uses cuentas de capital o reservas (100x-129x) para operaciones corrientes.",
        "Importes siempre positivos, mayores que cero; nunca uses importe 0. debe_haber solo D o H.",
        "Responde solo JSON válido con esta estructura:",
        '{"modo":"reemplazar o añadir","explicacion":"breve resumen",'
        '"lineas":[{"cuenta":"codigo","importe":0.0,"debe_haber":"D o H","concepto":"texto"}]}',
        "Usa modo añadir cuando debas incorporar líneas al asiento actual sin borrarlo; "
        "en ese caso lineas contiene SOLO las líneas nuevas.",
    ]

    reglas_extra = str(Config.AI_ASIENTO_REGLAS or "").strip()

    if reglas_extra:
        reglas.append(f"Reglas adicionales de la empresa: {reglas_extra}")

    return "\n".join(reglas)


def _extraer_json(texto):
    texto = str(texto or "").strip()

    if not texto:
        raise AIAsientoError("La IA no devolvió contenido")

    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        pass

    bloque = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", texto, re.DOTALL)

    if bloque:
        try:
            return json.loads(bloque.group(1))
        except json.JSONDecodeError:
            pass

    inicio = texto.find("{")
    fin = texto.rfind("}")

    if inicio >= 0 and fin > inicio:
        try:
            return json.loads(texto[inicio:fin + 1])
        except json.JSONDecodeError as error:
            raise AIAsientoError("La IA no devolvió un JSON válido") from error

    raise AIAsientoError("La IA no devolvió un JSON válido")


def _normalizar_fecha_sugerida(fecha):
    if fecha:
        texto = str(fecha).strip().replace("-", "")

        if len(texto) == 8 and texto.isdigit():
            return texto

    return date.today().strftime("%Y%m%d")


def _validar_lineas_sugeridas(lineas, cuentas, fecha, requiere_cuadre=True):
    if not lineas:
        raise AIAsientoError("La IA no propuso ninguna línea")

    codigos_validos = {str(cuenta["codigo"]).strip() for cuenta in cuentas}
    normalizadas = []
    total_debe = 0.0
    total_haber = 0.0

    for indice, linea in enumerate(lineas, start=1):
        cuenta = resolver_codigo_cuenta(linea.get("cuenta", ""), cuentas)
        concepto = str(linea.get("concepto", "")).strip()

        try:
            importe = round(float(linea.get("importe", 0)), 2)
        except (TypeError, ValueError):
            raise AIAsientoError(f"Importe no válido en la línea {indice} de la IA")

        debe_haber = str(linea.get("debe_haber", "")).strip().upper()

        if debe_haber in ("D", "DEBE"):
            debe_haber = "D"
        elif debe_haber in ("H", "HABER"):
            debe_haber = "H"
        else:
            raise AIAsientoError(
                f"Debe/Haber no válido en la línea {indice} de la IA"
            )

        if cuenta not in codigos_validos:
            raise AIAsientoError(
                f"La cuenta {cuenta or '(vacía)'} de la línea {indice} "
                "no existe en el plan contable cargado"
            )

        if not concepto:
            raise AIAsientoError(f"Falta concepto en la línea {indice} de la IA")

        if importe <= 0:
            raise AIAsientoError(
                f"Importe no válido en la línea {indice} de la IA "
                "(debe ser mayor que 0 €)"
            )

        if debe_haber == "D":
            total_debe += importe
        else:
            total_haber += importe

        normalizadas.append({
            "cuenta": cuenta,
            "fecha": _normalizar_fecha_sugerida(linea.get("fecha") or fecha),
            "importe": importe,
            "debe_haber": debe_haber,
            "concepto": concepto,
        })

    if requiere_cuadre and round(total_debe, 2) != round(total_haber, 2):
        raise AIAsientoError(
            "La sugerencia de la IA no cuadra "
            f"(debe {total_debe:.2f}, haber {total_haber:.2f})"
        )

    return normalizadas


def sugerir_asiento_contable(
    descripcion,
    cuentas,
    fecha=None,
    lineas_actuales=None,
    empresa_id=None,
):
    if not ai_asiento_disponible():
        raise AIAsientoError(
            "El asistente de IA no está configurado. "
            "Activa AI_ASIENTO_ENABLED y configura OpenAI, Groq, Google Gemini, "
            "Claude u Ollama en el .env."
        )

    descripcion = str(descripcion or "").strip()

    if len(descripcion) < 10 and not any(
        detector(_texto_para_analisis(descripcion))
        for detector in (_es_solicitud_cuadrar, _es_solicitud_eliminar_asiento)
    ):
        raise AIAsientoError("Describe la operación con un poco más de detalle")

    if not cuentas:
        raise AIAsientoError("No hay cuentas contables cargadas para la empresa")

    fecha_asiento = _normalizar_fecha_sugerida(fecha)
    lineas_actuales = _normalizar_lineas_actuales(lineas_actuales, fecha_asiento)
    modo_edicion = _detectar_modo_edicion(descripcion, lineas_actuales)

    rapida_vaciar = _intentar_eliminar_asiento_rapida(
        descripcion,
        lineas_actuales,
        fecha_asiento,
    )

    if rapida_vaciar:
        if rapida_vaciar.get("accion") in {"pregunta", "info"}:
            return {
                "success": True,
                "modo": rapida_vaciar["modo"],
                "explicacion": rapida_vaciar["explicacion"],
                "pregunta": rapida_vaciar.get("pregunta", ""),
                "lineas": [],
                "cuentas_candidatas": 0,
                "tipos_operacion": ["Edición"],
            }

        return {
            "success": True,
            "modo": rapida_vaciar.get("modo", "vaciar"),
            "explicacion": rapida_vaciar["explicacion"],
            "lineas": [],
            "cuentas_candidatas": 0,
            "tipos_operacion": rapida_vaciar.get("tipos_operacion", ["Edición"]),
        }

    if modo_edicion == "modificar":
        rapida = _intentar_modificar_linea_rapida(
            descripcion,
            lineas_actuales,
            cuentas,
            fecha_asiento,
        )

        if rapida:
            if rapida.get("accion") in {"pregunta", "info"}:
                return {
                    "success": True,
                    "modo": rapida["modo"],
                    "explicacion": rapida["explicacion"],
                    "pregunta": rapida.get("pregunta", ""),
                    "lineas": [],
                    "cuentas_candidatas": 0,
                    "tipos_operacion": ["Edición"],
                }

            lineas = _validar_lineas_sugeridas(
                rapida["lineas"],
                cuentas,
                fecha_asiento,
                requiere_cuadre=False,
            )

            return {
                "success": True,
                "modo": rapida.get("modo", "reemplazar"),
                "explicacion": rapida["explicacion"],
                "lineas": lineas,
                "cuentas_candidatas": 0,
                "tipos_operacion": rapida.get("tipos_operacion", ["Edición"]),
            }

    if modo_edicion == "añadir":
        rapida = _intentar_cuadrar_asiento(
            descripcion,
            lineas_actuales,
            cuentas,
            fecha_asiento,
        )

        if not rapida:
            rapida = _intentar_anadir_linea_rapida(
                descripcion,
                lineas_actuales,
                cuentas,
                fecha_asiento,
            )

        if not rapida:
            rapida = _intentar_anadir_base_iva_rapida(
                descripcion,
                lineas_actuales,
                cuentas,
                fecha_asiento,
            )

        if rapida:
            if rapida.get("accion") in {"pregunta", "info"}:
                return {
                    "success": True,
                    "modo": rapida["modo"],
                    "explicacion": rapida["explicacion"],
                    "pregunta": rapida.get("pregunta", ""),
                    "lineas": [],
                    "cuentas_candidatas": 0,
                    "tipos_operacion": ["Cuadre"],
                }

            lineas = _validar_lineas_sugeridas(
                rapida["lineas"],
                cuentas,
                fecha_asiento,
                requiere_cuadre=False,
            )

            return {
                "success": True,
                "modo": "añadir",
                "explicacion": rapida["explicacion"],
                "lineas": lineas,
                "cuentas_candidatas": 0,
                "tipos_operacion": rapida.get("tipos_operacion", ["Edición"]),
            }

    if modo_edicion != "añadir":
        rapida_confirming = _intentar_asiento_confirming_rapida(
            descripcion,
            cuentas,
            fecha_asiento,
        )

        if rapida_confirming:
            if rapida_confirming.get("accion") in {"pregunta", "info"}:
                return {
                    "success": True,
                    "modo": rapida_confirming["modo"],
                    "explicacion": rapida_confirming["explicacion"],
                    "pregunta": rapida_confirming.get("pregunta", ""),
                    "lineas": [],
                    "cuentas_candidatas": 0,
                    "tipos_operacion": ["Confirming"],
                }

            lineas = _validar_lineas_sugeridas(
                rapida_confirming["lineas"],
                cuentas,
                fecha_asiento,
            )

            return {
                "success": True,
                "modo": "reemplazar",
                "explicacion": rapida_confirming["explicacion"],
                "lineas": lineas,
                "cuentas_candidatas": 0,
                "tipos_operacion": rapida_confirming.get("tipos_operacion", ["Confirming"]),
            }

        rapida_traspaso = _intentar_traspaso_entre_bancos_rapida(
            descripcion,
            cuentas,
            fecha_asiento,
        )

        if rapida_traspaso:
            if rapida_traspaso.get("accion") in {"pregunta", "info"}:
                return {
                    "success": True,
                    "modo": rapida_traspaso["modo"],
                    "explicacion": rapida_traspaso["explicacion"],
                    "pregunta": rapida_traspaso.get("pregunta", ""),
                    "lineas": [],
                    "cuentas_candidatas": 0,
                    "tipos_operacion": rapida_traspaso.get("tipos_operacion", ["Edición"]),
                }

            lineas = _validar_lineas_sugeridas(
                rapida_traspaso["lineas"],
                cuentas,
                fecha_asiento,
            )

            return {
                "success": True,
                "modo": rapida_traspaso.get("modo", "reemplazar"),
                "explicacion": rapida_traspaso["explicacion"],
                "lineas": lineas,
                "cuentas_candidatas": 0,
                "tipos_operacion": rapida_traspaso.get("tipos_operacion", ["Edición"]),
            }

        rapida_pago = _intentar_pago_transferencia_rapida(
            descripcion,
            cuentas,
            fecha_asiento,
        )

        if rapida_pago:
            if rapida_pago.get("accion") in {"pregunta", "info"}:
                return {
                    "success": True,
                    "modo": rapida_pago["modo"],
                    "explicacion": rapida_pago["explicacion"],
                    "pregunta": rapida_pago.get("pregunta", ""),
                    "lineas": [],
                    "cuentas_candidatas": 0,
                    "tipos_operacion": rapida_pago.get("tipos_operacion", ["Edición"]),
                }

            lineas = _validar_lineas_sugeridas(
                rapida_pago["lineas"],
                cuentas,
                fecha_asiento,
            )

            return {
                "success": True,
                "modo": rapida_pago.get("modo", "reemplazar"),
                "explicacion": rapida_pago["explicacion"],
                "lineas": lineas,
                "cuentas_candidatas": 0,
                "tipos_operacion": rapida_pago.get("tipos_operacion", ["Pago", "Banco"]),
            }

        rapida_remesa = _intentar_liquidar_remesa_rapida(
            descripcion,
            cuentas,
            fecha_asiento,
        )

        if rapida_remesa:
            if rapida_remesa.get("accion") in {"pregunta", "info"}:
                return {
                    "success": True,
                    "modo": rapida_remesa["modo"],
                    "explicacion": rapida_remesa["explicacion"],
                    "pregunta": rapida_remesa.get("pregunta", ""),
                    "lineas": [],
                    "cuentas_candidatas": 0,
                    "tipos_operacion": rapida_remesa.get("tipos_operacion", ["Edición"]),
                }

            lineas = _validar_lineas_sugeridas(
                rapida_remesa["lineas"],
                cuentas,
                fecha_asiento,
            )

            return {
                "success": True,
                "modo": rapida_remesa.get("modo", "reemplazar"),
                "explicacion": rapida_remesa["explicacion"],
                "lineas": lineas,
                "cuentas_candidatas": 0,
                "tipos_operacion": rapida_remesa.get("tipos_operacion", ["Edición"]),
            }

        rapida_factura = _intentar_asiento_factura_rapida(
            descripcion,
            cuentas,
            fecha_asiento,
        )

        if not rapida_factura:
            rapida_factura = _intentar_anadir_base_iva_rapida(
                descripcion,
                lineas_actuales,
                cuentas,
                fecha_asiento,
            )

        if rapida_factura:
            lineas = _validar_lineas_sugeridas(
                rapida_factura["lineas"],
                cuentas,
                fecha_asiento,
                requiere_cuadre=rapida_factura.get("modo") != "añadir",
            )

            return {
                "success": True,
                "modo": rapida_factura.get("modo", "reemplazar"),
                "explicacion": rapida_factura["explicacion"],
                "lineas": lineas,
                "cuentas_candidatas": 0,
                "tipos_operacion": rapida_factura.get("tipos_operacion", []),
            }

    descripcion_busqueda = descripcion

    if lineas_actuales:
        descripcion_busqueda = (
            f"{descripcion}\n"
            + " ".join(
                linea["concepto"]
                for linea in lineas_actuales
            )
        )

    cuentas_ia, tipos_operacion, tokens = _seleccionar_cuentas_relevantes(
        descripcion_busqueda,
        cuentas,
    )
    plan_cuentas = _formatear_plan_cuentas(cuentas_ia)
    guia_tipos = _guia_tipos_asiento(tipos_operacion)
    resumen_fiscal = _resumen_fiscal_prompt(descripcion, cuentas, tipos_operacion)
    tipos_etiquetas = [
        TIPOS_ASIENTO_POR_ID[tipo_id]["etiqueta"]
        for tipo_id in tipos_operacion
        if tipo_id in TIPOS_ASIENTO_POR_ID
    ] or ["General"]

    if modo_edicion == "añadir":
        tipos_etiquetas = ["Edición"] + tipos_etiquetas

    lineas_actuales_prompt = _formatear_lineas_actuales_prompt(lineas_actuales)
    instruccion_edicion = ""

    if modo_edicion == "añadir":
        instruccion_edicion = (
            "\nINSTRUCCIÓN DE EDICIÓN: El usuario quiere MODIFICAR el asiento actual "
            "sin eliminarlo. Responde con modo \"añadir\" y en lineas SOLO las líneas "
            "nuevas que haya que incorporar. No hace falta que el resultado parcial cuadre."
        )

    ejemplos_similares = _seleccionar_ejemplos_similares(
        descripcion,
        empresa_id or "default",
        limite=5,
    )
    ejemplos_prompt = _formatear_ejemplos_prompt(ejemplos_similares)

    prompt_usuario = f"""Operación a contabilizar:
{descripcion}

Fecha del asiento: {fecha_asiento}
Tipos detectados: {", ".join(tipos_etiquetas)}
Palabras clave detectadas: {", ".join(tokens) if tokens else "(ninguna)"}
{lineas_actuales_prompt}
{instruccion_edicion}
{ejemplos_prompt}

GUÍA POR TIPO DE ASIENTO:
{guia_tipos}
{resumen_fiscal}

CUENTAS CANDIDATAS del plan contable (codigo|nombre|tipo|metadatos).
Debes elegir SOLO cuentas de este listado, con el código exacto:
{plan_cuentas}
"""

    messages = [
        {
            "role": "system",
            "content": _reglas_sistema(),
        },
        {
            "role": "user",
            "content": prompt_usuario,
        },
    ]

    contenido = _llamar_modelo(messages)
    resultado = _extraer_json(contenido)
    modo_resultado = str(resultado.get("modo", modo_edicion)).strip().lower()

    if modo_resultado not in {"añadir", "anadir", "agregar", "add"}:
        modo_resultado = "reemplazar"
    else:
        modo_resultado = "añadir"

    lineas = _validar_lineas_sugeridas(
        resultado.get("lineas", []),
        cuentas,
        fecha_asiento,
        requiere_cuadre=modo_resultado != "añadir",
    )

    explicacion = str(resultado.get("explicacion", "")).strip()

    if ejemplos_similares:
        aviso_ejemplos = f" Usados {len(ejemplos_similares)} ejemplo(s) aprendido(s) de la empresa."
    else:
        aviso_ejemplos = ""

    aviso = (
        f" (analizadas {len(cuentas_ia)} cuentas candidatas de "
        f"{len(cuentas)} en el plan){aviso_ejemplos}"
    )

    return {
        "success": True,
        "modo": modo_resultado,
        "explicacion": f"{explicacion}{aviso}".strip(),
        "lineas": lineas,
        "cuentas_candidatas": len(cuentas_ia),
        "tipos_operacion": tipos_etiquetas,
        "ejemplos_usados": len(ejemplos_similares),
    }
