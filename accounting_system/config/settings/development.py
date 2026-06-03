"""Local development settings: SQLite + console email + relaxed hosts."""
from .base import *  # noqa: F401,F403
from .base import BASE_DIR, config
from config.shop_database import configure_shop_database

DEBUG = True
ALLOWED_HOSTS = ["*"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}
configure_shop_database(DATABASES, config, BASE_DIR)

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Allow HTMX/dev tooling over plain HTTP.
CSRF_TRUSTED_ORIGINS = ["http://localhost", "http://127.0.0.1",
                        "http://localhost:8000", "http://127.0.0.1:8000"]
