from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from config import Config
from as400_api import (
    obtener_articulos,
    crear_pedido,
    AS400ApiError,
    obtener_proveedores,
    obtener_stocks,
)
from auth import admin_required, init_auth, safe_next_url
from empresa_session import clear_empresa_session, ensure_empresa_session, set_empresa_session
from empresas_store import list_empresas_public
from users_store import (
    add_user,
    auth_enabled,
    change_password,
    is_admin,
    list_empresas_for_user,
    list_users_public,
    set_active,
    set_admin,
    set_password,
    set_user_empresas,
    verify_login,
)

app = Flask(__name__)
app.config.from_object(Config)
init_auth(app)


@app.route("/")
def index():
    return redirect(url_for("pedido"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if not auth_enabled():
        return redirect(url_for("pedido"))

    if session.get("usuario"):
        return redirect(safe_next_url(request.args.get("next")))

    error = None
    next_url = safe_next_url(request.args.get("next"))

    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        password = request.form.get("password", "")

        if verify_login(usuario, password):
            session.permanent = True
            session["usuario"] = usuario
            session["es_admin"] = is_admin(usuario)
            ensure_empresa_session(usuario)
            return redirect(safe_next_url(request.args.get("next")))

        error = "Usuario o contraseña incorrectos"

    return render_template("login.html", error=error, next=next_url)


@app.route("/logout")
def logout():
    session.pop("usuario", None)
    session.pop("es_admin", None)
    clear_empresa_session()
    return redirect(url_for("login"))


def _pedido_context():
    usuario = session.get("usuario")
    empresas = list_empresas_for_user(usuario) if usuario else list_empresas_for_user(None)
    empresa = ensure_empresa_session(usuario)

    return {
        "usuario": usuario,
        "auth_enabled": auth_enabled(),
        "es_admin": session.get("es_admin", False),
        "empresas": [
            {"id": str(item["id"]), "nombre": item.get("nombre") or str(item["id"])}
            for item in empresas
        ],
        "empresa_actual": {
            "id": str(empresa["id"]),
            "nombre": empresa.get("nombre") or str(empresa["id"]),
        } if empresa else None,
    }


def _admin_redirect(mensaje, tipo="ok"):
    return redirect(url_for("admin_usuarios", mensaje=mensaje, tipo=tipo))


@app.route("/cuenta/password", methods=["GET", "POST"])
def cuenta_password():
    if not auth_enabled():
        return redirect(url_for("pedido"))

    usuario = session.get("usuario")

    if not usuario:
        return redirect(url_for("login", next=url_for("cuenta_password")))

    error = None
    ok = None

    if request.method == "POST":
        try:
            change_password(
                usuario,
                request.form.get("password_actual", ""),
                request.form.get("password_nueva", ""),
                request.form.get("password_nueva_confirmar", ""),
            )
            ok = "Contraseña actualizada correctamente"
        except ValueError as exc:
            error = str(exc)

    return render_template(
        "cuenta_password.html",
        usuario=usuario,
        error=error,
        ok=ok,
        es_admin=session.get("es_admin", False),
    )


@app.route("/admin/usuarios")
@admin_required
def admin_usuarios():
    return render_template(
        "admin_usuarios.html",
        usuarios=list_users_public(),
        empresas_disponibles=list_empresas_public(),
        actor=session.get("usuario"),
        mensaje=request.args.get("mensaje"),
        mensaje_tipo=request.args.get("tipo", "ok"),
    )


@app.route("/admin/usuarios/nuevo", methods=["POST"])
@admin_required
def admin_usuarios_crear():
    try:
        empresas = request.form.getlist("empresas")
        add_user(
            request.form.get("usuario", ""),
            request.form.get("password", ""),
            request.form.get("nombre", ""),
            admin=bool(request.form.get("admin")),
            empresas=empresas,
        )
        return _admin_redirect("Usuario creado correctamente")
    except ValueError as error:
        return _admin_redirect(str(error), "error")


@app.route("/admin/usuarios/<username>/password", methods=["POST"])
@admin_required
def admin_usuarios_password(username):
    try:
        set_password(username, request.form.get("password", ""))
        return _admin_redirect(f"Contraseña actualizada para {username}")
    except ValueError as error:
        return _admin_redirect(str(error), "error")


@app.route("/admin/usuarios/<username>/estado", methods=["POST"])
@admin_required
def admin_usuarios_estado(username):
    activo = request.form.get("activo") == "1"

    try:
        set_active(username, activo, actor=session.get("usuario"))
        accion = "activado" if activo else "desactivado"
        return _admin_redirect(f"Usuario {username} {accion}")
    except ValueError as error:
        return _admin_redirect(str(error), "error")


@app.route("/admin/usuarios/<username>/rol", methods=["POST"])
@admin_required
def admin_usuarios_rol(username):
    admin = request.form.get("admin") == "1"

    try:
        set_admin(username, admin, actor=session.get("usuario"))
        rol = "administrador" if admin else "usuario"
        return _admin_redirect(f"{username} es ahora {rol}")
    except ValueError as error:
        return _admin_redirect(str(error), "error")


@app.route("/admin/usuarios/<username>/empresas", methods=["POST"])
@admin_required
def admin_usuarios_empresas(username):
    try:
        set_user_empresas(username, request.form.getlist("empresas"))
        return _admin_redirect(f"Empresas actualizadas para {username}")
    except ValueError as error:
        return _admin_redirect(str(error), "error")


@app.route("/api/empresa", methods=["POST"])
def api_empresa():
    usuario = session.get("usuario")

    if auth_enabled() and not usuario:
        return jsonify({
            "success": False,
            "mensaje": "No autorizado"
        }), 401

    data = request.get_json(silent=True) or {}
    empresa_id = str(data.get("empresa_id", "")).strip()

    if not empresa_id:
        return jsonify({
            "success": False,
            "mensaje": "Seleccione una empresa"
        }), 400

    try:
        empresa = set_empresa_session(usuario, empresa_id)
        return jsonify({
            "success": True,
            "empresa": {
                "id": str(empresa["id"]),
                "nombre": empresa.get("nombre") or str(empresa["id"]),
            }
        })
    except ValueError as error:
        return jsonify({
            "success": False,
            "mensaje": str(error)
        }), 400


@app.route("/pedido")
def pedido():
    error = None
    proveedores = []
    contexto = _pedido_context()
    empresa = ensure_empresa_session(session.get("usuario"))

    if not empresa:
        error = "No hay empresas configuradas o no tienes acceso a ninguna."

    try:
        if empresa:
            proveedores = obtener_proveedores(empresa)
    except AS400ApiError as e:
        error = str(e)

    status = 500 if error and not proveedores else 200

    return render_template(
        "pedido.html",
        proveedores=proveedores,
        error=error,
        **contexto,
    ), status


@app.route("/api/articulos")
def api_articulos():
    proveedor_codigo = request.args.get("proveedor", "").strip()
    fechaAnalisis = request.args.get("fechaAnalisis", "").strip()

    if not proveedor_codigo:
        return jsonify({
            "success": False,
            "mensaje": "Seleccione un proveedor"
        }), 400

    empresa = ensure_empresa_session(session.get("usuario"))

    if not empresa:
        return jsonify({
            "success": False,
            "mensaje": "No hay empresa seleccionada"
        }), 400

    try:
        articulos = obtener_articulos(empresa, proveedor_codigo, fechaAnalisis)

        return jsonify({
            "success": True,
            "articulos": articulos
        })

    except AS400ApiError as e:
        return jsonify({
            "success": False,
            "mensaje": str(e)
        }), 500


@app.route("/api/articulos/<codigo>/stocks")
def api_articulos_stocks(codigo):
    empresa = ensure_empresa_session(session.get("usuario"))

    if not empresa:
        return jsonify({
            "success": False,
            "mensaje": "No hay empresa seleccionada"
        }), 400

    try:
        almacenes = obtener_stocks(empresa, codigo)

        return jsonify({
            "success": True,
            "almacenes": almacenes
        })

    except AS400ApiError as e:
        return jsonify({
            "success": False,
            "mensaje": str(e)
        }), 500


@app.route("/api/pedido/confirmar", methods=["POST"])
def confirmar_pedido():
    data = request.get_json(silent=True)

    if not data:
        return jsonify({
            "success": False,
            "mensaje": "No se recibieron datos"
        }), 400

    proveedor_codigo = data.get("proveedor")
    lineas = data.get("lineas", [])

    if not proveedor_codigo:
        return jsonify({
            "success": False,
            "mensaje": "Seleccione un proveedor"
        }), 400

    if not lineas:
        return jsonify({
            "success": False,
            "mensaje": "El pedido está vacío"
        }), 400

    try:
        carrito = []

        for linea in lineas:
            codigo_articulo = str(linea.get("codigo_articulo", "")).strip()
            cantidad = float(linea.get("cantidad", 0))
            codigoUm = int(linea.get("codigoUm", 0))

            if not codigo_articulo:
                return jsonify({
                    "success": False,
                    "mensaje": "Hay una línea sin código de artículo"
                }), 400

            if cantidad <= 0:
                return jsonify({
                    "success": False,
                    "mensaje": f"Cantidad no válida para el artículo {codigo_articulo}"
                }), 400

            carrito.append({
                "codigo": codigo_articulo,
                "cantidad": cantidad,
                "codigoUm": codigoUm
            })
        usuario = session.get("usuario")
        empresa = ensure_empresa_session(usuario)

        if not empresa:
            return jsonify({
                "success": False,
                "mensaje": "No hay empresa seleccionada"
            }), 400

        resultado = crear_pedido(empresa, proveedor_codigo, usuario, carrito)

        return jsonify(resultado)

    except AS400ApiError as e:
        return jsonify({
            "success": False,
            "mensaje": str(e)
        }), 500

    except ValueError:
        return jsonify({
            "success": False,
            "mensaje": "Alguna cantidad no tiene formato numérico válido"
        }), 400

    except Exception as e:
        mensaje = str(e) if app.config.get("DEBUG") else "Error inesperado al confirmar el pedido"

        return jsonify({
            "success": False,
            "mensaje": mensaje
        }), 500


if __name__ == "__main__":
    app.run(
        debug=app.config["DEBUG"],
        host=app.config["HOST"],
        port=app.config["PORT"],
    )