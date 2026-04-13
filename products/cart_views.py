from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .cart_utils import CART_SESSION_KEY, add_variant, cart_total_items, get_cart, set_variant_quantity
from .models import Order, OrderItem, Variant
from core.models import DeliveryAddress


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


@login_required(login_url="register")
def checkout_detail(request):
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

    saved_addresses = list(
        DeliveryAddress.objects.filter(user=request.user).order_by("-is_default", "-created_at")
    )
    default_address = next((address for address in saved_addresses if address.is_default), None)
    if not default_address and saved_addresses:
        default_address = saved_addresses[0]

    checkout_form = {
        "email": request.user.email or "",
        "first_name": request.user.first_name or "",
        "last_name": request.user.last_name or "",
        "phone": "",
        "country": default_address.country if default_address else "",
        "address_line1": default_address.address_line1 if default_address else "",
        "address_line2": default_address.address_line2 if default_address else "",
        "city": default_address.city if default_address else "",
        "region": default_address.region if default_address else "",
        "postal_code": default_address.postal_code if default_address else "",
        "delivery_method": Order.DeliveryMethod.COURIER,
        "order_note": "",
    }
    selected_address_id = str(default_address.id) if default_address else ""

    if request.method == "POST":
        if not items:
            return redirect("products:cart")
        checkout_form = {
            "email": request.POST.get("email", "").strip(),
            "first_name": request.POST.get("first_name", "").strip(),
            "last_name": request.POST.get("last_name", "").strip(),
            "phone": request.POST.get("phone", "").strip(),
            "country": request.POST.get("country", "").strip(),
            "address_line1": request.POST.get("address_line1", "").strip(),
            "address_line2": request.POST.get("address_line2", "").strip(),
            "city": request.POST.get("city", "").strip(),
            "region": request.POST.get("region", "").strip(),
            "postal_code": request.POST.get("postal_code", "").strip(),
            "delivery_method": request.POST.get(
                "delivery_method",
                Order.DeliveryMethod.COURIER,
            ),
            "order_note": request.POST.get("order_note", "").strip(),
        }
        selected_address_id = request.POST.get("selected_address_id", "").strip()

        required_fields = [
            "email",
            "first_name",
            "last_name",
            "phone",
            "country",
            "address_line1",
            "city",
            "region",
            "postal_code",
        ]
        if not request.POST.get("terms_accepted"):
            return render(
                request,
                "products/checkout.html",
                {
                    "cart_items": items,
                    "total_price": total_price,
                    "item_count": cart_total_items(raw_cart),
                    "checkout_error": "Подтвердите согласие с правилами и политикой.",
                    "checkout_form": checkout_form,
                    "saved_addresses": saved_addresses,
                    "selected_address_id": selected_address_id,
                },
            )
        if any(not request.POST.get(field, "").strip() for field in required_fields):
            return render(
                request,
                "products/checkout.html",
                {
                    "cart_items": items,
                    "total_price": total_price,
                    "item_count": cart_total_items(raw_cart),
                    "checkout_error": "Заполните все обязательные поля оформления заказа.",
                    "checkout_form": checkout_form,
                    "saved_addresses": saved_addresses,
                    "selected_address_id": selected_address_id,
                },
            )

        delivery_method = request.POST.get(
            "delivery_method",
            Order.DeliveryMethod.COURIER,
        )
        valid_delivery_methods = {
            value for value, _ in Order.DeliveryMethod.choices
        }
        if delivery_method not in valid_delivery_methods:
            delivery_method = Order.DeliveryMethod.COURIER

        order = Order.objects.create(
            user=request.user,
            email=checkout_form["email"],
            first_name=checkout_form["first_name"],
            last_name=checkout_form["last_name"],
            phone=checkout_form["phone"],
            country=checkout_form["country"],
            address_line1=checkout_form["address_line1"],
            address_line2=checkout_form["address_line2"],
            city=checkout_form["city"],
            region=checkout_form["region"],
            postal_code=checkout_form["postal_code"],
            delivery_method=delivery_method,
            order_note=checkout_form["order_note"],
            total_price=total_price,
        )
        OrderItem.objects.bulk_create(
            [
                OrderItem(
                    order=order,
                    variant=item["variant"],
                    quantity=item["quantity"],
                    price=item["variant"].price,
                    line_total=item["line_total"],
                )
                for item in items
            ]
        )
        request.session["cart"] = {}
        request.session.modified = True
        return redirect("account")

    return render(
        request,
        "products/checkout.html",
        {
            "cart_items": items,
            "total_price": total_price,
            "item_count": cart_total_items(raw_cart),
            "checkout_form": checkout_form,
            "saved_addresses": saved_addresses,
            "selected_address_id": selected_address_id,
        },
    )


@require_POST
def cart_clear(request):
    request.session[CART_SESSION_KEY] = {}
    request.session.modified = True
    return redirect("products:cart")


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
