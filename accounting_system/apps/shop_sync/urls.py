from django.urls import path

from .views import ImportShopOrdersFileView, SyncShopOrdersView

app_name = "shop_sync"

urlpatterns = [
    path("sync/", SyncShopOrdersView.as_view(), name="sync"),
    path("import/", ImportShopOrdersFileView.as_view(), name="import_file"),
]
