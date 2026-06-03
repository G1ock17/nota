from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from apps.clients.models import Client
from apps.core.models import OrganizationOwned, TimeStampedModel


class Invoice(TimeStampedModel, OrganizationOwned):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Черновик"
        SENT = "SENT", "Отправлен"
        PAID = "PAID", "Оплачен"
        OVERDUE = "OVERDUE", "Просрочен"
        CANCELLED = "CANCELLED", "Отменён"

    number = models.CharField(max_length=32, unique=True)
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="invoices")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    issue_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField()
    paid_date = models.DateField(null=True, blank=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("20.00"))
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=3, default="RUB")
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="invoices_created",
    )

    class Meta:
        ordering = ["-issue_date", "-number"]

    def __str__(self) -> str:
        return self.number

    def get_absolute_url(self):
        return reverse("invoices:detail", kwargs={"pk": self.pk})

    @property
    def is_overdue(self) -> bool:
        return (
            self.status in {self.Status.SENT, self.Status.OVERDUE}
            and self.due_date < timezone.localdate()
        )


class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=255)
    qty = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("1.00"))
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        self.amount = (self.qty or Decimal("0")) * (self.unit_price or Decimal("0"))
        super().save(*args, **kwargs)
