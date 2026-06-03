"""Fetch paid orders from the shop site over HTTPS (no remote MySQL)."""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from datetime import date
from decimal import Decimal

from django.conf import settings

from .order_data import PAID_STATUSES, ShopOrderData


def http_sync_configured() -> bool:
    return bool(getattr(settings, "SHOP_SYNC_URL", "").strip())


def fetch_orders_from_api(*, since: date | None = None) -> tuple[list[ShopOrderData], str | None]:
    """Return (orders, error_message). error_message is set on failure."""
    url = getattr(settings, "SHOP_SYNC_URL", "").strip().rstrip("/")
    token = getattr(settings, "SHOP_SYNC_TOKEN", "").strip()
    if not url or not token:
        return [], "Задайте SHOP_SYNC_URL и SHOP_SYNC_TOKEN в .env учётной системы."

    params = []
    if since:
        params.append(f"since={since.isoformat()}")
    if params:
        url = f"{url}?{'&'.join(params)}"

    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "X-Accounting-Token": token,
            "User-Agent": "AccordAccounting/1.0",
        },
        method="GET",
    )
    timeout = int(getattr(settings, "SHOP_SYNC_TIMEOUT", 30))

    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:200]
        return [], f"HTTP {exc.code} от магазина: {body or exc.reason}"
    except urllib.error.URLError as exc:
        return [], f"Не удалось связаться с магазином: {exc.reason}"
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        return [], f"Некорректный ответ API магазина: {exc}"

    if not payload.get("ok"):
        return [], payload.get("error") or "API магазина вернул ошибку."

    orders: list[ShopOrderData] = []
    for row in payload.get("orders", []):
        try:
            order = ShopOrderData.from_api_row(row)
        except (KeyError, ValueError, TypeError):
            continue
        if order.status in PAID_STATUSES and order.revenue_amount > 0:
            orders.append(order)
    return orders, None
