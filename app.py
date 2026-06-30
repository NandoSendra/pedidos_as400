import csv
import io
from datetime import date, datetime

from flask import Flask, Response, render_template, request, jsonify, redirect, url_for, session
from config import Config
from cuentas_cache import (
    buscar_cuentas_contables,
    get_cuentas_cache_info,
    get_cuentas_contables,
)
from cuenta_tipos import resolver_codigo_cuenta
from historial_store import (
    ESTADO_ERROR,
    ESTADO_OK,
    ESTADO_PROCESANDO,
    completar_operacion,
    crear_o_recuperar_operacion,
    get_operacion,
    list_operaciones,
    nueva_idempotency_key,
    normalizar_idempotency_key,
)
from asientos_ejemplos_store import (
    AsientosEjemplosError,
    actualizar_ejemplo,
    borrar_ejemplo,
    contar_ejemplos,
    get_ejemplo,
    guardar_ejemplo,
    list_ejemplos_por_empresa,
)
from ai_asiento import (
    AIAsientoError,
    _detectar_tipo_operacion,
    _validar_lineas_sugeridas,
    ai_asiento_disponible,
    ai_asiento_info,
    intentar_asiento_norma43_rapida,
    sugerir_asiento_contable,
)
from csv_asiento import CSVAsientoError, parsear_archivo_importacion
from as400_api import (
    AS400ApiError,
    crear_asiento_contable,
    crear_pedido,
    get_as400_status,
    obtener_articulos,
    obtener_proveedores,
    obtener_stocks,
    normalizar_fecha_asiento,
    normalizar_debe_haber,
)
from auth import admin_required, init_auth, safe_next_url
from empresa_session import clear_empresa_session, ensure_empresa_session, set_empresa_session
from empresas_store import get_empresa, list_empresas_public
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
    user_can_access_empresa,
    verify_login,
)

app = Flask(__name__)
app.config.from_object(Config)
init_auth(app)


@app.route("/")
def index():
    contexto = _empresa_context()
    return render_template("dashboard.html", error=None, **contexto)


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


def _empresa_context():
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


def _as400_status_payload(empresa=None):
    estado = get_as400_status()
    estado["cache_cuentas"] = get_cuentas_cache_info(empresa) if empresa else None
    return estado


def _idempotency_key(data):
    key = (
        (data or {}).get("idempotency_key")
        or request.headers.get("Idempotency-Key")
    )
    return normalizar_idempotency_key(key) or nueva_idempotency_key()


def _respuesta_operacion_existente(operacion):
    if operacion.get("estado") == ESTADO_PROCESANDO:
        return {
            "success": False,
            "mensaje": "Esta operación ya se está procesando. Espera unos segundos antes de reintentar.",
            "historial_id": operacion.get("id"),
            "idempotency_key": operacion.get("idempotency_key"),
            "duplicado": True,
        }, 409

    resultado = dict(operacion.get("resultado") or {})

    if not resultado:
        resultado = {
            "success": operacion.get("estado") == ESTADO_OK,
            "mensaje": operacion.get("mensaje") or operacion.get("error") or "Operación ya registrada",
        }

    resultado["historial_id"] = operacion.get("id")
    resultado["idempotency_key"] = operacion.get("idempotency_key")
    resultado["duplicado"] = True

    status = operacion.get("http_status")

    if not status:
        status = 200 if operacion.get("estado") == ESTADO_OK else 500

    return resultado, int(status)


def _respuesta_idempotency_conflict(operacion):
    return {
        "success": False,
        "mensaje": (
            "La clave de idempotencia ya se usó para otra operación. "
            "Vuelve a intentarlo desde la pantalla para generar una clave nueva."
        ),
        "historial_id": operacion.get("id"),
        "idempotency_key": operacion.get("idempotency_key"),
    }, 409


def _registrar_resultado_operacion(
    operacion,
    *,
    estado,
    body,
    status,
    numero="",
    mensaje="",
    error="",
):
    completar_operacion(
        operacion.get("id"),
        estado=estado,
        resultado=body,
        http_status=status,
        numero=numero,
        mensaje=mensaje,
        error=error,
    )


def _empresa_id(empresa):
    return str(empresa.get("id") or "default")


def _operacion_visible_para_usuario(operacion):
    if not auth_enabled():
        return True

    usuario = session.get("usuario")

    if not usuario:
        return False

    if session.get("es_admin"):
        return True

    empresa_id = str(operacion.get("empresa_id") or "").strip()

    if empresa_id and user_can_access_empresa(usuario, empresa_id):
        return True

    return operacion.get("usuario") == usuario


def _texto_busqueda_operacion(operacion):
    partes = [
        operacion.get("id"),
        operacion.get("tipo"),
        operacion.get("estado"),
        operacion.get("usuario"),
        operacion.get("empresa_id"),
        operacion.get("empresa_nombre"),
        operacion.get("proveedor_codigo"),
        operacion.get("proveedor_nombre"),
        operacion.get("numero"),
        operacion.get("mensaje"),
        operacion.get("error"),
    ]

    for linea in operacion.get("lineas") or []:
        if isinstance(linea, dict):
            partes.extend(str(valor) for valor in linea.values())

    return " ".join(str(parte or "") for parte in partes).lower()


