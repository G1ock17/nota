from django.urls import path

from .cart_views import cart_add, cart_clear, cart_detail, cart_update, checkout_detail
from .views import CatalogListView, ProductDetailView, product_search_suggest

app_name = "products"

urlpatterns = [
    path("search/suggest/", product_search_suggest, name="search_suggest"),
    path("", CatalogListView.as_view(), name="catalog"),
    path("cart/", cart_detail, name="cart"),
    path("checkout/", checkout_detail, name="checkout"),
    path("cart/add/", cart_add, name="cart_add"),
    path("cart/update/", cart_update, name="cart_update"),
    path("cart/clear/", cart_clear, name="cart_clear"),
    path("<slug:slug>/", ProductDetailView.as_view(), name="product_detail"),
]
