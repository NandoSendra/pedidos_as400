from functools import wraps
from urllib.parse import urlparse

from flask import jsonify, redirect, request, session, url_for

from users_store import auth_enabled


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("usuario"):
            return redirect(url_for("login", next=request.path))

        if not session.get("es_admin"):
            return redirect(url_for("pedido"))

        return view(*args, **kwargs)

    return wrapped


def safe_next_url(url):
    if not url or not url.startswith("/") or url.startswith("//"):
        return url_for("pedido")

    parsed = urlparse(url)

    if parsed.netloc or parsed.scheme:
        return url_for("pedido")

    return url


def init_auth(app):
    @app.before_request
    def require_login():
        if not auth_enabled():
            return None

        if request.endpoint in (None, "login", "static"):
            return None

        if session.get("usuario"):
            return None

        if request.path.startswith("/api/"):
            return jsonify({
                "success": False,
                "mensaje": "No autorizado. Inicie sesión."
            }), 401

        return redirect(url_for("login", next=request.path))