def _historial_filtros_desde_request():
    return {
        "tipo": request.args.get("tipo", "").strip(),
        "estado": request.args.get("estado", "").strip(),
        "empresa_id": request.args.get("empresa_id", "").strip(),
        "usuario": request.args.get("usuario", "").strip(),
        "desde": request.args.get("desde", "").strip(),
        "hasta": request.args.get("hasta", "").strip(),
        "q": request.args.get("q", "").strip(),
    }


def _filtrar_operaciones_historial(filtros):
    operaciones = []
    texto = filtros.get("q", "").lower()

    for operacion in list_operaciones():
        if not _operacion_visible_para_usuario(operacion):
            continue

        if filtros.get("tipo") and operacion.get("tipo") != filtros["tipo"]:
            continue

        if filtros.get("estado") and operacion.get("estado") != filtros["estado"]:
            continue

        if filtros.get("empresa_id") and str(operacion.get("empresa_id")) != filtros["empresa_id"]:
            continue

        if filtros.get("usuario") and str(operacion.get("usuario")) != filtros["usuario"]:
            continue

        fecha = str(operacion.get("fecha_creacion") or "")[:10]

        if filtros.get("desde") and fecha < filtros["desde"]:
            continue

        if filtros.get("hasta") and fecha > filtros["hasta"]:
            continue

        if texto and texto not in _texto_busqueda_operacion(operacion):
            continue

        operaciones.append(operacion)

    return operaciones


def _operacion_o_404(operacion_id):
    operacion = get_operacion(operacion_id)

    if not operacion or not _operacion_visible_para_usuario(operacion):
        return None

    return operacion


def _preparar_lineas_pedido(lineas):
    if not lineas:
        raise ValueError("El pedido está vacío")

    carrito = []
    lineas_historial = []

    for linea in lineas:
        codigo_articulo = str(linea.get("codigo_articulo", "")).strip()
        cantidad = float(linea.get("cantidad", 0))
        codigo_um = int(linea.get("codigoUm", 0))

        if not codigo_articulo:
            raise ValueError("Hay una línea sin código de artículo")

        if cantidad <= 0:
            raise ValueError(f"Cantidad no válida para el artículo {codigo_articulo}")

        carrito.append({
            "codigo": codigo_articulo,
            "cantidad": cantidad,
            "codigoUm": codigo_um,
        })
        lineas_historial.append({
            "codigo_articulo": codigo_articulo,
            "descripcion": str(linea.get("descripcion", "")).strip(),
            "cantidad": cantidad,
            "codigoUm": codigo_um,
            "unidadMedida": str(linea.get("unidadMedida", "")).strip(),
            "precio": linea.get("precio", ""),
        })

    return carrito, lineas_historial


def _confirmar_pedido_data(data, origen_reintento_id=None):
    if not data:
        return {"success": False, "mensaje": "No se recibieron datos"}, 400

    proveedor_codigo = str(data.get("proveedor", "")).strip()

    if not proveedor_codigo:
        return {"success": False, "mensaje": "Seleccione un proveedor"}, 400

    try:
        carrito, lineas_historial = _preparar_lineas_pedido(data.get("lineas", []))
    except ValueError as error:
        return {"success": False, "mensaje": str(error)}, 400

    usuario = session.get("usuario")
    empresa = ensure_empresa_session(usuario)

    if not empresa:
        return {"success": False, "mensaje": "No hay empresa seleccionada"}, 400

    idempotency_key = _idempotency_key(data)
    payload_historial = {
        "proveedor": proveedor_codigo,
        "proveedor_nombre": str(data.get("proveedor_nombre", "")).strip(),
        "lineas": lineas_historial,
    }
    estado, operacion = crear_o_recuperar_operacion(
        tipo="pedido",
        idempotency_key=idempotency_key,
        usuario=usuario,
        empresa=empresa,
        payload=payload_historial,
        lineas=lineas_historial,
        proveedor_codigo=proveedor_codigo,
        proveedor_nombre=payload_historial["proveedor_nombre"],
        fecha_operacion=str(data.get("fecha", "")).strip(),
        origen_reintento_id=origen_reintento_id,
    )

    if estado == "conflicto":
        return _respuesta_idempotency_conflict(operacion)

    if estado == "existente":
        return _respuesta_operacion_existente(operacion)

    try:
        resultado = crear_pedido(empresa, proveedor_codigo, usuario, carrito)
        body = dict(resultado)
        body["historial_id"] = operacion.get("id")
        body["idempotency_key"] = idempotency_key
        _registrar_resultado_operacion(
            operacion,
            estado=ESTADO_OK,
            body=body,
            status=200,
            numero=resultado.get("numero_pedido"),
            mensaje=resultado.get("mensaje", "Pedido creado correctamente"),
        )
        return body, 200
    except AS400ApiError as error:
        body = {
            "success": False,
            "mensaje": str(error),
            "historial_id": operacion.get("id"),
            "idempotency_key": idempotency_key,
        }
        _registrar_resultado_operacion(
            operacion,
            estado=ESTADO_ERROR,
            body=body,
            status=500,
            error=str(error),
        )
        return body, 500
    except ValueError as error:
        body = {
            "success": False,
            "mensaje": str(error),
            "historial_id": operacion.get("id"),
            "idempotency_key": idempotency_key,
        }
        _registrar_resultado_operacion(
            operacion,
            estado=ESTADO_ERROR,
            body=body,
            status=400,
            error=str(error),
        )
        return body, 400
    except Exception as error:
        mensaje = str(error) if app.config.get("DEBUG") else "Error inesperado al confirmar el pedido"
        body = {
            "success": False,
            "mensaje": mensaje,
            "historial_id": operacion.get("id"),
            "idempotency_key": idempotency_key,
        }
        _registrar_resultado_operacion(
            operacion,
            estado=ESTADO_ERROR,
            body=body,
            status=500,
            error=mensaje,
        )
        return body, 500


