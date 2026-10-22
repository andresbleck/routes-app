"""Django settings for the Weather-Aware Truck Routing API.

The API is stateless: no database, no auth, no sessions. Configuration comes
from environment variables so the same settings work locally and on Render.
"""

import os
import tempfile
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Local development reads backend/.env; on Render variables come from the environment.
load_dotenv(BASE_DIR / ".env")


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() == "true"

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is false.")
    SECRET_KEY = "dev-only-insecure-key"

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
# Render provides the service's public hostname, e.g. routes-app-api.onrender.com.
if render_hostname := os.environ.get("RENDER_EXTERNAL_HOSTNAME"):
    ALLOWED_HOSTS.append(render_hostname)

INSTALLED_APPS = [
    "django.contrib.staticfiles",  # assets for DRF's browsable API (DEBUG only)
    "corsheaders",
    "rest_framework",
    "trips",
]

MIDDLEWARE = [
    "django.middleware.gzip.GZipMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
    }
]
STATIC_URL = "static/"

DATABASES = {}

# A plan prepared in step 1 is read back in step 2, possibly by another
# Gunicorn worker, so the cache lives on disk rather than in process memory.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": Path(tempfile.gettempdir()) / "routes-app-cache",
        "TIMEOUT": 30 * 60,
    }
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}
if DEBUG:
    # Lets you try the API from the browser at http://localhost:8000/api/...
    REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"].append("rest_framework.renderers.BrowsableAPIRenderer")

# Origins must not end with "/", a common slip when pasting the frontend URL.
CORS_ALLOWED_ORIGINS = [origin.rstrip("/") for origin in env_list("CORS_ALLOWED_ORIGINS", "http://localhost:5173")]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

# External providers
TOMTOM_API_KEY = os.environ.get("TOMTOM_API_KEY", "")
