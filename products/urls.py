from django.urls import path

from .views import CatalogListView

app_name = "products"

urlpatterns = [
    path("", CatalogListView.as_view(), name="catalog"),
]
