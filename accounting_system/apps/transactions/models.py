from django.conf import settings
from django.db import models

from apps.categories.models import Category
from apps.clients.models import Client
from apps.core.models import OrganizationOwned, TimeStampedModel


class Transaction(TimeStampedModel, OrganizationOwned):
    class Type(models.TextChoices):
        INCOME = "INCOME", "Доход"
        EXPENSE = "EXPENSE", "Расход"
        TRANSFER = "TRANSFER", "Перевод"

    type = models.CharField(max_length=10, choices=Type.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="RUB")
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="transactions"
    )
    client = models.ForeignKey(
        Client, null=True, blank=True, on_delete=models.SET_NULL, related_name="transactions"
    )
    invoice = models.ForeignKey(
        "invoices.Invoice", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="transactions",
    )
    date = models.DateField()
    description = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="transactions_created",
    )
    # Idempotent import from external systems (e.g. Accord shop orders).
    external_source = models.CharField(max_length=32, blank=True, default="")
    external_id = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        ordering = ["-date", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "external_source", "external_id"],
                condition=models.Q(external_source__gt=""),
                name="unique_external_tx_per_org",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_type_display()} {self.amount} {self.currency}"

    @property
    def signed_amount(self):
        return -self.amount if self.type == self.Type.EXPENSE else self.amount
