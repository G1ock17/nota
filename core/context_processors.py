from products.cart_utils import cart_total_items, get_cart
from products.models import Favorite

from .brand_constants import MEGA_MENU_BRANDS


def cart_context(request):
    return {"cart_item_count": cart_total_items(get_cart(request))}


def favorite_context(request):
    if request.user.is_authenticated:
        ids = set(
            Favorite.objects.filter(user=request.user).values_list(
                "product_id", flat=True
            )
        )
    else:
        ids = set()
    return {"favorite_product_ids": ids}


def nav_mega_menu(request):
    items = [{"name": name, "slug": slug} for name, slug in MEGA_MENU_BRANDS]
    return {"nav_mega_brands": items}