def _indexar_cuentas_por_codigo(cuentas_plan):
    return {
        str(cuenta.get("codigo", "")).strip(): cuenta
        for cuenta in cuentas_plan
        if str(cuenta.get("codigo", "")).strip()
    }


def _resolver_cuenta_plan_estricta(valor, cuentas_plan, cuentas_por_codigo):
    cuenta = resolver_codigo_cuenta(valor, cuentas_plan)

    if cuenta and cuenta in cuentas_por_codigo:
        return cuenta

    return ""


def _lado_habitual_cuenta(cuenta):
    if cuenta.get("debe_haber_habitual"):
        return cuenta.get("debe_haber_habitual")

    tipo = cuenta.get("tipo")
    mapa = {
        "cliente": "D",
        "proveedor": "H",
        "ventas": "H",
        "compra_gasto": "D",
        "servicios": "D",
        "otros_gastos": "D",
        "iva_soportado": "D",
        "iva_repercutido": "H",
        "empleado": "H",
        "gastos_personal": "D",
        "ss_empresa": "D",
        "irpf": "H",
        "ss_acreedora": "H",
    }

    return mapa.get(tipo)


def _fecha_asiento_date(fecha):
    texto = str(fecha or "").strip().replace("-", "")

    if len(texto) != 8 or not texto.isdigit():
        return None

    try:
        return datetime.strptime(texto, "%Y%m%d").date()
    except ValueError:
        return None


def _advertencias_asiento(lineas, cuentas_por_codigo):
    avisos = []
    hoy = date.today()

    for indice, linea in enumerate(lineas, start=1):
        codigo = str(linea.get("cuenta", "")).strip()
        cuenta = cuentas_por_codigo.get(codigo) or {}
        prefijo = f"Línea {indice} ({codigo})"
        tipo = cuenta.get("tipo")
        lado = linea.get("debe_haber")

        if cuenta.get("activa") is False:
            avisos.append(f"{prefijo}: la cuenta está marcada como inactiva.")

        if cuenta.get("generica") or cuenta.get("subtipo") == "generica":
            avisos.append(f"{prefijo}: la cuenta parece genérica; revisa si hay una cuenta específica.")

        if tipo == "iva_repercutido" and lado != "H":
            avisos.append(f"{prefijo}: IVA repercutido normalmente va al Haber.")

        if tipo == "iva_soportado" and lado != "D":
            avisos.append(f"{prefijo}: IVA soportado normalmente va al Debe.")

        lado_habitual = _lado_habitual_cuenta(cuenta)

        if lado_habitual and lado != lado_habitual:
            etiqueta = "Debe" if lado_habitual == "D" else "Haber"
            avisos.append(f"{prefijo}: lado poco habitual; esta cuenta suele ir al {etiqueta}.")

        fecha_linea = _fecha_asiento_date(linea.get("fecha"))

        if fecha_linea:
            if fecha_linea > hoy:
                avisos.append(f"{prefijo}: fecha futura.")
            elif fecha_linea.year != hoy.year:
                avisos.append(f"{prefijo}: fecha fuera del ejercicio actual {hoy.year}.")

    return avisos[:12]


def _normalizar_lineas_asiento_para_confirmar(data, empresa):
    lineas = data.get("lineas", [])

    if not lineas:
        raise ValueError("El asiento está vacío")

    lineas_con_datos = []

    for linea in lineas:
        try:
            importe = float(linea.get("importe", 0) or 0)
        except (TypeError, ValueError):
            importe = 0

        if (
            str(linea.get("cuenta", "")).strip()
            or str(linea.get("concepto", "")).strip()
            or importe > 0
        ):
            lineas_con_datos.append(linea)

    if not lineas_con_datos:
        raise ValueError("El asiento no tiene líneas válidas")

    cuentas_plan = get_cuentas_contables(empresa, refresh=False)
    cuentas_por_codigo = _indexar_cuentas_por_codigo(cuentas_plan)
    asiento_lineas = []
    total_debe = 0.0
    total_haber = 0.0

    for indice, linea in enumerate(lineas_con_datos, start=1):
        cuenta = _resolver_cuenta_plan_estricta(
            linea.get("cuenta", ""),
            cuentas_plan,
            cuentas_por_codigo,
        )
        concepto = str(linea.get("concepto", "")).strip()
        fecha = normalizar_fecha_asiento(linea.get("fecha", ""))
        importe = float(linea.get("importe", 0))
        debe_haber = normalizar_debe_haber(linea.get("debe_haber", ""))

        if not cuenta:
            raise ValueError(f"La línea {indice} no tiene una cuenta contable válida en el plan")

        if not concepto:
            raise ValueError(f"La línea {indice} no tiene concepto")

        if importe <= 0:
            raise ValueError(f"El importe de la línea {indice} debe ser mayor que 0 €")

        if debe_haber == "D":
            total_debe += importe
        else:
            total_haber += importe

        asiento_lineas.append({
            "cuenta": cuenta,
            "fecha": fecha,
            "importe": importe,
            "debe_haber": debe_haber,
            "concepto": concepto,
        })

    if round(total_debe, 2) != round(total_haber, 2):
        raise ValueError(
            "El asiento no cuadra: "
            f"debe {total_debe:.2f} €, haber {total_haber:.2f} €"
        )

    return asiento_lineas, _advertencias_asiento(asiento_lineas, cuentas_por_codigo)


