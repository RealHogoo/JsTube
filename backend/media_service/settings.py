import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("MEDIA_SERVICE_SECRET_KEY", "dev-media-secret")
DEBUG = os.environ.get("MEDIA_SERVICE_DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = [item.strip() for item in os.environ.get("MEDIA_SERVICE_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if item.strip()]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "media_api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "media_api.middleware.SecurityHeaderMiddleware",
]

ROOT_URLCONF = "media_service.urls"
WSGI_APPLICATION = "media_service.wsgi.application"
ASGI_APPLICATION = "media_service.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "media-service.sqlite3",
    }
}

LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

MEDIA_CONFIG = {
    "ADMIN_SERVICE_BASE_URL": os.environ.get("ADMIN_SERVICE_BASE_URL", "http://localhost:8081").rstrip("/"),
    "WEBHARD_PUBLIC_BASE_URL": os.environ.get("WEBHARD_PUBLIC_BASE_URL", "http://localhost:8083").rstrip("/"),
    "WEBHARD_DB_HOST": os.environ.get("WEBHARD_DB_HOST", "localhost"),
    "WEBHARD_DB_PORT": int(os.environ.get("WEBHARD_DB_PORT", "5432")),
    "WEBHARD_DB_DATABASE": os.environ.get("WEBHARD_DB_DATABASE", "webhard"),
    "WEBHARD_DB_USERNAME": os.environ.get("WEBHARD_DB_USERNAME", "postgres"),
    "WEBHARD_DB_PASSWORD": os.environ.get("WEBHARD_DB_PASSWORD", "postgres"),
    "MEDIA_MONGO_URI": os.environ.get("MEDIA_MONGO_URI", "mongodb://localhost:27017"),
    "MEDIA_MONGO_DATABASE": os.environ.get("MEDIA_MONGO_DATABASE", "media_service"),
    "MEDIA_SYNC_LIMIT": int(os.environ.get("MEDIA_SYNC_LIMIT", "500")),
}

CORS_ORIGINS = [item.strip() for item in os.environ.get("MEDIA_SERVICE_CORS_ORIGINS", "").split(",") if item.strip()]

