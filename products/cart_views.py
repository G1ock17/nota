from decimal import Decimal

from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .cart_utils import add_variant, cart_total_items, get_cart, set_variant_quantity
from .models import Variant


@require_POST
def cart_add(request):
    variant_id_raw = request.POST.get("variant_id")
    if variant_id_raw:
        try:
            variant_pk = int(variant_id_raw)
        except (TypeError, ValueError):
            return HttpResponseBadRequest("Invalid variant")
        variant = (
            Variant.objects.filter(pk=variant_pk, stock__gt=0)
            .select_related("product", "product__brand")
            .first()
        )
    else:
        try:
            product_id = int(request.POST.get("product_id", ""))
        except (TypeError, ValueError):
            return HttpResponseBadRequest("Invalid product")
        variant = (
            Variant.objects.filter(product_id=product_id, stock__gt=0)
            .select_related("product", "product__brand")
            .order_by("price", "volume")
            .first()
        )

    is_htmx = request.headers.get("HX-Request") == "true"

    if not variant:
        if is_htmx:
            return render(
                request,
                "products/partials/cart_toast.html",
                {"error": "Нет в наличии"},
                status=200,
            )
        return HttpResponseBadRequest("Out of stock")

    cart = add_variant(request, variant.pk, 1)
    count = cart_total_items(cart)

    if is_htmx:
        product_name = variant.product.name
        vol = variant.get_volume_display()
        if vol:
            product_name = f"{product_name} ({vol})"
        return render(
            request,
            "products/partials/cart_toast.html",
            {
                "product_name": product_name,
                "item_count": count,
            },
            status=200,
        )

    return HttpResponseBadRequest("HTMX required")


def cart_detail(request):
    raw_cart = get_cart(request)
    variant_ids = []
    for key in raw_cart.keys():
        try:
            variant_ids.append(int(key))
        except (TypeError, ValueError):
            continue

    variants = {
        v.pk: v
        for v in Variant.objects.filter(pk__in=variant_ids).select_related(
            "product", "product__brand"
        )
    }

    items = []
    total_price = Decimal("0")
    for key, qty in raw_cart.items():
        try:
            variant_id = int(key)
            quantity = int(qty)
        except (TypeError, ValueError):
            continue
        variant = variants.get(variant_id)
        if not variant or quantity <= 0:
            continue
        line_total = variant.price * quantity
        total_price += line_total
        items.append(
            {
                "variant": variant,
                "quantity": quantity,
                "line_total": line_total,
            }
        )

    return render(
        request,
        "products/cart.html",
        {
            "cart_items": items,
            "total_price": total_price,
            "item_count": cart_total_items(raw_cart),
        },
    )


@require_POST
def cart_update(request):
    try:
        variant_id = int(request.POST.get("variant_id", ""))
    except (TypeError, ValueError):
        return HttpResponseBadRequest("Invalid variant")

    action = request.POST.get("action", "").strip().lower()
    cart = get_cart(request)
    current_qty = int(cart.get(str(variant_id), 0) or 0)

    if action == "inc":
        set_variant_quantity(request, variant_id, current_qty + 1)
    elif action == "dec":
        set_variant_quantity(request, variant_id, current_qty - 1)
    elif action == "remove":
        set_variant_quantity(request, variant_id, 0)
    else:
        try:
            quantity = int(request.POST.get("quantity", current_qty))
        except (TypeError, ValueError):
            quantity = current_qty
        set_variant_quantity(request, variant_id, quantity)

    return redirect("products:cart")
