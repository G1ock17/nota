import hashlib
import json
import logging
from decimal import Decimal
from typing import Any

import requests
from django.conf import settings
from django.db import transaction

from .models import Order

logger = logging.getLogger(__name__)

RUB_CURRENCY_CODE = "643"
PAID_ORDER_STATUSES = frozenset(
    {
        "STATUS_PAID",
        "STATUS_SUCCESS",
        "STATUS_COMPLETED",
        "STATUS_AUTHORIZED",
    }
)
PAID_PAYMENT_STATUSES = frozenset({"PAYMENT_CONFIRMED", "PAYMENT_AUTHORIZED"})


def is_ozon_pay_configured() -> bool:
    access_key = (getattr(settings, "OZON_PAY_ACCESS_KEY", None) or "").strip()
    secret_key = (getattr(settings, "OZON_PAY_SECRET_KEY", None) or "").strip()
    return bool(access_key and secret_key)


def _access_key() -> str:
    return str(settings.OZON_PAY_ACCESS_KEY).strip()


def _secret_key() -> str:
    return str(settings.OZON_PAY_SECRET_KEY).strip()


def _notification_secret() -> str:
    return str(getattr(settings, "OZON_PAY_NOTIFICATION_SECRET", "") or "").strip()


def _api_base_url() -> str:
    return (getattr(settings, "OZON_PAY_API_BASE_URL", None) or "https://payapi.ozon.ru").rstrip("/")


def _payment_algorithm() -> str:
    return (getattr(settings, "OZON_PAY_PAYMENT_ALGORITHM", None) or "PAY_ALGO_SMS").strip()


def _fiscalization_type() -> str:
    return (getattr(settings, "OZON_PAY_FISCALIZATION_TYPE", None) or "FISCAL_TYPE_SINGLE").strip()


def _default_vat() -> str:
    return (getattr(settings, "OZON_PAY_VAT", None) or "VAT_NONE").strip()


def _enable_fiscalization() -> bool:
    raw = getattr(settings, "OZON_PAY_ENABLE_FISCALIZATION", "true")
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in ("1", "true", "yes")


def _amount_dict(amount: Decimal) -> dict[str, str]:
    value = format(amount.quantize(Decimal("0.01")), "f")
    return {"currencyCode": RUB_CURRENCY_CODE, "value": value}


def _canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def compute_request_sign(payload: dict[str, Any]) -> str:
    """
    Подпись исходящего запроса к API Ozon Pay (SHA-256 от JSON-тела без requestSign + secretKey).
    """
    unsigned = {k: v for k, v in payload.items() if k != "requestSign"}
    digest = _canonical_json(unsigned) + _secret_key()
    return hashlib.sha256(digest.encode("utf-8")).hexdigest()


