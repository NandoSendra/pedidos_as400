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
    APP_ASIENTOS_EJEMPLOS_FILE = os.getenv(
        "APP_ASIENTOS_EJEMPLOS_FILE",
        "asientos_ejemplos.json",
    )
    APP_HISTORIAL_FILE = os.getenv(
        "APP_HISTORIAL_FILE",
        "historial_operaciones.json",
    )

    # Compatibilidad: si no existe users.json, se usa un único usuario del .env
    APP_LOGIN_USER = os.getenv("APP_LOGIN_USER", "admin")
    APP_LOGIN_PASSWORD = os.getenv("APP_LOGIN_PASSWORD", "")

    AS400_API_BASE_URL = os.getenv("AS400_API_BASE_URL")
    AS400_API_USER = os.getenv("AS400_API_USER")
    AS400_API_PASSWORD = os.getenv("AS400_API_PASSWORD")
    AS400_CONTABILIDAD_BASE_URL = os.getenv("AS400_CONTABILIDAD_BASE_URL")

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    AI_ASIENTO_ENABLED = _env_bool("AI_ASIENTO_ENABLED", False)
    AI_ASIENTO_REGLAS = os.getenv("AI_ASIENTO_REGLAS", "")
    AI_ASIENTO_PROVIDER = os.getenv("AI_ASIENTO_PROVIDER", "openai").strip().lower()
    AI_ASIENTO_BASE_URL = os.getenv(
        "AI_ASIENTO_BASE_URL", "http://localhost:11434/v1"
    ).strip().rstrip("/")
    AI_ASIENTO_API_KEY = os.getenv("AI_ASIENTO_API_KEY", "")
    AI_ASIENTO_MODEL = os.getenv("AI_ASIENTO_MODEL", "")
    AI_ASIENTO_TIMEOUT = int(os.getenv("AI_ASIENTO_TIMEOUT", "120"))
