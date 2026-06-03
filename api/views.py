from decimal import Decimal, InvalidOperation
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_GET, require_POST

from core.rate_limit import ACTION_GIFT_PURCHASE, record_attempt, recent_attempts
from products.gift_cards import (
    GIFT_CARD_APPLY_SESSION_KEY,
    allocate_user_cards,
    decimal_from_money_post,
    total_active_balance,
)
from products.models import GiftCard, GiftCardTransaction, Order


def _json_error(message: str, status: int = 400):
    return JsonResponse({"ok": False, "error": message}, status=status)


def _client_ip(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    return xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "0.0.0.0")


@require_POST
def purchase_gift_card(request):
    # Endpoint создаёт карты без оплаты — доступен только при явном флаге (dev/тест).
    if not getattr(settings, "GIFT_CARD_PURCHASE_ENABLED", False):
        return _json_error("Покупка подарочных карт через API отключена.", status=403)

    ip = _client_ip(request)
    if recent_attempts(ip, ACTION_GIFT_PURCHASE, 60) >= 20:
        return _json_error("Слишком много запросов. Попробуйте позже.", status=429)

    try:
        nominal = decimal_from_money_post(request.POST.get("nominal", "0"))
    except (InvalidOperation, AttributeError, TypeError, ValueError):
        return _json_error("Некорректный номинал.")
    if nominal <= 0:
        return _json_error("Номинал должен быть больше 0.")

    buyer_email = (request.POST.get("email") or "").strip()
    expires_days_raw = (request.POST.get("expires_days") or "").strip()
    expires_at = None
    if expires_days_raw:
        try:
            expires_days = int(expires_days_raw)
            if expires_days > 0:
                expires_at = timezone.now() + timedelta(days=expires_days)
        except ValueError:
            return _json_error("Некорректный срок действия.")

    card = GiftCard.objects.create(
        code=GiftCard.generate_code(),
        nominal=nominal,
        balance=nominal,
        buyer_email=buyer_email,
        expires_at=expires_at,
    )
    GiftCardTransaction.objects.create(
        gift_card=card,
        amount=nominal,
        type=GiftCardTransaction.TxType.PURCHASE,
    )

    if buyer_email:
        # Почтовая отправка может быть отключена в локальной среде.
        send_mail(
            subject="Подарочная карта accord",
            message=f"Ваш код подарочной карты: {card.code}\nНоминал: {card.nominal} ₽",
            from_email=None,
            recipient_list=[buyer_email],
            fail_silently=True,
        )

    record_attempt(ip, ACTION_GIFT_PURCHASE)

    return JsonResponse(
        {
            "ok": True,
            "gift_card": {
                "id": card.id,
                "code": card.code,
                "nominal": str(card.nominal),
                "balance": str(card.balance),
                "expires_at": card.expires_at.isoformat() if card.expires_at else None,
            },
        }
    )


@require_POST
@login_required
@transaction.atomic
def activate_gift_card(request):
    code = (request.POST.get("code") or "").strip().upper()
    if not code:
        return _json_error("Введите код карты.")

    card = GiftCard.objects.select_for_update().filter(code=code).first()
    if not card:
        return _json_error("Карта не найдена.", status=404)
    if card.is_expired:
        return _json_error("Срок действия карты истек.")
    if card.is_activated and card.user_id and card.user_id != request.user.id:
        return _json_error("Карта уже активирована другим пользователем.")
    if card.is_activated and card.user_id == request.user.id:
        return _json_error("Эта карта уже активирована в вашем аккаунте.")

    card.is_activated = True
    card.user = request.user
    card.activated_at = timezone.now()
    card.save(update_fields=["is_activated", "user", "activated_at", "updated_at"])
    GiftCardTransaction.objects.create(
        gift_card=card,
        amount=Decimal("0.00"),
        type=GiftCardTransaction.TxType.ACTIVATION,
    )
    return JsonResponse(
        {
            "ok": True,
            "gift_card": {
                "id": card.id,
                "code": card.code,
                "balance": str(card.balance),
                "activated_at": card.activated_at.isoformat(),
            },
        }
    )


