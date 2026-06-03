"""Optional read-only connection to the Accord shop database."""

from pathlib import Path


def configure_shop_database(databases: dict, config, base_dir: Path) -> None:
    """Add ``DATABASES['shop']`` when SHOP_DB_NAME (or SHOP_DB_ENGINE=sqlite3) is set."""
    shop_name = config("SHOP_DB_NAME", default="").strip()
    shop_engine = config("SHOP_DB_ENGINE", default="").strip()

    if not shop_name and not shop_engine:
        return

    if shop_engine == "sqlite3" or (not shop_engine and shop_name.endswith(".sqlite3")):
        path = Path(shop_name)
        if not path.is_absolute():
            path = base_dir / path
        databases["shop"] = {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": path,
        }
        return

    if not shop_name:
        return

    databases["shop"] = {
        "ENGINE": shop_engine or "django.db.backends.mysql",
        "NAME": shop_name,
        "USER": config("SHOP_DB_USER", default=""),
        "PASSWORD": config("SHOP_DB_PASSWORD", default=""),
        "HOST": config("SHOP_DB_HOST", default="localhost"),
        "PORT": config("SHOP_DB_PORT", default="3306"),
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
        "CONN_MAX_AGE": 60,
    }
