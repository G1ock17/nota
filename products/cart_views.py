import json
import logging
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.contrib import messages
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from .cart_utils import CART_SESSION_KEY, add_variant, cart_total_items, get_cart, set_variant_quantity
from .gift_cards import (
    GIFT_CARD_APPLY_SESSION_KEY,
    apply_gift_cards_to_order,
    cancel_checkout_order_after_payment_failure,
    total_active_balance,
)
from .models import Order, OrderItem, Variant
from .ozon_pay import (
    create_redirect_payment,
    fetch_order_details,
    is_ozon_pay_configured,
    try_mark_order_paid_from_details,
    try_mark_order_paid_from_notification,
    verify_notification_signature,
)
from core.models import DeliveryAddress, UserProfile

GUEST_CHECKOUT_ADDRESS_KEY = "guest_checkout_address"

logger = logging.getLogger(__name__)


def _webhook_client_ip(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def _webhook_ip_allowed(request) -> bool:
    allowed = getattr(settings, "OZON_PAY_WEBHOOK_IPS", frozenset())
    if not allowed:
        return True
    client_ip = _webhook_client_ip(request)
    return client_ip in allowed


def _send_order_confirmation_email(order: Order, checkout_items: list[dict], request=None) -> None:
    email_items = []
    for item in checkout_items:
        variant = item["variant"]
        product_name = variant.product.display_name
        volume = variant.get_volume_display()
        if volume:
            product_name = f"{product_name} ({volume})"
        quantity = int(item["quantity"])
        line_total = item["line_total"]
        email_items.append(
            {
                "name": product_name,
                "quantity": quantity,
                "line_total": line_total,
            }
        )

    payment_note = (
        "Заказ ожидает онлайн-оплату."
        if order.payable_amount > Decimal("0.00")
        else "Полностью оплачено подарочной картой."
    )

    context = {
        "order": order,
        "email_items": email_items,
        "payment_note": payment_note,
        "logo_url": request.build_absolute_uri(static("core/img/brand-logo.png")) if request else "",
    }

    text_body = render_to_string("products/emails/order_confirmation.txt", context)
    html_body = render_to_string("products/emails/order_confirmation.html", context)

    try:
        email = EmailMultiAlternatives(
            subject=f"Ваш заказ №{order.pk} оформлен",
            body=text_body,
            from_email=None,
            to=[order.email],
        )
        email.attach_alternative(html_body, "text/html")
        email.send(fail_silently=False)
    except Exception:
        logger.exception("Не удалось отправить email-подтверждение для заказа %s", order.pk)


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
        product_name = variant.product.display_name
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


@require_POST
def cart_add_bulk(request):
    """Добавить несколько вариантов в корзину (набор пробников)."""
    raw_ids = request.POST.getlist("variant_id")
    if not raw_ids:
        raw = (request.POST.get("variant_ids") or "").strip()
        if raw:
            raw_ids = [x.strip() for x in raw.split(",") if x.strip()]

    is_htmx = request.headers.get("HX-Request") == "true"
    added_count = 0
    cart = get_cart(request)

    for raw in raw_ids:
        try:
            variant_pk = int(raw)
        except (TypeError, ValueError):
            continue
        variant = Variant.objects.filter(pk=variant_pk, stock__gt=0).first()
        if not variant:
            continue
        cart = add_variant(request, variant.pk, 1)
        added_count += 1

    count = cart_total_items(cart)

    if not added_count:
        if is_htmx:
            return render(
                request,
                "products/partials/cart_toast.html",
                {"error": "Нет в наличии"},
                status=200,
            )
        return HttpResponseBadRequest("Нет в наличии")

    if is_htmx:
        label = "пробник" if added_count == 1 else "пробников"
        return render(
            request,
            "products/partials/cart_toast.html",
            {
                "product_name": f"Набор пробников ({added_count} {label})",
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
            "line_count": len(items),
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

        gift_applied = Decimal("0.00")
        gift_available = Decimal("0.00")
        gift_payable = total_price
        if request.user.is_authenticated:
            gift_available = total_active_balance(request.user)
            session_apply = request.session.get(GIFT_CARD_APPLY_SESSION_KEY) or {}
            try:
                gift_applied = Decimal(session_apply.get("amount", "0"))
            except (InvalidOperation, TypeError, ValueError):
                gift_applied = Decimal("0.00")
            max_applicable = min(total_price, gift_available)
            if gift_applied > max_applicable:
                gift_applied = max_applicable
            if gift_applied < 0:
                gift_applied = Decimal("0.00")
            gift_payable = total_price - gift_applied

        # Для JS/API: без локализации (ru даёт «5 000,00» → Number() = NaN).
        checkout_total_amount_str = format(total_price, "f")
        gift_available_balance_str = format(gift_available, "f")
        gift_applied_amount_str = format(gift_applied, "f")
        gift_payable_amount_str = format(gift_payable, "f")

        return {
            "cart_items": items,
            "total_price": total_price,
            "ozon_pay_enabled": is_ozon_pay_configured(),
            "checkout_total_amount_str": checkout_total_amount_str,
            "gift_available_balance": gift_available,
            "gift_available_balance_str": gift_available_balance_str,
            "gift_applied_amount": gift_applied,
            "gift_applied_amount_str": gift_applied_amount_str,
            "gift_payable_amount": gift_payable,
            "gift_payable_amount_str": gift_payable_amount_str,
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
            gift_card_debit=Decimal("0.00"),
            payable_amount=total_price,
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
        if request.user.is_authenticated:
            session_apply = request.session.get(GIFT_CARD_APPLY_SESSION_KEY) or {}
            try:
                requested = Decimal(session_apply.get("amount", "0"))
            except (InvalidOperation, TypeError, ValueError):
                requested = Decimal("0.00")
            if requested > 0:
                apply_gift_cards_to_order(order=order, user=request.user, requested_amount=requested)
        _send_order_confirmation_email(order, items, request=request)

        if order.payable_amount > Decimal("0.00") and is_ozon_pay_configured():
            try:
                success_url = request.build_absolute_uri(reverse("products:ozon_pay_return"))
                fail_url = request.build_absolute_uri(reverse("products:checkout"))
                notification_url = request.build_absolute_uri(reverse("products:ozon_pay_webhook"))
                payment = create_redirect_payment(
                    order,
                    success_url=success_url,
                    fail_url=fail_url,
                    notification_url=notification_url,
                )
                confirm_url = payment.get("_pay_link")
                ozon_order_id = payment.get("_ozon_order_id")
                if not confirm_url or not ozon_order_id:
                    raise ValueError("Ответ Ozon Pay без payLink или id заказа")
                order.ozon_pay_order_id = ozon_order_id
                order.save(update_fields=["ozon_pay_order_id"])
                request.session[CART_SESSION_KEY] = {}
                request.session.pop(GIFT_CARD_APPLY_SESSION_KEY, None)
                if not request.user.is_authenticated:
                    request.session.pop(GUEST_CHECKOUT_ADDRESS_KEY, None)
                request.session["pending_ozon_pay_order_id"] = order.pk
                request.session.modified = True
                return redirect(confirm_url)
            except Exception:
                logger.exception("Не удалось создать платёж Ozon Pay")
                cancel_checkout_order_after_payment_failure(order)
                messages.error(
                    request,
                    "Не удалось перейти к оплате. Попробуйте ещё раз.",
                )
                return redirect("products:checkout")

        request.session[CART_SESSION_KEY] = {}
        request.session.pop(GIFT_CARD_APPLY_SESSION_KEY, None)
        if not request.user.is_authenticated:
            request.session.pop(GUEST_CHECKOUT_ADDRESS_KEY, None)
            request.session["checkout_last_order_id"] = order.pk
        request.session.modified = True
        if request.user.is_authenticated:
            return redirect("account")
        return redirect("products:checkout_success")

    return render_checkout()


@require_http_methods(["GET", "HEAD"])
def ozon_pay_return(request):
    if not is_ozon_pay_configured():
        return redirect("products:cart")

    pending_id = request.session.get("pending_ozon_pay_order_id")
    if not pending_id:
        return redirect("products:cart")

    order = Order.objects.filter(pk=pending_id).first()
    if not order or not order.ozon_pay_order_id:
        request.session.pop("pending_ozon_pay_order_id", None)
        return redirect("products:cart")

    try:
        details = fetch_order_details(order)
    except Exception:
        logger.exception("Ozon Pay: не удалось получить статус заказа")
        messages.warning(
            request,
            "Не удалось проверить оплату. Если деньги списались, статус заказа обновится после уведомления от Ozon Pay.",
        )
        if order.user_id:
            return redirect("account")
        request.session["checkout_last_order_id"] = order.pk
        request.session.modified = True
        return redirect("products:checkout_success")

    request.session.pop("pending_ozon_pay_order_id", None)
    request.session.modified = True

    if try_mark_order_paid_from_details(order, details):
        if order.user_id:
            return redirect("account")
        request.session["checkout_last_order_id"] = order.pk
        return redirect("products:checkout_success")

    item = details.get("item") or (details.get("order") or {}).get("item") or {}
    status = (item.get("status") or "").strip() if isinstance(item, dict) else ""
    if status in ("STATUS_CANCELLED", "STATUS_CANCELED", "STATUS_EXPIRED"):
        messages.info(request, "Оплата отменена.")
        return redirect("products:catalog")

    messages.info(request, "Платёж ещё обрабатывается.")
    if order.user_id:
        return redirect("account")
    request.session["checkout_last_order_id"] = order.pk
    return redirect("products:checkout_success")


@csrf_exempt
@require_POST
def ozon_pay_webhook(request):
    """
    POST-нотификация Ozon Pay о статусе транзакции.
    csrf_exempt необходим для внешних POST; проверяем подпись requestSign
    и при необходимости IP allowlist.
    """
    if not is_ozon_pay_configured():
        return HttpResponse(status=403)
    if not _webhook_ip_allowed(request):
        logger.warning("Ozon Pay webhook: запрос с неразрешённого IP %s", _webhook_client_ip(request))
        return HttpResponse(status=403)
    try:
        data = json.loads(request.body.decode())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return HttpResponse(status=400)

    if not isinstance(data, dict):
        return HttpResponse(status=400)
    if not verify_notification_signature(data):
        logger.warning("Ozon Pay webhook: неверная подпись")
        return HttpResponse(status=403)

    ext_order_id = (data.get("extOrderID") or data.get("extOrderId") or "").strip()
    order = None
    if ext_order_id:
        order = Order.objects.filter(pk=ext_order_id).first()
    if not order:
        order_id = (data.get("orderID") or data.get("orderId") or "").strip()
        if order_id:
            order = Order.objects.filter(ozon_pay_order_id=order_id).first()

    if order and (data.get("status") or "").strip() == "Completed":
        try_mark_order_paid_from_notification(order, data)
    return HttpResponse(status=200)


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
        new_qty = current_qty + 1
    elif action == "dec":
        new_qty = current_qty - 1
    elif action == "remove":
        new_qty = 0
    else:
        try:
            new_qty = int(request.POST.get("quantity", current_qty))
        except (TypeError, ValueError):
            new_qty = current_qty

    set_variant_quantity(request, variant_id, new_qty)

    is_ajax = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.headers.get("HX-Request") == "true"
        or "application/json" in request.headers.get("Accept", "")
    )

    if not is_ajax:
        return redirect("products:cart")

    cart_after = get_cart(request)
    final_qty = int(cart_after.get(str(variant_id), 0) or 0)

    variant_ids: list[int] = []
    for key in cart_after.keys():
        try:
            variant_ids.append(int(key))
        except (TypeError, ValueError):
            continue

    prices = {
        v.pk: v.price
        for v in Variant.objects.filter(pk__in=variant_ids).only("pk", "price")
    }

    total_price = Decimal("0")
    for key, qty in cart_after.items():
        try:
            vid = int(key)
            q = int(qty)
        except (TypeError, ValueError):
            continue
        if q <= 0 or vid not in prices:
            continue
        total_price += prices[vid] * q

    line_total = (prices.get(variant_id, Decimal("0")) * final_qty) if final_qty > 0 else Decimal("0")
    item_count = cart_total_items(cart_after)

    return JsonResponse(
        {
            "ok": True,
            "variant_id": variant_id,
            "quantity": final_qty,
            "removed": final_qty <= 0,
            "line_total": format(line_total, "f"),
            "line_total_display": f"{line_total:.2f} \u20bd",
            "total_price": format(total_price, "f"),
            "total_price_display": f"{total_price:.2f} \u20bd",
            "item_count": item_count,
            "empty": item_count <= 0,
        }
    )