def _confirmar_asiento_data(data, origen_reintento_id=None):
    if not data:
        return {"success": False, "mensaje": "No se recibieron datos"}, 400

    usuario = session.get("usuario")
    empresa = ensure_empresa_session(usuario)

    if not empresa:
        return {"success": False, "mensaje": "No hay empresa seleccionada"}, 400

    try:
        asiento_lineas, advertencias = _normalizar_lineas_asiento_para_confirmar(data, empresa)
    except ValueError as error:
        return {"success": False, "mensaje": str(error)}, 400
    except AS400ApiError as error:
        return {"success": False, "mensaje": str(error)}, 500

    idempotency_key = _idempotency_key(data)
    payload_historial = {
        "lineas": asiento_lineas,
        "guardar_ejemplo": bool(data.get("guardar_ejemplo")),
        "descripcion_ejemplo": str(data.get("descripcion_ejemplo", "")).strip(),
        "advertencias": advertencias,
    }
    fecha_operacion = asiento_lineas[0]["fecha"] if asiento_lineas else ""
    estado, operacion = crear_o_recuperar_operacion(
        tipo="asiento",
        idempotency_key=idempotency_key,
        usuario=usuario,
        empresa=empresa,
        payload=payload_historial,
        lineas=asiento_lineas,
        fecha_operacion=fecha_operacion,
        origen_reintento_id=origen_reintento_id,
    )

    if estado == "conflicto":
        return _respuesta_idempotency_conflict(operacion)

    if estado == "existente":
        return _respuesta_operacion_existente(operacion)

    try:
        resultado = crear_asiento_contable(empresa, usuario, asiento_lineas)
        body = dict(resultado)
        body["historial_id"] = operacion.get("id")
        body["idempotency_key"] = idempotency_key
        body["advertencias"] = advertencias

        if data.get("guardar_ejemplo"):
            try:
                ejemplo = _guardar_ejemplo_desde_lineas(
                    empresa,
                    str(data.get("descripcion_ejemplo", "")).strip(),
                    asiento_lineas,
                    usuario,
                )
                body["ejemplo_guardado"] = True
                body["num_ejemplos_ia"] = contar_ejemplos(_empresa_id(empresa))
                body["ejemplo_id"] = ejemplo.get("id")
            except AsientosEjemplosError as error:
                body["ejemplo_guardado"] = False
                body["aviso_ejemplo"] = str(error)

        _registrar_resultado_operacion(
            operacion,
            estado=ESTADO_OK,
            body=body,
            status=200,
            numero=resultado.get("numero_asiento"),
            mensaje=resultado.get("mensaje", "Asiento creado correctamente"),
        )
        return body, 200
    except AS400ApiError as error:
        body = {
            "success": False,
            "mensaje": str(error),
            "historial_id": operacion.get("id"),
            "idempotency_key": idempotency_key,
        }
        _registrar_resultado_operacion(
            operacion,
            estado=ESTADO_ERROR,
            body=body,
            status=500,
            error=str(error),
        )
        return body, 500
    except ValueError as error:
        body = {
            "success": False,
            "mensaje": str(error),
            "historial_id": operacion.get("id"),
            "idempotency_key": idempotency_key,
        }
        _registrar_resultado_operacion(
            operacion,
            estado=ESTADO_ERROR,
            body=body,
            status=400,
            error=str(error),
        )
        return body, 400
    except Exception as error:
        mensaje = (
            str(error) if app.config.get("DEBUG")
            else "Error inesperado al confirmar el asiento"
        )
        body = {
            "success": False,
            "mensaje": mensaje,
            "historial_id": operacion.get("id"),
            "idempotency_key": idempotency_key,
        }
        _registrar_resultado_operacion(
            operacion,
            estado=ESTADO_ERROR,
            body=body,
            status=500,
            error=mensaje,
        )
        return body, 500


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


@app.route("/estado-as400")
def estado_as400():
    contexto = _empresa_context()
    empresa = ensure_empresa_session(session.get("usuario"))

    return render_template(
        "estado_as400.html",
        estado=_as400_status_payload(empresa),
        error=None if empresa else "No hay empresa seleccionada.",
        **contexto,
    )


