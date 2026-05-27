"""
Application configuration. Loads variables from .env via python-dotenv.

Copy .env.example to .env and set your values. Never commit .env to version control.
"""
import os
import warnings
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_GEMINI_MODEL = "gemini-2.0-flash-lite"
FALLBACK_GEMINI_MODEL = "gemini-2.0-flash"
DEPRECATED_GEMINI_MODELS = {
    "gemini-pro",
    "gemini-1.0-pro",
    "gemini-1.5-flash",
}

# Project root (directory containing config.py)
BASE_DIR = Path(__file__).resolve().parent

# Load .env from project root before reading any variables
load_dotenv(BASE_DIR / ".env")


def getenv(key: str, default=None):
    """Read an environment variable (stripped). Use for all secrets and config."""
    value = os.getenv(key, default)
    if isinstance(value, str):
        value = value.strip()
    return value


def getenv_int(key: str, default: int) -> int:
    raw = getenv(key)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        warnings.warn(f"Invalid integer for {key}={raw!r}; using default {default}.")
        return default


def getenv_bool(key: str, default: bool = False) -> bool:
    raw = getenv(key)
    if raw is None or raw == "":
        return default
    return raw.lower() in ("1", "true", "yes", "on")


def is_vercel() -> bool:
    """Return True when running inside Vercel serverless environment."""
    return bool(os.getenv("VERCEL"))


class Config:
    """Base configuration — all values from environment with safe defaults."""

    SECRET_KEY = getenv("SECRET_KEY") or "dev-change-me-in-production"

    # Vercel filesystem is read-only except /tmp.
    # Therefore SQLite must be stored in /tmp on Vercel.
    SQLALCHEMY_DATABASE_URI = getenv("DATABASE_URL") or (
        "sqlite:////tmp/agroguide.db"
        if is_vercel()
        else f"sqlite:///{BASE_DIR / 'agroguide.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    PERMANENT_SESSION_LIFETIME = timedelta(
        days=getenv_int("SESSION_LIFETIME_DAYS", 30)
    )
    REMEMBER_COOKIE_DURATION = timedelta(
        days=getenv_int("REMEMBER_COOKIE_DAYS", 30)
    )
    REMEMBER_COOKIE_REFRESH_EACH_REQUEST = True
    SESSION_REFRESH_EACH_REQUEST = True

    # Uploaded files must also use /tmp on Vercel.
    UPLOAD_FOLDER = Path(
        getenv(
            "UPLOAD_FOLDER",
            "/tmp/uploads" if is_vercel() else BASE_DIR / "app" / "uploads",
        )
    )

    ML_MODELS_FOLDER = BASE_DIR / "app" / "ml_models"
    MAX_CONTENT_LENGTH = getenv_int("MAX_UPLOAD_MB", 8) * 1024 * 1024
    ALLOWED_EXTENSIONS = frozenset({"png", "jpg", "jpeg", "webp", "gif"})

    MODEL_CHECKPOINT = ML_MODELS_FOLDER / "plant_disease_checkpoint.pth"
    CLASS_INDICES = ML_MODELS_FOLDER / "class_indices.json"

    OPEN_METEO_GEOCODE = getenv(
        "OPEN_METEO_GEOCODE_URL", "https://geocoding-api.open-meteo.com/v1/search"
    )
    OPEN_METEO_FORECAST = getenv(
        "OPEN_METEO_FORECAST_URL", "https://api.open-meteo.com/v1/forecast"
    )

    DEFAULT_ADMIN_EMAIL = getenv("ADMIN_EMAIL", "admin@agroguide.com")
    DEFAULT_ADMIN_PASSWORD = getenv("ADMIN_PASSWORD", "Admin@12345")

    # API keys — never hardcode; empty string if unset.
    GEMINI_API_KEY = getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    SEARCH_PROVIDER = getenv("SEARCH_PROVIDER", "tavily")
    SEARCH_API_KEY = getenv("SEARCH_API_KEY", "")
    GOOGLE_CSE_ID = getenv("GOOGLE_CSE_ID", "")

    FLASK_ENV = getenv("FLASK_ENV", "development")
    DEBUG = getenv_bool("FLASK_DEBUG", default=True)

    @classmethod
    def gemini_configured(cls) -> bool:
        return bool(cls.GEMINI_API_KEY)

    @classmethod
    def validate(cls):
        """Warn on missing recommended settings without crashing."""
        if cls.SECRET_KEY == "dev-change-me-in-production":
            warnings.warn(
                "SECRET_KEY is not set. Copy .env.example to .env and set a strong SECRET_KEY.",
                stacklevel=2,
            )
        if not cls.GEMINI_API_KEY:
            warnings.warn(
                "GEMINI_API_KEY is not set. AI Assistant will show a configuration message.",
                stacklevel=2,
            )
        if not cls.GEMINI_MODEL:
            warnings.warn(
                f"GEMINI_MODEL is not set. AI Assistant will use {DEFAULT_GEMINI_MODEL}.",
                stacklevel=2,
            )
        elif cls.GEMINI_MODEL in DEPRECATED_GEMINI_MODELS or "preview" in cls.GEMINI_MODEL.lower():
            warnings.warn(
                f"GEMINI_MODEL={cls.GEMINI_MODEL!r} is deprecated or unsupported. "
                f"Use {DEFAULT_GEMINI_MODEL}, or {FALLBACK_GEMINI_MODEL} as a fallback.",
                stacklevel=2,
            )

    @staticmethod
    def init_app(app):
        pass


class DevelopmentConfig(Config):
    DEBUG = True
    FLASK_ENV = "development"


class ProductionConfig(Config):
    DEBUG = False
    FLASK_ENV = "production"

    @staticmethod
    def init_app(app):
        Config.init_app(app)
        if app.config.get("SECRET_KEY") == "dev-change-me-in-production":
            app.logger.warning(
                "Running in production without SECRET_KEY. Set SECRET_KEY in the environment."
            )


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}


def get_config():
    """Resolve config class from FLASK_ENV / FLASK_CONFIG."""
    name = getenv("FLASK_CONFIG") or getenv("FLASK_ENV", "development")
    return config_by_name.get(name.lower(), DevelopmentConfig)
