from flask import Flask, render_template, request, jsonify, redirect, url_for
from config import Config
from as400_api import obtener_articulos, crear_pedido, AS400ApiError, obtener_proveedores

app = Flask(__name__)
app.config.from_object(Config)


@app.route("/")
def index():
    return redirect(url_for("pedido"))


@app.route("/pedido")
def pedido():
    error = None
    proveedores = []

    try:
        proveedores = obtener_proveedores()
    except AS400ApiError as e:
        error = str(e)

    status = 500 if error and not proveedores else 200

    return render_template(
        "pedido.html",
        proveedores=proveedores,
        error=error
    ), status


@app.route("/api/articulos")
def api_articulos():
    proveedor_codigo = request.args.get("proveedor", "").strip()

    if not proveedor_codigo:
        return jsonify({
            "success": False,
            "mensaje": "Seleccione un proveedor"
        }), 400

    try:
        articulos = obtener_articulos(proveedor_codigo)

        return jsonify({
            "success": True,
            "articulos": articulos
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

        resultado = crear_pedido(proveedor_codigo, carrito)

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