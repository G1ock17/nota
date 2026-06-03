from django.apps import AppConfig


class ShopSyncConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.shop_sync"
    verbose_name = "Синхронизация с магазином"
