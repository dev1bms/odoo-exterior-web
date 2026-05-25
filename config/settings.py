"""Django settings for the odoo-exterior-web project."""

from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


# --- Optional .env loading ------------------------------------------------ #
try:
    from dotenv import load_dotenv  # type: ignore[import-not-found]
    load_dotenv(BASE_DIR / ".env")
except Exception:
    pass


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


# --- Core ----------------------------------------------------------------- #
SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "insecure-dev-key-change-me",  # only used when env var is missing
)
DEBUG = _env_bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = _env_list("DJANGO_ALLOWED_HOSTS", ["127.0.0.1", "localhost"])

# Key used to encrypt Odoo passwords at rest. If empty, the project derives
# a Fernet key from SECRET_KEY (acceptable for local development; set an
# explicit value in production).
FIELD_ENCRYPTION_KEY = os.getenv("FIELD_ENCRYPTION_KEY", "")


# --- Applications --------------------------------------------------------- #
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Local apps
    "accounts",
    "instances",
    "audits",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


# --- Database ------------------------------------------------------------- #
_db_engine = os.getenv("DB_ENGINE")
if _db_engine:
    DATABASES = {
        "default": {
            "ENGINE": _db_engine,
            "NAME": os.getenv("DB_NAME", "odoo_exterior_web"),
            "USER": os.getenv("DB_USER", ""),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "127.0.0.1"),
            "PORT": os.getenv("DB_PORT", ""),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# --- Password validation -------------------------------------------------- #
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# --- Internationalization ------------------------------------------------- #
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# --- Static files --------------------------------------------------------- #
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"


# --- Default primary key -------------------------------------------------- #
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --- Auth routing --------------------------------------------------------- #
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "instances:dashboard"
LOGOUT_REDIRECT_URL = "landing"


# --- Messages framework: Bootstrap-friendly tags -------------------------- #
from django.contrib.messages import constants as messages  # noqa: E402

MESSAGE_TAGS = {
    messages.DEBUG: "secondary",
    messages.INFO: "info",
    messages.SUCCESS: "success",
    messages.WARNING: "warning",
    messages.ERROR: "danger",
}