@app.route("/api/estado-as400")
def api_estado_as400():
    empresa = ensure_empresa_session(session.get("usuario"))

    return jsonify({
        "success": True,
        "estado": _as400_status_payload(empresa),
    })


@app.route("/api/estado-as400/probar", methods=["POST"])
def api_estado_as400_probar():
    empresa = ensure_empresa_session(session.get("usuario"))

    if not empresa:
        return jsonify({
            "success": False,
            "mensaje": "No hay empresa seleccionada",
            "estado": _as400_status_payload(None),
        }), 400

    resultados = {}

    try:
        proveedores = obtener_proveedores(empresa)
        resultados["pedidos"] = {
            "success": True,
            "mensaje": f"{len(proveedores)} proveedor(es) recibidos",
        }
    except AS400ApiError as error:
        resultados["pedidos"] = {
            "success": False,
            "mensaje": str(error),
        }

    try:
        cuentas = get_cuentas_contables(empresa, refresh=True)
        resultados["contabilidad"] = {
            "success": True,
            "mensaje": f"{len(cuentas)} cuenta(s) recibidas",
        }
    except AS400ApiError as error:
        resultados["contabilidad"] = {
            "success": False,
            "mensaje": str(error),
        }

    ok = all(resultado["success"] for resultado in resultados.values())

    return jsonify({
        "success": ok,
        "resultados": resultados,
        "estado": _as400_status_payload(empresa),
    }), 200 if ok else 502


@app.route("/historial")
def historial():
    filtros = _historial_filtros_desde_request()
    operaciones = _filtrar_operaciones_historial(filtros)
    query_string = request.query_string.decode("utf-8")

    return render_template(
        "historial.html",
        operaciones=operaciones[:300],
        total_operaciones=len(operaciones),
        filtros=filtros,
        query_string=query_string,
        **_empresa_context(),
    )


@app.route("/historial/export")
def historial_export():
    filtros = _historial_filtros_desde_request()
    operaciones = _filtrar_operaciones_historial(filtros)
    salida = io.StringIO()
    writer = csv.writer(salida, delimiter=";")
    writer.writerow([
        "id",
        "tipo",
        "estado",
        "fecha_creacion",
        "fecha_operacion",
        "usuario",
        "empresa_id",
        "empresa_nombre",
        "proveedor_codigo",
        "proveedor_nombre",
        "numero",
        "mensaje",
        "error",
        "num_lineas",
    ])

    for operacion in operaciones:
        writer.writerow([
            operacion.get("id", ""),
            operacion.get("tipo", ""),
            operacion.get("estado", ""),
            operacion.get("fecha_creacion", ""),
            operacion.get("fecha_operacion", ""),
            operacion.get("usuario", ""),
            operacion.get("empresa_id", ""),
            operacion.get("empresa_nombre", ""),
            operacion.get("proveedor_codigo", ""),
            operacion.get("proveedor_nombre", ""),
            operacion.get("numero", ""),
            operacion.get("mensaje", ""),
            operacion.get("error", ""),
            len(operacion.get("lineas") or []),
        ])

    return Response(
        salida.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=historial_operaciones.csv"
        },
    )


@app.route("/historial/<operacion_id>")
def historial_detalle(operacion_id):
    operacion = _operacion_o_404(operacion_id)

    if not operacion:
        return redirect(url_for("historial"))

    return render_template(
        "historial_detalle.html",
        operacion=operacion,
        **_empresa_context(),
    )


@app.route("/api/historial/<operacion_id>/reintentar", methods=["POST"])
def api_historial_reintentar(operacion_id):
    operacion = _operacion_o_404(operacion_id)

    if not operacion:
        return jsonify({
            "success": False,
            "mensaje": "Operación no encontrada",
        }), 404

    if operacion.get("estado") != ESTADO_ERROR:
        return jsonify({
            "success": False,
            "mensaje": "Solo se pueden reintentar operaciones fallidas",
        }), 400

    empresa_id = str(operacion.get("empresa_id") or "").strip()
    empresa = get_empresa(empresa_id)

    if not empresa:
        return jsonify({
            "success": False,
            "mensaje": "La empresa de la operación ya no está disponible",
        }), 400

    usuario = session.get("usuario")

    try:
        set_empresa_session(usuario, empresa_id)
    except ValueError as error:
        return jsonify({
            "success": False,
            "mensaje": str(error),
        }), 400

    payload = dict(operacion.get("payload") or {})
    payload["idempotency_key"] = nueva_idempotency_key()

    if operacion.get("tipo") == "pedido":
        body, status = _confirmar_pedido_data(
            payload,
            origen_reintento_id=operacion.get("id"),
        )
        return jsonify(body), status

    if operacion.get("tipo") == "asiento":
        body, status = _confirmar_asiento_data(
            payload,
            origen_reintento_id=operacion.get("id"),
        )
        return jsonify(body), status

    return jsonify({
        "success": False,
        "mensaje": "Tipo de operación no soportado",
    }), 400


