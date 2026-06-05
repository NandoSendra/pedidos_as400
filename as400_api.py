import requests
from urllib.parse import urlencode
from config import Config


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

    articulo["fecha_ultimo"] = _normalizar_fecha_as400(
        articulo.get("fecha_ultimo")
    )
    articulo["fecha_ultimo_consumo"] = _normalizar_fecha_as400(
        articulo.get("fecha_ultimo_consumo")
    )

    return articulo


def _get_auth():
    if Config.AS400_API_USER and Config.AS400_API_PASSWORD:
        return (Config.AS400_API_USER, Config.AS400_API_PASSWORD)

    return None


def _build_url(endpoint, params=None):
    url = f"{Config.AS400_API_BASE_URL.rstrip('/')}/{endpoint.lstrip('/')}"

    if params:
        query = urlencode(params)
        separador = "&" if "?" in url else "?"
        url = f"{url}{separador}{query}"

    return url


def _request(method, endpoint, params=None, **kwargs):
    if not Config.AS400_API_BASE_URL:
        raise AS400ApiError("No está configurada AS400_API_BASE_URL")

    url = _build_url(endpoint, params)

    try:
        response = requests.request(
            method=method,
            url=url,
            auth=_get_auth(),
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



def obtener_articulos(proveedor_codigo):
    """
    GET /articulos?proveedor={codigo}
    """
    proveedor = str(proveedor_codigo).strip()

    if not proveedor:
        raise AS400ApiError("Falta el código de proveedor")

    data = _request(
        "GET",
        "/articulos",
        params={"proveedor": proveedor},
    )
    salida = data.get("salida", data)
    articulos = salida.get("articulos", [])
    try:
        num_articulos = int(salida.get("numArticulos", len(articulos)))
    except (TypeError, ValueError):
        num_articulos = len(articulos)

    num_articulos = min(num_articulos, len(articulos))
    
    return [_normalizar_articulo(articulo) for articulo in articulos[:num_articulos]]



'''
def obtener_articulos():
    data = _request("GET", "/pedidos/articulos")

    salida = data.get("salida", data)

    success = salida.get("success")

    if success not in (True, "1", 1, "true", "True"):
        raise AS400ApiError("Error obteniendo artículos")

    articulos = salida.get("articulos", [])

    try:
        num_articulos = int(salida.get("numArticulos", len(articulos)))
    except (TypeError, ValueError):
        num_articulos = len(articulos)

    return articulos[:num_articulos]

'''
'''
def obtener_articulos():
    return [
        {
            "codigo": "ART001",
            "descripcion": "Artículo prueba 1",
            "precio": 12.5,
            "stock": 100
        },
        {
            "codigo": "ART002",
            "descripcion": "Artículo prueba 2",
            "precio": 8.75,
            "stock": 50
        }
    ]

'''

def obtener_articulo_por_codigo(codigo, proveedor_codigo):
    for articulo in obtener_articulos(proveedor_codigo):
        if articulo["codigo"] == codigo:
            return articulo

    return None

def obtener_proveedores():
    data = _request("GET", "/proveedores")

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


def crear_pedido(proveedor_codigo, carrito):
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
        "numLineasIn": len(lineas),
        "lineas": lineas
    }

    print(payload)

    data = _request("POST", "/pedidos/crear", json=payload)

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