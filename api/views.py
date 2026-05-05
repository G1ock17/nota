from decimal import Decimal, InvalidOperation
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from products.gift_cards import (
    GIFT_CARD_APPLY_SESSION_KEY,
    allocate_user_cards,
    decimal_from_money_post,
    total_active_balance,
)
from products.models import GiftCard, GiftCardTransaction


def _json_error(message: str, status: int = 400):
    return JsonResponse({"ok": False, "error": message}, status=status)


@require_POST
def purchase_gift_card(request):
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