@app.route("/pedido")
def pedido():
    error = None
    proveedores = []
    contexto = _empresa_context()
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
    body, status = _confirmar_pedido_data(request.get_json(silent=True))
    return jsonify(body), status


@app.route("/asiento")
def asiento():
    contexto = _empresa_context()
    empresa = ensure_empresa_session(session.get("usuario"))
    error = None

    if not empresa:
        error = "No hay empresas configuradas o no tienes acceso a ninguna."

    num_ejemplos_ia = 0

    if empresa and ai_asiento_disponible():
        num_ejemplos_ia = contar_ejemplos(str(empresa.get("id") or "default"))

    return render_template(
        "asiento.html",
        ai_disponible=ai_asiento_disponible(),
        ai_info=ai_asiento_info() if ai_asiento_disponible() else None,
        num_ejemplos_ia=num_ejemplos_ia,
        error=error,
        **contexto,
    )


@app.route("/api/asiento/sugerir", methods=["POST"])
def api_asiento_sugerir():
    if not ai_asiento_disponible():
        return jsonify({
            "success": False,
            "mensaje": "El asistente de IA no está configurado",
        }), 503

    data = request.get_json(silent=True) or {}
    descripcion = str(data.get("descripcion", "")).strip()
    fecha = str(data.get("fecha", "")).strip() or None
    lineas_actuales = data.get("lineas_actuales", [])

    empresa = ensure_empresa_session(session.get("usuario"))

    if not empresa:
        return jsonify({
            "success": False,
            "mensaje": "No hay empresa seleccionada",
        }), 400

    try:
        cuentas = get_cuentas_contables(
            empresa,
            refresh=bool(request.args.get("refresh")),
        )
        resultado = sugerir_asiento_contable(
            descripcion,
            cuentas,
            fecha=fecha,
            lineas_actuales=lineas_actuales,
            empresa_id=empresa.get("id"),
        )
        return jsonify(resultado)
    except AIAsientoError as error:
        return jsonify({
            "success": False,
            "mensaje": str(error),
        }), 400
    except AS400ApiError as error:
        return jsonify({
            "success": False,
            "mensaje": str(error),
        }), 500


@app.route("/api/asiento/validar", methods=["POST"])
def api_asiento_validar():
    empresa = ensure_empresa_session(session.get("usuario"))

    if not empresa:
        return jsonify({
            "success": False,
            "mensaje": "No hay empresa seleccionada",
        }), 400

    data = request.get_json(silent=True) or {}

    try:
        lineas, advertencias = _normalizar_lineas_asiento_para_confirmar(data, empresa)
        return jsonify({
            "success": True,
            "lineas": lineas,
            "advertencias": advertencias,
        })
    except ValueError as error:
        return jsonify({
            "success": False,
            "mensaje": str(error),
        }), 400
    except AS400ApiError as error:
        return jsonify({
            "success": False,
            "mensaje": str(error),
        }), 500


