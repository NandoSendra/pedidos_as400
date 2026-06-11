from flask import session

from empresas_store import get_empresa, list_empresas
from users_store import list_empresas_for_user


def ensure_empresa_session(username=None):
    empresas = list_empresas_for_user(username) if username else list_empresas()

    if not empresas:
        session.pop("empresa_id", None)
        return None

    empresa_id = str(session.get("empresa_id") or "").strip()
    permitidas = {str(empresa["id"]) for empresa in empresas}

    if empresa_id not in permitidas:
        empresa_id = str(empresas[0]["id"])
        session["empresa_id"] = empresa_id

    return get_empresa(empresa_id)


def set_empresa_session(username, empresa_id):
    empresa_id = str(empresa_id or "").strip()
    empresas = list_empresas_for_user(username)
    permitidas = {str(empresa["id"]) for empresa in empresas}

    if empresa_id not in permitidas:
        raise ValueError("No tienes acceso a esa empresa")

    empresa = get_empresa(empresa_id)

    if not empresa:
        raise ValueError("Empresa no disponible")

    session["empresa_id"] = empresa_id
    return empresa


def clear_empresa_session():
    session.pop("empresa_id", None)
