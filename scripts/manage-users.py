#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from users_store import add_user, list_users, set_active, set_admin, set_password, set_user_empresas, users_file_path


def comando_listar(_args):
    usuarios = list_users(active_only=False)

    if not usuarios:
        print("No hay usuarios definidos.")
        print(f"Fichero: {users_file_path()}")
        return

    for usuario in usuarios:
        estado = "activo" if usuario.get("activo", True) else "inactivo"
        nombre = usuario.get("nombre") or usuario.get("usuario")
        rol = "admin" if usuario.get("admin") else "usuario"
        empresas = usuario.get("empresas", ["*"])
        empresas_txt = "todas" if "*" in empresas else ",".join(empresas)
        print(f"- {usuario['usuario']} ({nombre}) [{estado}, {rol}, empresas: {empresas_txt}]")


def comando_anadir(args):
    empresas = args.empresas or ["*"]
    add_user(args.usuario, args.password, args.nombre, admin=args.admin, empresas=empresas)
    print(f"Usuario creado: {args.usuario}")


def comando_empresas(args):
    set_user_empresas(args.usuario, args.empresas)
    print(f"Empresas actualizadas: {args.usuario}")


def comando_admin(args):
    set_admin(args.usuario, args.admin)
    rol = "administrador" if args.admin else "usuario"
    print(f"{args.usuario} es ahora {rol}")


def comando_password(args):
    set_password(args.usuario, args.password)
    print(f"Contraseña actualizada: {args.usuario}")


def comando_desactivar(args):
    set_active(args.usuario, False)
    print(f"Usuario desactivado: {args.usuario}")


def comando_activar(args):
    set_active(args.usuario, True)
    print(f"Usuario activado: {args.usuario}")


def main():
    parser = argparse.ArgumentParser(description="Gestión de usuarios de pedidos_as400")
    subparsers = parser.add_subparsers(dest="comando", required=True)

    listar = subparsers.add_parser("list", help="Listar usuarios")
    listar.set_defaults(func=comando_listar)

    anadir = subparsers.add_parser("add", help="Crear usuario")
    anadir.add_argument("usuario")
    anadir.add_argument("--password", required=True)
    anadir.add_argument("--nombre", default="")
    anadir.add_argument("--admin", action="store_true")
    anadir.add_argument("--empresas", nargs="*", help="IDs de empresa o * para todas")
    anadir.set_defaults(func=comando_anadir)

    empresas = subparsers.add_parser("empresas", help="Asignar empresas a un usuario")
    empresas.add_argument("usuario")
    empresas.add_argument("empresas", nargs="+", help="IDs de empresa o * para todas")
    empresas.set_defaults(func=comando_empresas)

    rol = subparsers.add_parser("admin", help="Asignar o quitar rol administrador")
    rol.add_argument("usuario")
    rol.add_argument("--on", dest="admin", action="store_true")
    rol.add_argument("--off", dest="admin", action="store_false")
    rol.set_defaults(admin=True, func=comando_admin)

    password = subparsers.add_parser("password", help="Cambiar contraseña")
    password.add_argument("usuario")
    password.add_argument("--password", required=True)
    password.set_defaults(func=comando_password)

    desactivar = subparsers.add_parser("deactivate", help="Desactivar usuario")
    desactivar.add_argument("usuario")
    desactivar.set_defaults(func=comando_desactivar)

    activar = subparsers.add_parser("activate", help="Activar usuario")
    activar.add_argument("usuario")
    activar.set_defaults(func=comando_activar)

    args = parser.parse_args()

    try:
        args.func(args)
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