@app.route("/api/asiento/importar-csv", methods=["POST"])
def api_asiento_importar_csv():
    empresa = ensure_empresa_session(session.get("usuario"))

    if not empresa:
        return jsonify({
            "success": False,
            "mensaje": "No hay empresa seleccionada",
        }), 400

    archivo = request.files.get("archivo")

    if not archivo or not archivo.filename:
        return jsonify({
            "success": False,
            "mensaje": "No se ha adjuntado ningún archivo",
        }), 400

    nombre_archivo = archivo.filename.lower()
    extensiones_validas = (
        ".csv", ".tsv", ".txt", ".dat", ".tab",
        ".xlsx", ".xlsm", ".xls",
        ".n43", ".c43", ".csb", ".43",
    )

    if not nombre_archivo.endswith(extensiones_validas):
        return jsonify({
            "success": False,
            "mensaje": (
                "Formato no soportado. Usa un fichero encolumnado "
                "(CSV, Excel, TSV), Norma 43 (.n43, .43) o similar."
            ),
        }), 400

    modo = str(request.form.get("modo", "lineas")).strip().lower()
    descripcion_extra = str(request.form.get("descripcion", "")).strip()
    fecha = str(request.form.get("fecha", "")).strip() or None
    cuenta_banco = str(request.form.get("cuenta_banco", "")).strip() or None

    try:
        contenido = archivo.read()
        cuentas_plan = None

        if modo == "lineas" or cuenta_banco:
            cuentas_plan = get_cuentas_contables(
                empresa,
                refresh=bool(request.args.get("refresh")),
            )

        resultado = parsear_archivo_importacion(
            contenido,
            filename=archivo.filename,
            cuenta_banco=cuenta_banco,
            cuentas_plan=cuentas_plan,
        )

        if modo == "ia":
            if not ai_asiento_disponible():
                return jsonify({
                    "success": False,
                    "mensaje": "El asistente de IA no está configurado",
                }), 503

            descripcion = descripcion_extra

            if resultado["resumen"]:
                descripcion = (
                    f"{descripcion_extra}\n\n{resultado['resumen']}".strip()
                    if descripcion_extra
                    else resultado["resumen"]
                )

            if len(descripcion) < 10:
                return jsonify({
                    "success": False,
                    "mensaje": (
                        "Añade una descripción de la operación o un archivo "
                        "con datos reconocibles"
                    ),
                }), 400

            cuentas = get_cuentas_contables(
                empresa,
                refresh=bool(request.args.get("refresh")),
            )

            if resultado.get("formato") == "norma43":
                rapida_norma43 = intentar_asiento_norma43_rapida(
                    resultado.get("movimientos") or [],
                    cuentas,
                    resultado.get("cuenta_banco"),
                    fecha=fecha,
                )

                if rapida_norma43:
                    lineas = _validar_lineas_sugeridas(
                        rapida_norma43["lineas"],
                        cuentas,
                        fecha,
                    )

                    return jsonify({
                        "success": True,
                        "modo": "reemplazar",
                        "formato": "norma43",
                        "num_filas": resultado["num_filas"],
                        "encabezados": resultado["encabezados"],
                        "delimitador": resultado.get("delimitador"),
                        "diagnostico": resultado.get("diagnostico"),
                        "explicacion": rapida_norma43["explicacion"],
                        "lineas": lineas,
                        "cuentas_candidatas": 0,
                        "tipos_operacion": rapida_norma43.get("tipos_operacion", []),
                    })

            sugerencia = sugerir_asiento_contable(
                descripcion,
                cuentas,
                fecha=fecha,
            )

            return jsonify({
                "success": True,
                "modo": "ia",
                "formato": resultado.get("formato", "csv"),
                "num_filas": resultado["num_filas"],
                "encabezados": resultado["encabezados"],
                "delimitador": resultado.get("delimitador"),
                "diagnostico": resultado.get("diagnostico"),
                **sugerencia,
            })

        if resultado["modo"] != "lineas":
            mensaje = (
                "El archivo no tiene columnas reconocibles para un asiento. "
                "Campos mínimos: cuenta + importe + debe/haber "
                "(o columnas debe y haber). También puedes analizarlo con IA."
            )

            if resultado.get("formato") == "norma43":
                mensaje = (
                    "No se pudo identificar la cuenta contable del banco (572). "
                    "Indica la cuenta bancaria en el campo opcional o usa "
                    "«Analizar con IA» para contabilizar los movimientos."
                )
            elif resultado.get("motivo") == "sin_lineas_validas":
                mensaje = (
                    "No se pudo cargar ninguna línea válida. "
                    "Revisa el informe de importación."
                )

            return jsonify({
                "success": False,
                "mensaje": mensaje,
                "modo": resultado["modo"],
                "formato": resultado.get("formato"),
                "num_filas": resultado["num_filas"],
                "encabezados": resultado["encabezados"],
                "diagnostico": resultado.get("diagnostico"),
            }), 400

        return jsonify({
            "success": True,
            "modo": "lineas",
            "formato": resultado.get("formato", "csv"),
            "lineas": resultado["lineas"],
            "num_filas": resultado["num_filas"],
            "encabezados": resultado["encabezados"],
            "delimitador": resultado.get("delimitador"),
            "cuenta_banco": resultado.get("cuenta_banco"),
            "diagnostico": resultado.get("diagnostico"),
        })
    except CSVAsientoError as error:
        return jsonify({
            "success": False,
            "mensaje": str(error),
        }), 400
    except AIAsientoError as error:
        return jsonify({
            "success": False,
            "mensaje": str(error),
        }), 400
    except AS400ApiError as error:
        return jsonify({
            "success": False,
            "mensaje": str(error),
        }), 500

def _guardar_ejemplo_desde_lineas(empresa, descripcion, lineas, usuario):
    tipos = _detectar_tipo_operacion(descripcion or "")

    return guardar_ejemplo(
        _empresa_id(empresa),
        descripcion,
        lineas,
        usuario=usuario,
        tipos_operacion=tipos,
    )


def _ejemplo_para_api(ejemplo):
    return {
        "id": ejemplo.get("id"),
        "empresa_id": ejemplo.get("empresa_id"),
        "descripcion": ejemplo.get("descripcion"),
        "lineas": ejemplo.get("lineas", []),
        "num_lineas": len(ejemplo.get("lineas", [])),
        "tipos_operacion": ejemplo.get("tipos_operacion", []),
        "usuario": ejemplo.get("usuario"),
        "activo": ejemplo.get("activo", True) is not False,
        "creado": ejemplo.get("creado"),
        "actualizado": ejemplo.get("actualizado"),
    }


@app.route("/asiento/ejemplos")
def asiento_ejemplos():
    contexto = _empresa_context()
    empresa = ensure_empresa_session(session.get("usuario"))
    ejemplos = []
    error = None

    if not empresa:
        error = "No hay empresa seleccionada."
    else:
        ejemplos = [
            _ejemplo_para_api(ejemplo)
            for ejemplo in list_ejemplos_por_empresa(
                _empresa_id(empresa),
                incluir_inactivos=True,
            )
        ]

    return render_template(
        "asiento_ejemplos.html",
        ejemplos=ejemplos,
        error=error,
        **contexto,
    )


