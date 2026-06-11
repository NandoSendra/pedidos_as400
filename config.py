import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


def _env_bool(name, default=False):
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in ("1", "true", "yes", "on")


class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")
    DEBUG = _env_bool("FLASK_DEBUG", False)
    HOST = os.getenv("FLASK_HOST", "0.0.0.0")
    PORT = int(os.getenv("FLASK_PORT", "5100"))
    PERMANENT_SESSION_LIFETIME = timedelta(
        hours=int(os.getenv("APP_SESSION_HOURS", "8"))
    )

    APP_USERS_FILE = os.getenv("APP_USERS_FILE", "users.json")
    APP_EMPRESAS_FILE = os.getenv("APP_EMPRESAS_FILE", "empresas.json")

    # Compatibilidad: si no existe users.json, se usa un único usuario del .env
    APP_LOGIN_USER = os.getenv("APP_LOGIN_USER", "admin")
    APP_LOGIN_PASSWORD = os.getenv("APP_LOGIN_PASSWORD", "")

    AS400_API_BASE_URL = os.getenv("AS400_API_BASE_URL")
    AS400_API_USER = os.getenv("AS400_API_USER")
    AS400_API_PASSWORD = os.getenv("AS400_API_PASSWORD")