import os
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

    AS400_API_BASE_URL = os.getenv("AS400_API_BASE_URL")
    AS400_API_USER = os.getenv("AS400_API_USER")
    AS400_API_PASSWORD = os.getenv("AS400_API_PASSWORD")