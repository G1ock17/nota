from decimal import Decimal
from urllib.parse import urlencode

from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .cart_utils import CART_SESSION_KEY, add_variant, cart_total_items, get_cart, set_variant_quantity
from .models import Order, OrderItem, Variant
from core.models import DeliveryAddress, UserProfile

GUEST_CHECKOUT_ADDRESS_KEY = "guest_checkout_address"


def _guest_address_complete(data) -> bool:
    if not data or not isinstance(data, dict):
        return False
    required = ["country", "city", "region", "postal_code", "address_line1"]
    return all((data.get(f) or "").strip() for f in required)


def _format_guest_checkout_address(data: dict) -> str:
    parts = [
        (data.get("country") or "").strip(),
        (data.get("region") or "").strip(),
        (data.get("city") or "").strip(),
        (data.get("address_line1") or "").strip(),
    ]
    extra = (data.get("address_line2") or "").strip()
    if extra:
        parts.append(extra)
    parts.append((data.get("postal_code") or "").strip())
    return "Адрес: " + ", ".join(p for p in parts if p)


def _address_prefill_from_model(address):
    if not address:
        return {
            "country": "",
            "city": "",
            "region": "",
            "postal_code": "",
            "address_line1": "",
            "address_line2": "",
        }
    return {
        "country": address.country,
        "city": address.city,
        "region": address.region,
        "postal_code": address.postal_code,
        "address_line1": address.address_line1,
        "address_line2": address.address_line2 or "",
    }


def _address_prefill_from_session_dict(data: dict):
    if not data:
        data = {}
    return {
        "country": (data.get("country") or "").strip(),
        "city": (data.get("city") or "").strip(),
        "region": (data.get("region") or "").strip(),
        "postal_code": (data.get("postal_code") or "").strip(),
        "address_line1": (data.get("address_line1") or "").strip(),
        "address_line2": (data.get("address_line2") or "").strip(),
    }


def _user_checkout_address(user):
    saved = list(
        DeliveryAddress.objects.filter(user=user).order_by("-is_default", "-created_at")
    )
    default = next((a for a in saved if a.is_default), None)
    if not default and saved:
        default = saved[0]
    return default


def _format_checkout_address(address: DeliveryAddress) -> str:
    parts = [
        address.country,
        address.region,
        address.city,
        address.address_line1,
    ]
    extra = (address.address_line2 or "").strip()
    if extra:
        parts.append(extra)
    parts.append(address.postal_code)
    return "Адрес: " + ", ".join(p for p in parts if p)


@require_POST
def cart_add(request):
    variant_id_raw = request.POST.get("variant_id")
    if variant_id_raw:
        try:
            variant_pk = int(variant_id_raw)
        except (TypeError, ValueError):
            return HttpResponseBadRequest("Некорректный вариант")
        variant = (
            Variant.objects.filter(pk=variant_pk, stock__gt=0)
            .select_related("product", "product__brand")
            .first()
        )
    else:
        try:
            product_id = int(request.POST.get("product_id", ""))
        except (TypeError, ValueError):
            return HttpResponseBadRequest("Некорректный товар")
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
        return HttpResponseBadRequest("Нет в наличии")

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

    return HttpResponseBadRequest("Требуется HTMX")


def cart_detail(request):
    raw_cart = get_cart(request)
    checkout_next_query = urlencode({"next": reverse("products:checkout")})
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
            "checkout_next_query": checkout_next_query,
        },
    )


@require_POST
def checkout_save_address(request):
    address_id_raw = request.POST.get("address_id", "").strip()
    country = request.POST.get("country", "").strip()
    city = request.POST.get("city", "").strip()
    region = request.POST.get("region", "").strip()
    postal_code = request.POST.get("postal_code", "").strip()
    address_line1 = request.POST.get("address_line1", "").strip()
    address_line2 = request.POST.get("address_line2", "").strip()

    if not all([country, city, region, postal_code, address_line1]):
        return JsonResponse(
            {"ok": False, "error": "Заполните все поля адреса."},
            status=400,
        )

    if not request.user.is_authenticated:
        request.session[GUEST_CHECKOUT_ADDRESS_KEY] = {
            "country": country,
            "city": city,
            "region": region,
            "postal_code": postal_code,
            "address_line1": address_line1,
            "address_line2": address_line2,
        }
        request.session.modified = True
        summary = _format_guest_checkout_address(request.session[GUEST_CHECKOUT_ADDRESS_KEY])
        return JsonResponse({"ok": True, "guest": True, "summary": summary})

    address = None
    if address_id_raw:
        try:
            aid = int(address_id_raw)
        except (TypeError, ValueError):
            return JsonResponse({"ok": False, "error": "Некорректный адрес."}, status=400)
        address = DeliveryAddress.objects.filter(pk=aid, user=request.user).first()
        if not address:
            return JsonResponse(
                {"ok": False, "error": "Адрес не найден. Обновите страницу."},
                status=400,
            )

    if not address:
        address = _user_checkout_address(request.user)

    if address:
        address.country = country
        address.city = city
        address.region = region
        address.postal_code = postal_code
        address.address_line1 = address_line1
        address.address_line2 = address_line2
        address.save(
            update_fields=[
                "country",
                "city",
                "region",
                "postal_code",
                "address_line1",
                "address_line2",
            ]
        )
    else:
        address = DeliveryAddress.objects.create(
            user=request.user,
            country=country,
            city=city,
            region=region,
            postal_code=postal_code,
            address_line1=address_line1,
            address_line2=address_line2,
            is_default=True,
        )

    return JsonResponse(
        {
            "ok": True,
            "address_id": address.pk,
            "summary": _format_checkout_address(address),
        }
    )


