"""Import paid shop orders as INCOME transactions (HTTP API or same-server MySQL)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.conf import settings
from django.db import connections
from django.utils import timezone

from apps.categories.models import Category
from apps.clients.models import Client
from apps.transactions.models import Transaction

from .http_client import fetch_orders_from_api, http_sync_configured
from .models import ShopOrder
from .order_data import PAID_STATUSES, ShopOrderData

SOURCE = "accord_shop"
SALES_CATEGORY = "Продажи с сайта"


@dataclass
class SyncResult:
    created: int = 0
    skipped: int = 0
    errors: list[str] | None = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


def shop_db_configured() -> bool:
    return "shop" in settings.DATABASES


def sync_mode() -> str:
    if http_sync_configured():
        return "http"
    if shop_db_configured():
        return "mysql"
    return ""


def test_shop_connection() -> tuple[bool, str]:
    mode = sync_mode()
    if mode == "http":
        orders, err = fetch_orders_from_api()
        if err:
            return False, err
        return True, f"API магазина доступен (найдено оплаченных заказов: {len(orders)})."
    if mode == "mysql":
        try:
            with connections["shop"].cursor() as cur:
                cur.execute("SELECT 1")
            ShopOrder.sync_queryset().exists()
            return True, "Подключение к БД магазина (localhost) успешно."
        except Exception as exc:
            return False, f"Ошибка подключения к БД магазина: {exc}"
    return False, (
        "Синхронизация не настроена. Укажите SHOP_SYNC_URL + SHOP_SYNC_TOKEN "
        "(рекомендуется) или SHOP_DB_* (только на сервере с localhost MySQL)."
    )


def _sales_category(organization):
    cat, _ = Category.objects.get_or_create(
        organization=organization,
        name=SALES_CATEGORY,
        type=Category.Type.INCOME,
        defaults={"color": "#10b981", "icon": "shopping-bag"},
    )
    return cat


def _client_for_order(organization, order: ShopOrderData) -> Client:
    label = order.client_label
    client = Client.objects.filter(organization=organization, email__iexact=order.email).first()
    if client:
        if not client.name or client.name == order.email:
            client.name = label
            client.phone = order.phone or client.phone
            client.save(update_fields=["name", "phone", "updated_at"])
        return client
    return Client.objects.create(
        organization=organization,
        name=label,
        email=order.email,
        phone=order.phone or "",
        type=Client.Type.INDIVIDUAL,
    )


def _iter_orders(since: date | None) -> tuple[list[ShopOrderData], str | None]:
    if http_sync_configured():
        return fetch_orders_from_api(since=since)

    if not shop_db_configured():
        return [], "Синхронизация не настроена."

    qs = ShopOrder.sync_queryset().filter(status__in=PAID_STATUSES)
    if since:
        qs = qs.filter(created_at__date__gte=since)
    return [row.to_order_data() for row in qs.iterator()], None


def _import_order_list(
    organization,
    orders: list[ShopOrderData],
    *,
    dry_run: bool = False,
    created_by=None,
) -> SyncResult:
    """Create income transactions from parsed orders (idempotent by order id)."""
    result = SyncResult()
    category = _sales_category(organization)
    existing = set(
        Transaction.objects.filter(
            organization=organization,
            external_source=SOURCE,
        ).values_list("external_id", flat=True)
    )

    for order in orders:
        ext_id = str(order.id)
        if ext_id in existing:
            result.skipped += 1
            continue

        amount = order.revenue_amount
        if amount <= 0:
            result.skipped += 1
            continue

        if dry_run:
            result.created += 1
            continue

        client = _client_for_order(organization, order)
        tx_date = timezone.localdate(order.created_at)
        desc = f"Заказ #{order.id} — {order.status_display}"

        Transaction.objects.create(
            organization=organization,
            type=Transaction.Type.INCOME,
            amount=amount,
            currency="RUB",
            category=category,
            client=client,
            date=tx_date,
            description=desc[:255],
            notes=order.accounting_notes(),
            external_source=SOURCE,
            external_id=ext_id,
            created_by=created_by,
        )
        result.created += 1
        existing.add(ext_id)

    return result


def import_shop_orders_from_file(
    organization,
    file_obj,
    filename: str,
    *,
    dry_run: bool = False,
    created_by=None,
) -> SyncResult:
    """Import orders from CSV/Excel export (phpMyAdmin)."""
    from .file_import import parse_orders_file

    result = SyncResult()
    try:
        orders, row_errors = parse_orders_file(file_obj, filename)
    except ValueError as exc:
        result.errors.append(str(exc))
        return result

    result.errors.extend(row_errors[:20])
    if len(row_errors) > 20:
        result.errors.append(f"… и ещё {len(row_errors) - 20} строк с ошибками")

    if not orders and not row_errors:
        result.errors.append("В файле не найдено строк с данными.")
        return result

    imported = _import_order_list(
        organization, orders, dry_run=dry_run, created_by=created_by,
    )
    result.created = imported.created
    result.skipped = imported.skipped
    return result


def sync_shop_orders(
    organization,
    *,
    since: date | None = None,
    dry_run: bool = False,
    created_by=None,
) -> SyncResult:
    result = SyncResult()
    orders, err = _iter_orders(since)
    if err:
        result.errors.append(err)
        return result

    imported = _import_order_list(
        organization, orders, dry_run=dry_run, created_by=created_by,
    )
    result.created = imported.created
    result.skipped = imported.skipped
    return result
