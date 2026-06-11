import json
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

from config import Config


def _normalize_empresas(empresas):
    if empresas is None:
        return ["*"]

    if isinstance(empresas, str):
        empresas = [empresas]

    valores = [str(empresa).strip() for empresa in empresas if str(empresa).strip()]

    if not valores or "*" in valores:
        return ["*"]

    return valores


def get_user_empresas(username):
    registro = find_user_record(username)

    if not registro:
        return ["*"]

    return _normalize_empresas(registro.get("empresas"))


def user_can_access_empresa(username, empresa_id):
    empresa_id = str(empresa_id or "").strip()
    permitidas = get_user_empresas(username)

    if "*" in permitidas:
        return True

    return empresa_id in permitidas


def list_empresas_for_user(username):
    from empresas_store import list_empresas

    empresas = list_empresas()
    permitidas = get_user_empresas(username)

    if "*" in permitidas:
        return empresas

    return [
        empresa for empresa in empresas
        if str(empresa.get("id", "")) in permitidas
    ]


def format_user_empresas(username):
    from empresas_store import list_empresas_public

    permitidas = get_user_empresas(username)

    if "*" in permitidas:
        return "Todas"

    nombres = {
        empresa["id"]: empresa["nombre"]
        for empresa in list_empresas_public()
    }

    return ", ".join(
        nombres.get(empresa_id, empresa_id)
        for empresa_id in permitidas
    ) or "Ninguna"


def users_file_path():
    return Path(Config.APP_USERS_FILE)


def _read_data():
    path = users_file_path()

    if not path.is_file():
        return {"usuarios": []}

    with path.open(encoding="utf-8") as fichero:
        data = json.load(fichero)

    if not isinstance(data, dict):
        raise ValueError("El fichero de usuarios debe ser un objeto JSON")

    usuarios = data.get("usuarios", [])

    if not isinstance(usuarios, list):
        raise ValueError("El campo usuarios debe ser una lista")

    return {"usuarios": usuarios}


def _write_data(data):
    path = users_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as fichero:
        json.dump(data, fichero, indent=2, ensure_ascii=False)
        fichero.write("\n")


def list_users(active_only=True):
    usuarios = []

    for usuario in _read_data()["usuarios"]:
        if active_only and not usuario.get("activo", True):
            continue

        usuarios.append(usuario)

    return usuarios


def list_users_public(active_only=False):
    return [
        {
            "usuario": usuario.get("usuario", ""),
            "nombre": usuario.get("nombre") or usuario.get("usuario", ""),
            "activo": usuario.get("activo", True),
            "admin": user_is_effectively_admin(usuario),
            "empresas": _normalize_empresas(usuario.get("empresas")),
            "empresas_texto": format_user_empresas(usuario.get("usuario", "")),
        }
        for usuario in list_users(active_only=active_only)
    ]


def find_user_record(username, active_only=False):
    nombre = str(username or "").strip()

    if not nombre:
        return None

    for usuario in _read_data()["usuarios"]:
        if usuario.get("usuario") != nombre:
            continue

        if active_only and not usuario.get("activo", True):
            return None

        return usuario

    return None


def has_any_admin():
    return any(usuario.get("admin") for usuario in _read_data()["usuarios"])


def user_is_effectively_admin(usuario):
    if usuario.get("admin"):
        return True

    if not has_any_admin() and usuario.get("usuario") == Config.APP_LOGIN_USER:
        return True

    return False


def is_admin(username):
    nombre = str(username or "").strip()

    if not nombre:
        return False

    registro = find_user_record(nombre)

    if registro:
        return user_is_effectively_admin(registro)

    if Config.APP_LOGIN_PASSWORD and not users_file_path().is_file():
        import secrets

        return secrets.compare_digest(nombre, Config.APP_LOGIN_USER)

    return False


def count_active_admins(exclude_username=None):
    total = 0

    for usuario in _read_data()["usuarios"]:
        if not usuario.get("activo", True):
            continue

        if exclude_username and usuario.get("usuario") == exclude_username:
            continue

        if user_is_effectively_admin(usuario):
            total += 1

    return total


def auth_enabled():
    if list_users():
        return True

    return bool(Config.APP_LOGIN_PASSWORD)


def find_user(username):
    return find_user_record(username, active_only=True)