@app.route("/api/asiento/ejemplos", methods=["GET", "POST"])
def api_asiento_ejemplos():
    empresa = ensure_empresa_session(session.get("usuario"))

    if not empresa:
        return jsonify({
            "success": False,
            "mensaje": "No hay empresa seleccionada",
        }), 400

    empresa_id = _empresa_id(empresa)

    if request.method == "GET":
        incluir_inactivos = request.args.get("incluir_inactivos") == "1"
        ejemplos = list_ejemplos_por_empresa(
            empresa_id,
            incluir_inactivos=incluir_inactivos,
        )

        return jsonify({
            "success": True,
            "num_ejemplos": len(ejemplos),
            "ejemplos": [
                _ejemplo_para_api(ejemplo)
                for ejemplo in ejemplos[:200]
            ],
        })

    data = request.get_json(silent=True) or {}
    descripcion = str(data.get("descripcion", "")).strip()
    lineas = data.get("lineas", [])

    try:
        ejemplo = _guardar_ejemplo_desde_lineas(
            empresa,
            descripcion,
            lineas,
            session.get("usuario"),
        )

        return jsonify({
            "success": True,
            "mensaje": "Ejemplo guardado para la IA",
            "ejemplo_id": ejemplo.get("id"),
            "num_ejemplos": contar_ejemplos(empresa_id),
        })
    except AsientosEjemplosError as error:
        return jsonify({
            "success": False,
            "mensaje": str(error),
        }), 400


@app.route("/api/asiento/ejemplos/<ejemplo_id>", methods=["GET", "PUT", "PATCH", "DELETE"])
def api_asiento_ejemplo_detalle(ejemplo_id):
    empresa = ensure_empresa_session(session.get("usuario"))

    if not empresa:
        return jsonify({
            "success": False,
            "mensaje": "No hay empresa seleccionada",
        }), 400

    empresa_id = _empresa_id(empresa)

    if request.method == "GET":
        ejemplo = get_ejemplo(empresa_id, ejemplo_id)

        if not ejemplo:
            return jsonify({
                "success": False,
                "mensaje": "Ejemplo no encontrado",
            }), 404

        return jsonify({
            "success": True,
            "ejemplo": _ejemplo_para_api(ejemplo),
        })

    if request.method == "DELETE":
        try:
            borrar_ejemplo(empresa_id, ejemplo_id)
            return jsonify({
                "success": True,
                "mensaje": "Ejemplo borrado",
                "num_ejemplos": contar_ejemplos(empresa_id),
            })
        except AsientosEjemplosError as error:
            return jsonify({
                "success": False,
                "mensaje": str(error),
            }), 404

    data = request.get_json(silent=True) or {}

    try:
        ejemplo = actualizar_ejemplo(
            empresa_id,
            ejemplo_id,
            descripcion=data.get("descripcion") if "descripcion" in data else None,
            lineas=data.get("lineas") if "lineas" in data else None,
            tipos_operacion=(
                data.get("tipos_operacion")
                if "tipos_operacion" in data
                else None
            ),
            activo=data.get("activo") if "activo" in data else None,
            usuario=session.get("usuario"),
        )

        return jsonify({
            "success": True,
            "mensaje": "Ejemplo actualizado",
            "ejemplo": _ejemplo_para_api(ejemplo),
            "num_ejemplos": contar_ejemplos(empresa_id),
        })
    except AsientosEjemplosError as error:
        return jsonify({
            "success": False,
            "mensaje": str(error),
        }), 400


@app.route("/api/cuentas")
def api_cuentas():
    empresa = ensure_empresa_session(session.get("usuario"))

    if not empresa:
        return jsonify({
            "success": False,
            "mensaje": "No hay empresa seleccionada"
        }), 400

    try:
        refresh = bool(request.args.get("refresh"))
        cuentas = get_cuentas_contables(empresa, refresh=refresh)

        if request.args.get("meta"):
            return jsonify({
                "success": True,
                "numCuentas": len(cuentas),
                "cache": not refresh,
            })

        return jsonify({
            "success": True,
            "cuentas": cuentas,
            "numCuentas": len(cuentas),
            "cache": not refresh,
        })
    except AS400ApiError as e:
        return jsonify({
            "success": False,
            "mensaje": str(e)
        }), 500


@app.route("/api/cuentas/buscar")
def api_cuentas_buscar():
    empresa = ensure_empresa_session(session.get("usuario"))

    if not empresa:
        return jsonify({
            "success": False,
            "mensaje": "No hay empresa seleccionada"
        }), 400

    texto = str(request.args.get("q", "")).strip()

    try:
        limite = int(request.args.get("limit", 40))
    except (TypeError, ValueError):
        limite = 40

    try:
        cuentas = buscar_cuentas_contables(
            empresa,
            texto,
            limit=limite,
        )

        return jsonify({
            "success": True,
            "cuentas": cuentas,
            "numCuentas": len(cuentas),
        })
    except AS400ApiError as e:
        return jsonify({
            "success": False,
            "mensaje": str(e)
        }), 500


@app.route("/api/asiento/confirmar", methods=["POST"])
def confirmar_asiento():
    body, status = _confirmar_asiento_data(request.get_json(silent=True))
    return jsonify(body), status


if __name__ == "__main__":
    app.run(
        debug=app.config["DEBUG"],
        host=app.config["HOST"],
        port=app.config["PORT"],
    )