def _signed_payload(payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(payload)
    payload["requestSign"] = compute_request_sign(payload)
    return payload


def _api_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{_api_base_url()}{path}"
    body = _signed_payload(payload)
    response = requests.post(
        url,
        json=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        timeout=int(getattr(settings, "OZON_PAY_TIMEOUT", 30) or 30),
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Ответ Ozon Pay не является JSON-объектом")
    return data


def _order_items_payload(order: Order) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for idx, line in enumerate(order.items.select_related("variant", "variant__product"), start=1):
        product_name = line.variant.product.display_name
        volume = line.variant.get_volume_display()
        if volume:
            product_name = f"{product_name} ({volume})"
        items.append(
            {
                "extId": f"order-{order.pk}-item-{idx}",
                "name": product_name[:128],
                "price": _amount_dict(line.price),
                "quantity": int(line.quantity),
                "type": "TYPE_PRODUCT",
                "vat": _default_vat(),
                "needMark": False,
            }
        )
    if not items:
        items.append(
            {
                "extId": f"order-{order.pk}-total",
                "name": f"Заказ №{order.pk} — accord",
                "price": _amount_dict(order.payable_amount),
                "quantity": 1,
                "type": "TYPE_PRODUCT",
                "vat": _default_vat(),
                "needMark": False,
            }
        )
    return items


def _extract_pay_link(data: dict[str, Any]) -> str | None:
    for key in ("payLink",):
        if isinstance(data.get(key), str) and data[key].strip():
            return data[key].strip()
    order = data.get("order")
    if isinstance(order, dict):
        for nested_key in ("payLink",):
            if isinstance(order.get(nested_key), str) and order[nested_key].strip():
                return order[nested_key].strip()
        item = order.get("item")
        if isinstance(item, dict):
            link = item.get("payLink")
            if isinstance(link, str) and link.strip():
                return link.strip()
    item = data.get("item")
    if isinstance(item, dict):
        link = item.get("payLink")
        if isinstance(link, str) and link.strip():
            return link.strip()
    return None


def _extract_order_id(data: dict[str, Any]) -> str | None:
    for container_key in ("order", "item", None):
        container = data if container_key is None else data.get(container_key)
        if not isinstance(container, dict):
            continue
        for id_key in ("id",):
            oid = container.get(id_key)
            if oid is not None and str(oid).strip():
                return str(oid).strip()
    return None


def create_redirect_payment(order: Order, success_url: str, fail_url: str, notification_url: str) -> dict[str, Any]:
    """
    Создаёт заказ в Ozon Pay и возвращает ответ API с payLink для редиректа покупателя.
    """
    payload: dict[str, Any] = {
        "accessKey": _access_key(),
        "amount": _amount_dict(order.payable_amount),
        "extId": str(order.pk),
        "mode": "MODE_FULL",
        "enableFiscalization": _enable_fiscalization(),
        "fiscalizationType": _fiscalization_type(),
        "paymentAlgorithm": _payment_algorithm(),
        "items": _order_items_payload(order),
        "successUrl": success_url,
        "failUrl": fail_url,
        "notificationUrl": notification_url,
        "receiptEmail": order.email,
        "extData": {"order_id": str(order.pk)},
    }
    data = _api_post("/v1/createOrder", payload)
    pay_link = _extract_pay_link(data)
    if not pay_link:
        raise ValueError("Ответ Ozon Pay без payLink")
    ozon_order_id = _extract_order_id(data)
    if not ozon_order_id:
        raise ValueError("Ответ Ozon Pay без id заказа")
    data["_pay_link"] = pay_link
    data["_ozon_order_id"] = ozon_order_id
    return data


def fetch_order_details(order: Order) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "accessKey": _access_key(),
        "extId": str(order.pk),
    }
    if order.ozon_pay_order_id:
        payload["id"] = order.ozon_pay_order_id
    return _api_post("/v1/getOrderDetails", payload)


def _amount_matches_order(amount_raw, order: Order) -> bool:
    try:
        if isinstance(amount_raw, int):
            paid = Decimal(amount_raw) / Decimal("100")
        else:
            paid = Decimal(str(amount_raw))
    except Exception:
        return False
    return paid == order.payable_amount.quantize(Decimal("0.01"))


def _order_item_from_details(data: dict[str, Any]) -> dict[str, Any] | None:
    item = data.get("item")
    if isinstance(item, dict):
        return item
    order = data.get("order")
    if isinstance(order, dict):
        nested = order.get("item")
        if isinstance(nested, dict):
            return nested
    return None


def _is_paid_from_details(data: dict[str, Any], order: Order) -> bool:
    item = _order_item_from_details(data)
    if item:
        status = (item.get("status") or "").strip()
        if status in PAID_ORDER_STATUSES:
            remaining = item.get("remainingAmount") or {}
            if isinstance(remaining, dict):
                try:
                    if Decimal(str(remaining.get("value", "0"))) == Decimal("0"):
                        return True
                except Exception:
                    pass
            if status in ("STATUS_PAID", "STATUS_SUCCESS", "STATUS_COMPLETED"):
                return True
    operations = data.get("operations")
    if isinstance(operations, dict):
        op_status = (operations.get("status") or "").strip()
        if op_status in PAID_PAYMENT_STATUSES:
            return _amount_matches_order(
                (operations.get("amount") or {}).get("value"),
                order,
            )
    if isinstance(operations, list):
        for op in operations:
            if not isinstance(op, dict):
                continue
            if (op.get("status") or "").strip() in PAID_PAYMENT_STATUSES:
                amt = op.get("amount") or {}
                if _amount_matches_order(amt.get("value"), order):
                    return True
    return False


def verify_notification_signature(data: dict[str, Any]) -> bool:
    secret = _notification_secret()
    if not secret:
        logger.warning("Ozon Pay webhook: OZON_PAY_NOTIFICATION_SECRET не задан, проверка подписи пропущена")
        return True

    received = (data.get("requestSign") or "").strip()
    if not received:
        return False

    access_key = _access_key()
    order_id = (data.get("orderID") or data.get("orderId") or "").strip()
    ext_order_id = (data.get("extOrderID") or data.get("extOrderId") or "").strip()
    transaction_id = data.get("transactionID")
    transaction_uid = (data.get("transactionUID") or data.get("transactionUid") or "").strip()
    ext_transaction_id = (data.get("extTransactionID") or data.get("extTransactionId") or "").strip()
    amount = data.get("amount")
    currency_code = (data.get("currencyCode") or RUB_CURRENCY_CODE).strip()

    if order_id:
        tx_part = str(transaction_id) if transaction_id is not None else transaction_uid
        ext_part = ext_order_id
    else:
        tx_part = transaction_uid
        ext_part = ext_transaction_id

    digest = (
        f"{access_key}|"
        f"{order_id}|"
        f"{tx_part}|"
        f"{ext_part}|"
        f"{amount}|"
        f"{currency_code}|"
        f"{secret}"
    )
    expected = hashlib.sha256(digest.encode("utf-8")).hexdigest()
    return expected == received


def try_mark_order_paid(order: Order, *, ozon_order_id: str | None = None) -> bool:
    with transaction.atomic():
        locked = Order.objects.select_for_update().filter(pk=order.pk).first()
        if not locked:
            return False
        if locked.status == Order.Status.PAID:
            return True
        if ozon_order_id and locked.ozon_pay_order_id and str(locked.ozon_pay_order_id) != str(ozon_order_id):
            return False
        locked.status = Order.Status.PAID
        update_fields = ["status"]
        if ozon_order_id and not locked.ozon_pay_order_id:
            locked.ozon_pay_order_id = str(ozon_order_id)
            update_fields.append("ozon_pay_order_id")
        locked.save(update_fields=update_fields)
    return True


def try_mark_order_paid_from_details(order: Order, details: dict[str, Any]) -> bool:
    if not _is_paid_from_details(details, order):
        return False
    ozon_order_id = _extract_order_id(details)
    return try_mark_order_paid(order, ozon_order_id=ozon_order_id)


def try_mark_order_paid_from_notification(order: Order, data: dict[str, Any]) -> bool:
    status = (data.get("status") or "").strip()
    operation_type = (data.get("operationType") or "").strip()
    if status != "Completed" or operation_type != "Payment":
        return False
    if not _amount_matches_order(data.get("amount"), order):
        logger.warning("Ozon Pay: сумма в webhook не совпадает с заказом %s", order.pk)
        return False
    ext_order_id = (data.get("extOrderID") or data.get("extOrderId") or "").strip()
    if ext_order_id and str(ext_order_id) != str(order.pk):
        return False
    ozon_order_id = (data.get("orderID") or data.get("orderId") or "").strip() or None
    return try_mark_order_paid(order, ozon_order_id=ozon_order_id)
