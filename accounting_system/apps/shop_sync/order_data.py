"""Normalized order row for accounting sync (MySQL or HTTP API)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


PAID_STATUSES = frozenset({"paid", "assembling", "shipped", "delivered"})

STATUS_LABELS = {
    "new": "Новый",
    "paid": "Оплачен",
    "assembling": "В сборке",
    "shipped": "Отправлен",
    "delivered": "Доставлен",
}


@dataclass(frozen=True)
class ShopOrderData:
    id: int
    email: str
    first_name: str
    last_name: str
    phone: str
    status: str
    total_price: Decimal
    gift_card_debit: Decimal
    payable_amount: Decimal
    created_at: datetime

    @property
    def revenue_amount(self) -> Decimal:
        if self.total_price and self.total_price > 0:
            return self.total_price
        return (self.payable_amount or Decimal("0")) + (self.gift_card_debit or Decimal("0"))

    @property
    def client_label(self) -> str:
        name = f"{self.first_name} {self.last_name}".strip()
        return name or self.email

    @property
    def status_display(self) -> str:
        return STATUS_LABELS.get(self.status, self.status)

    def accounting_notes(self) -> str:
        parts = [f"Импорт с сайта Accord, заказ #{self.id}."]
        if self.gift_card_debit and self.gift_card_debit > 0:
            parts.append(f"Сертификат: {self.gift_card_debit} ₽.")
        if self.payable_amount and self.payable_amount > 0:
            parts.append(f"Оплата: {self.payable_amount} ₽.")
        return " ".join(parts)

    @classmethod
    def from_api_row(cls, row: dict) -> ShopOrderData:
        created = row["created_at"]
        if isinstance(created, str):
            created = datetime.fromisoformat(created.replace("Z", "+00:00"))
        return cls(
            id=int(row["id"]),
            email=row.get("email") or "",
            first_name=row.get("first_name") or "",
            last_name=row.get("last_name") or "",
            phone=row.get("phone") or "",
            status=row["status"],
            total_price=Decimal(str(row.get("total_price") or "0")),
            gift_card_debit=Decimal(str(row.get("gift_card_debit") or "0")),
            payable_amount=Decimal(str(row.get("payable_amount") or "0")),
            created_at=created,
        )