def checkout_success(request):
    order_id = request.session.pop("checkout_last_order_id", None)
    return render(
        request,
        "products/checkout_success.html",
        {"order_id": order_id},
    )


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
        for v in Variant.objects.filter(pk__in=variant_ids)
        .select_related("product", "product__brand")
        .prefetch_related("product__images")
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

    def initial_checkout_form():
        if request.user.is_authenticated:
            profile, _ = UserProfile.objects.get_or_create(user=request.user)
            return {
                "email": request.user.email or "",
                "first_name": request.user.first_name or "",
                "last_name": request.user.last_name or "",
                "phone": (profile.phone or "").strip(),
                "order_note": "",
            }
        return {
            "email": "",
            "first_name": "",
            "last_name": "",
            "phone": "",
            "order_note": "",
        }

    def build_checkout_context(form_data):
        guest_data = request.session.get(GUEST_CHECKOUT_ADDRESS_KEY) or {}
        is_auth = request.user.is_authenticated
        if is_auth:
            checkout_address = _user_checkout_address(request.user)
            checkout_address_summary = (
                _format_checkout_address(checkout_address) if checkout_address else ""
            )
            checkout_has_address = checkout_address is not None
            address_prefill = _address_prefill_from_model(checkout_address)
        else:
            checkout_address = None
            checkout_address_summary = (
                _format_guest_checkout_address(guest_data)
                if _guest_address_complete(guest_data)
                else ""
            )
            checkout_has_address = _guest_address_complete(guest_data)
            address_prefill = _address_prefill_from_session_dict(guest_data)

        return {
            "cart_items": items,
            "total_price": total_price,
            "item_count": cart_total_items(raw_cart),
            "checkout_form": form_data,
            "checkout_address": checkout_address,
            "checkout_address_summary": checkout_address_summary,
            "checkout_has_address": checkout_has_address,
            "address_prefill": address_prefill,
            "checkout_guest": not is_auth,
        }

    checkout_form = initial_checkout_form()

    def render_checkout(**extra):
        ctx = build_checkout_context(checkout_form)
        ctx.update(extra)
        return render(request, "products/checkout.html", ctx)

    if request.method == "POST":
        if not items:
            return redirect("products:cart")
        checkout_form = {
            "email": request.POST.get("email", "").strip(),
            "first_name": request.POST.get("first_name", "").strip(),
            "last_name": request.POST.get("last_name", "").strip(),
            "phone": request.POST.get("phone", "").strip(),
            "order_note": request.POST.get("order_note", "").strip(),
        }

        required_contact = ["email", "first_name", "last_name", "phone"]

        if not request.POST.get("terms_accepted"):
            return render_checkout(
                checkout_error="Подтвердите согласие с правилами и политикой.",
            )
        if any(not checkout_form[f] for f in required_contact):
            return render_checkout(
                checkout_error="Заполните имя, фамилию, email и телефон.",
            )

        country = ""
        address_line1 = ""
        address_line2 = ""
        city = ""
        region = ""
        postal_code = ""

        if request.user.is_authenticated:
            address_id_raw = request.POST.get("checkout_address_id", "").strip()
            delivery_address = None
            if address_id_raw:
                try:
                    aid = int(address_id_raw)
                except (TypeError, ValueError):
                    aid = None
                if aid is not None:
                    delivery_address = DeliveryAddress.objects.filter(
                        pk=aid, user=request.user
                    ).first()
            if not delivery_address:
                return render_checkout(
                    checkout_error="Укажите и сохраните адрес доставки.",
                )
            country = delivery_address.country
            address_line1 = delivery_address.address_line1
            address_line2 = delivery_address.address_line2 or ""
            city = delivery_address.city
            region = delivery_address.region
            postal_code = delivery_address.postal_code
            order_user = request.user
        else:
            gd = request.session.get(GUEST_CHECKOUT_ADDRESS_KEY)
            if not _guest_address_complete(gd):
                return render_checkout(
                    checkout_error="Укажите и сохраните адрес доставки.",
                )
            country = gd["country"].strip()
            address_line1 = gd["address_line1"].strip()
            address_line2 = (gd.get("address_line2") or "").strip()
            city = gd["city"].strip()
            region = gd["region"].strip()
            postal_code = gd["postal_code"].strip()
            order_user = None

        order = Order.objects.create(
            user=order_user,
            email=checkout_form["email"],
            first_name=checkout_form["first_name"],
            last_name=checkout_form["last_name"],
            phone=checkout_form["phone"],
            country=country,
            address_line1=address_line1,
            address_line2=address_line2,
            city=city,
            region=region,
            postal_code=postal_code,
            delivery_method=Order.DeliveryMethod.COURIER,
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
        request.session[CART_SESSION_KEY] = {}
        if not request.user.is_authenticated:
            request.session.pop(GUEST_CHECKOUT_ADDRESS_KEY, None)
            request.session["checkout_last_order_id"] = order.pk
        request.session.modified = True
        if request.user.is_authenticated:
            return redirect("account")
        return redirect("products:checkout_success")

    return render_checkout()


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
        return HttpResponseBadRequest("Некорректный вариант")

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
