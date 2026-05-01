import logging
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from yookassa import Configuration, Payment

from .models import Order

logger = logging.getLogger(__name__)


def is_yookassa_configured() -> bool:
    sid = (getattr(settings, "YOOKASSA_SHOP_ID", None) or "").strip()
    key = (getattr(settings, "YOOKASSA_SECRET_KEY", None) or "").strip()
    return bool(sid and key)


def _configure() -> None:
    Configuration.configure(
        str(settings.YOOKASSA_SHOP_ID).strip(),
        str(settings.YOOKASSA_SECRET_KEY).strip(),
    )


def create_redirect_payment(order, return_url: str):
    """
    Создаёт платёж в ЮKassa с подтверждением redirect.
    Возвращает объект ответа API (у него есть .id, .status, .confirmation).
    """
    _configure()
    value = format(order.payable_amount.quantize(Decimal("0.01")), "f")
    body = {
        "amount": {"value": value, "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": return_url},
        "capture": True,
        "description": f"Заказ №{order.pk} — nota",
        "metadata": {"order_id": str(order.pk)},
    }
    return Payment.create(body, str(uuid.uuid4()))


def fetch_payment(payment_id: str):
    _configure()
    return Payment.find_one(payment_id)


def try_mark_order_paid(order: Order, payment) -> bool:
    """
    Если платёж в ЮKassa успешен и совпадает с заказом (id, metadata, сумма) —
    выставляет заказу status=PAID. Идемпотентно (повторные вызовы безопасны).
    """
    pid = getattr(payment, "id", None) or ""
    if not order.yookassa_payment_id or str(pid) != str(order.yookassa_payment_id):
        return False
    status = (getattr(payment, "status", None) or "").strip()
    if status != "succeeded":
        return False

    raw_meta = getattr(payment, "metadata", None)
    meta = raw_meta if isinstance(raw_meta, dict) else {}
    if str(meta.get("order_id", "")) != str(order.pk):
        logger.warning("ЮKassa: metadata order_id не совпадает с заказом %s", order.pk)
        return False

    amt = getattr(payment, "amount", None)
    if amt is None or getattr(amt, "value", None) is None:
        return False
    try:
        paid_value = Decimal(str(amt.value))
    except Exception:
        return False
    if paid_value != order.payable_amount.quantize(Decimal("0.01")):
        logger.warning("ЮKassa: сумма платежа не совпадает с заказом %s", order.pk)
        return False

    with transaction.atomic():
        locked = Order.objects.select_for_update().filter(pk=order.pk).first()
        if not locked:
            return False
        if locked.status == Order.Status.PAID:
            return True
        locked.status = Order.Status.PAID
        locked.save(update_fields=["status"])
    return True
