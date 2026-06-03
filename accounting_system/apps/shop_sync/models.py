"""Unmanaged model — read-only mirror of ``products_order`` (same-server MySQL only)."""
from decimal import Decimal

from django.db import models

from .order_data import ShopOrderData

SYNC_FIELDS = (
    "id", "email", "first_name", "last_name", "phone", "status",
    "total_price", "gift_card_debit", "payable_amount", "created_at",
)


class ShopOrder(models.Model):
    email = models.EmailField()
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=32)
    status = models.CharField(max_length=32)
    total_price = models.DecimalField(max_digits=12, decimal_places=2)
    gift_card_debit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    payable_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "products_order"
        ordering = ["-created_at"]

    @classmethod
    def sync_queryset(cls, using="shop"):
        return cls.objects.using(using).only(*SYNC_FIELDS)

    def to_order_data(self) -> ShopOrderData:
        return ShopOrderData(
            id=self.pk,
            email=self.email,
            first_name=self.first_name,
            last_name=self.last_name,
            phone=self.phone,
            status=self.status,
            total_price=self.total_price,
            gift_card_debit=self.gift_card_debit or Decimal("0"),
            payable_amount=self.payable_amount or Decimal("0"),
            created_at=self.created_at,
        )
