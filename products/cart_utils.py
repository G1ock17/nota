"""Session-based cart: variant_id (str) -> quantity (int)."""

CART_SESSION_KEY = "cart"


def get_cart(request):
    return request.session.get(CART_SESSION_KEY, {})


def cart_total_items(cart):
    return sum(int(q) for q in cart.values())


def add_variant(request, variant_id, quantity=1):
    cart = {str(k): int(v) for k, v in get_cart(request).items()}
    key = str(variant_id)
    cart[key] = cart.get(key, 0) + int(quantity)
    request.session[CART_SESSION_KEY] = cart
    request.session.modified = True
    return cart


def set_variant_quantity(request, variant_id, quantity):
    cart = {str(k): int(v) for k, v in get_cart(request).items()}
    key = str(variant_id)
    qty = int(quantity)
    if qty > 0:
        cart[key] = qty
    else:
        cart.pop(key, None)
    request.session[CART_SESSION_KEY] = cart
    request.session.modified = True
    return cart