@require_GET
@login_required
def my_gift_cards(request):
    cards = (
        GiftCard.objects.filter(user=request.user, is_activated=True)
        .order_by("-activated_at")
        .values("id", "code", "nominal", "balance", "activated_at", "expires_at")
    )
    return JsonResponse(
        {
            "ok": True,
            "total_balance": str(total_active_balance(request.user)),
            "cards": [
                {
                    **item,
                    "nominal": str(item["nominal"]),
                    "balance": str(item["balance"]),
                    "activated_at": item["activated_at"].isoformat() if item["activated_at"] else None,
                    "expires_at": item["expires_at"].isoformat() if item["expires_at"] else None,
                }
                for item in cards
            ],
        }
    )


@require_POST
@login_required
def apply_gift_card_to_cart(request):
    try:
        order_total = decimal_from_money_post(request.POST.get("order_total", "0"))
        amount = decimal_from_money_post(request.POST.get("amount", "0"))
    except (InvalidOperation, AttributeError, TypeError, ValueError):
        return _json_error("Некорректная сумма.")
    if order_total <= 0:
        return _json_error("Сумма заказа должна быть больше 0.")
    if amount < 0:
        return _json_error("Сумма списания не может быть отрицательной.")

    available = total_active_balance(request.user)
    max_allowed = min(order_total, available)
    if amount > max_allowed:
        return _json_error("Недостаточно баланса карты или сумма превышает заказ.")

    allocations = allocate_user_cards(request.user, amount)
    # Сессия с JSONSerializer: только int/str/list/dict — без Decimal.
    request.session[GIFT_CARD_APPLY_SESSION_KEY] = {
        "amount": str(amount),
        "order_total": str(order_total),
        "allocations": [
            {"gift_card_id": int(a["gift_card_id"]), "amount": str(a["amount"])}
            for a in allocations
        ],
    }
    request.session.modified = True
    return JsonResponse(
        {
            "ok": True,
            "amount": str(amount),
            "available_balance": str(available),
            "payable_amount": str(order_total - amount),
        }
    )


_ACCOUNTING_PAID_STATUSES = (
    Order.Status.PAID,
    Order.Status.ASSEMBLING,
    Order.Status.SHIPPED,
    Order.Status.DELIVERED,
)


def _accounting_token_ok(request) -> bool:
    expected = getattr(settings, "ACCOUNTING_SYNC_TOKEN", "").strip()
    if not expected:
        return False
    supplied = (
        request.headers.get("X-Accounting-Token")
        or request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        or request.GET.get("token", "")
    ).strip()
    return supplied == expected


@require_GET
def accounting_orders_export(request):
    """Paid orders for the accounting system (token-protected, minimal fields)."""
    if not _accounting_token_ok(request):
        return _json_error("Доступ запрещён.", status=403)

    qs = Order.objects.filter(status__in=_ACCOUNTING_PAID_STATUSES).order_by("-created_at")
    since_raw = (request.GET.get("since") or "").strip()
    if since_raw:
        since = parse_date(since_raw)
        if since is not None:
            qs = qs.filter(created_at__date__gte=since)

    orders = []
    for order in qs.iterator():
        orders.append(
            {
                "id": order.pk,
                "email": order.email,
                "first_name": order.first_name,
                "last_name": order.last_name,
                "phone": order.phone,
                "status": order.status,
                "total_price": str(order.total_price),
                "gift_card_debit": str(order.gift_card_debit or Decimal("0")),
                "payable_amount": str(order.payable_amount or Decimal("0")),
                "created_at": order.created_at.isoformat(),
            }
        )

    return JsonResponse({"ok": True, "count": len(orders), "orders": orders})
