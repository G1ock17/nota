from products.cart_utils import cart_total_items, get_cart


def cart_context(request):
    return {"cart_item_count": cart_total_items(get_cart(request))}
