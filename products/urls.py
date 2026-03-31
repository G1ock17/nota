from django.urls import path

from .cart_views import cart_add, cart_detail, cart_update, checkout_detail
from .views import CatalogListView, ProductDetailView

app_name = "products"

urlpatterns = [
    path("", CatalogListView.as_view(), name="catalog"),
    path("cart/", cart_detail, name="cart"),
    path("checkout/", checkout_detail, name="checkout"),
    path("cart/add/", cart_add, name="cart_add"),
    path("cart/update/", cart_update, name="cart_update"),
    path("<slug:slug>/", ProductDetailView.as_view(), name="product_detail"),
]
