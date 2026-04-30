import re
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import GiftCard, GiftCardTransaction, Order


GIFT_CARD_APPLY_SESSION_KEY = "checkout_gift_card_apply"


def decimal_from_money_post(raw) -> Decimal:
    """
    Парсит сумму из POST/query: «111,01», «10 000,50», «10000.5».
    """
    if raw is None:
        raise InvalidOperation
    s = str(raw).strip()
    for ch in ("\u00a0", "\u202f"):
        s = s.replace(ch, "")
    s = re.sub(r"\s+", "", s)
    if not s:
        raise InvalidOperation
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    return Decimal(s)


def active_user_cards_queryset(user):
    now = timezone.now()
    return GiftCard.objects.select_for_update().filter(
        user=user,
        is_activated=True,
        balance__gt=Decimal("0.00"),
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))


def active_user_cards(user):
    now = timezone.now()
    return GiftCard.objects.filter(
        user=user,
        is_activated=True,
        balance__gt=Decimal("0.00"),
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))


def total_active_balance(user) -> Decimal:
    value = (
        active_user_cards(user).aggregate(
            total=Coalesce(Sum("balance"), Decimal("0.00"))
        ).get("total")
        or Decimal("0.00")
    )
    return Decimal(value)


def allocate_user_cards(user, amount: Decimal):
    amount = Decimal(amount or "0.00")
    if amount <= 0:
        return []
    allocations = []
    remaining = amount
    cards = list(active_user_cards(user).order_by("expires_at", "created_at"))
    for card in cards:
        if remaining <= 0:
            break
        take = min(card.balance, remaining)
        if take <= 0:
            continue
        allocations.append({"gift_card_id": card.id, "amount": take})
        remaining -= take
    return allocations


@transaction.atomic
def apply_gift_cards_to_order(order: Order, user, requested_amount: Decimal) -> Decimal:
    requested_amount = Decimal(requested_amount or "0.00")
    if requested_amount <= 0:
        order.gift_card_debit = Decimal("0.00")
        order.payable_amount = order.total_price
        order.save(update_fields=["gift_card_debit", "payable_amount"])
        return Decimal("0.00")

    cards = list(active_user_cards_queryset(user).order_by("expires_at", "created_at"))

    remaining = min(requested_amount, order.total_price)
    debited = Decimal("0.00")
    for card in cards:
        if remaining <= 0:
            break
        take = min(card.balance, remaining)
        if take <= 0:
            continue
        card.balance = card.balance - take
        card.save(update_fields=["balance", "updated_at"])
        GiftCardTransaction.objects.create(
            gift_card=card,
            amount=take,
            type=GiftCardTransaction.TxType.DEBIT,
            order=order,
        )
        debited += take
        remaining -= take

    order.gift_card_debit = debited
    order.payable_amount = max(order.total_price - debited, Decimal("0.00"))
    if order.payable_amount == Decimal("0.00"):
        order.status = Order.Status.PAID
        order.save(update_fields=["gift_card_debit", "payable_amount", "status"])
    else:
        order.save(update_fields=["gift_card_debit", "payable_amount"])
    return debited
