from django.urls import path

from .views import (
    activate_gift_card,
    apply_gift_card_to_cart,
    my_gift_cards,
    purchase_gift_card,
)

urlpatterns = [
    path("gift-cards/purchase", purchase_gift_card, name="api_gift_cards_purchase"),
    path("gift-cards/activate", activate_gift_card, name="api_gift_cards_activate"),
    path("gift-cards/my", my_gift_cards, name="api_gift_cards_my"),
    path("cart/apply-gift-card", apply_gift_card_to_cart, name="api_cart_apply_gift_card"),
]