def verify_login(username, password):
    if not auth_enabled():
        return True

    usuario = str(username or "").strip()
    clave = str(password or "")

    if not usuario or not clave:
        return False

    registro = find_user(usuario)

    if registro:
        return check_password_hash(registro["password_hash"], clave)

    if Config.APP_LOGIN_PASSWORD and not users_file_path().is_file():
        import secrets

        return (
            secrets.compare_digest(usuario, Config.APP_LOGIN_USER)
            and secrets.compare_digest(clave, Config.APP_LOGIN_PASSWORD)
        )

    return False


def add_user(username, password, nombre="", admin=False, empresas=None):
    usuario = str(username or "").strip()
    clave = str(password or "")

    if not usuario:
        raise ValueError("El usuario no puede estar vacío")

    if not clave:
        raise ValueError("La contraseña no puede estar vacía")

    data = _read_data()

    for registro in data["usuarios"]:
        if registro.get("usuario") == usuario:
            raise ValueError(f"El usuario {usuario} ya existe")

    data["usuarios"].append({
        "usuario": usuario,
        "nombre": str(nombre or usuario).strip(),
        "password_hash": generate_password_hash(clave),
        "activo": True,
        "admin": bool(admin),
        "empresas": _normalize_empresas(empresas),
    })

    _write_data(data)


def set_user_empresas(username, empresas):
    usuario = str(username or "").strip()
    data = _read_data()
    encontrado = False

    for registro in data["usuarios"]:
        if registro.get("usuario") == usuario:
            registro["empresas"] = _normalize_empresas(empresas)
            encontrado = True
            break

    if not encontrado:
        raise ValueError(f"No existe el usuario {usuario}")

    _write_data(data)


def change_password(username, current_password, new_password, confirm_password=None):
    usuario = str(username or "").strip()
    actual = str(current_password or "")
    nueva = str(new_password or "")
    confirmar = str(confirm_password if confirm_password is not None else new_password or "")

    if not find_user_record(usuario):
        raise ValueError("Este usuario no puede cambiar la contraseña desde la aplicación")

    if not verify_login(usuario, actual):
        raise ValueError("La contraseña actual no es correcta")

    if not nueva:
        raise ValueError("La nueva contraseña no puede estar vacía")

    if nueva != confirmar:
        raise ValueError("Las contraseñas nuevas no coinciden")

    if actual == nueva:
        raise ValueError("La nueva contraseña debe ser distinta a la actual")

    set_password(usuario, nueva)


def set_password(username, password):
    usuario = str(username or "").strip()
    clave = str(password or "")

    if not usuario:
        raise ValueError("El usuario no puede estar vacío")

    if not clave:
        raise ValueError("La contraseña no puede estar vacía")

    data = _read_data()
    encontrado = False

    for registro in data["usuarios"]:
        if registro.get("usuario") == usuario:
            registro["password_hash"] = generate_password_hash(clave)
            registro["activo"] = True
            encontrado = True
            break

    if not encontrado:
        raise ValueError(f"No existe el usuario {usuario}")

    _write_data(data)


def set_active(username, activo, actor=None):
    usuario = str(username or "").strip()
    actor = str(actor or "").strip()
    data = _read_data()
    encontrado = False
    objetivo_admin = False

    for registro in data["usuarios"]:
        if registro.get("usuario") == usuario:
            objetivo_admin = user_is_effectively_admin(registro)
            registro["activo"] = bool(activo)
            encontrado = True
            break

    if not encontrado:
        raise ValueError(f"No existe el usuario {usuario}")

    if actor and usuario == actor and not activo:
        raise ValueError("No puedes desactivar tu propio usuario")

    if not activo and objetivo_admin and count_active_admins(exclude_username=usuario) == 0:
        raise ValueError("Debe quedar al menos un administrador activo")

    _write_data(data)


def set_admin(username, admin, actor=None):
    usuario = str(username or "").strip()
    actor = str(actor or "").strip()
    data = _read_data()
    encontrado = False

    for registro in data["usuarios"]:
        if registro.get("usuario") == usuario:
            registro["admin"] = bool(admin)
            encontrado = True
            break

    if not encontrado:
        raise ValueError(f"No existe el usuario {usuario}")

    if actor and usuario == actor and not admin and count_active_admins(exclude_username=usuario) == 0:
        raise ValueError("Debe quedar al menos un administrador activo")

    _write_data(data)
