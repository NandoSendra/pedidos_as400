import json
from pathlib import Path

from config import Config

CONTABILIDAD_OPERACIONES = frozenset({"cuentas", "crear_asiento"})

DEFAULT_ENDPOINTS = {
    "proveedores": "/proveedores",
    "articulos": "/articulos",
    "stocks": "/stocks",
    "crear_pedido": "/pedidos/crear",
    "crear_asiento": "/asientos/crear",
    "cuentas": "/cuentas",
}


def contabilidad_base_url(empresa):
    url = (
        str(empresa.get("contabilidad_base_url") or "").strip().rstrip("/")
        or str(Config.AS400_CONTABILIDAD_BASE_URL or "").strip().rstrip("/")
        or str(empresa.get("base_url", "")).strip().rstrip("/")
    )

    return url or None


def empresas_file_path():
    return Path(Config.APP_EMPRESAS_FILE)


def _read_data():
    path = empresas_file_path()

    if not path.is_file():
        return {"empresas": []}

    with path.open(encoding="utf-8") as fichero:
        data = json.load(fichero)

    if not isinstance(data, dict):
        raise ValueError("El fichero de empresas debe ser un objeto JSON")

    empresas = data.get("empresas", [])

    if not isinstance(empresas, list):
        raise ValueError("El campo empresas debe ser una lista")

    return {"empresas": empresas}


def _empresa_from_env():
    if not Config.AS400_API_BASE_URL:
        return None

    return {
        "id": "default",
        "nombre": "Principal",
        "base_url": Config.AS400_API_BASE_URL,
        "contabilidad_base_url": Config.AS400_CONTABILIDAD_BASE_URL,
        "endpoints": dict(DEFAULT_ENDPOINTS),
        "api_user": Config.AS400_API_USER,
        "api_password": Config.AS400_API_PASSWORD,
        "activa": True,
    }


def list_empresas(active_only=True):
    empresas = [dict(empresa) for empresa in _read_data()["empresas"]]

    if not empresas:
        fallback = _empresa_from_env()
        return [fallback] if fallback else []

    if active_only:
        empresas = [empresa for empresa in empresas if empresa.get("activa", True)]

    return empresas


def list_empresas_public():
    return [
        {
            "id": str(empresa.get("id", "")),
            "nombre": empresa.get("nombre") or str(empresa.get("id", "")),
        }
        for empresa in list_empresas()
    ]


def get_empresa(empresa_id):
    empresa_id = str(empresa_id or "").strip()

    if not empresa_id:
        return None

    for empresa in list_empresas(active_only=False):
        if str(empresa.get("id", "")) == empresa_id:
            if not empresa.get("activa", True):
                return None

            return dict(empresa)

    if empresa_id == "default":
        return _empresa_from_env()

    return None


def endpoint_path(empresa, operacion):
    endpoints = empresa.get("endpoints") or {}
    return endpoints.get(operacion) or DEFAULT_ENDPOINTS[operacion]
