"""Invoice business logic: numbering, totals, paid→transaction link."""
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction as db_transaction
from django.db.models import Max
from django.utils import timezone

TWO = Decimal("0.01")


def next_invoice_number(organization) -> str:
    """Generate INV-<year>-NNNN scoped to the organization."""
    year = timezone.localdate().year
    prefix = f"INV-{year}-"
    last = (
        organization.invoice_set.filter(number__startswith=prefix)
        .aggregate(m=Max("number"))
        .get("m")
    )
    seq = 1
    if last:
        try:
            seq = int(last.split("-")[-1]) + 1
        except (ValueError, IndexError):
            seq = organization.invoice_set.filter(number__startswith=prefix).count() + 1
    return f"{prefix}{seq:04d}"


def recalc_invoice(invoice) -> None:
    """Recompute subtotal/tax/total from line items and persist."""
    subtotal = sum((item.amount for item in invoice.items.all()), Decimal("0.00"))
    subtotal = subtotal.quantize(TWO, rounding=ROUND_HALF_UP)
    rate = invoice.tax_rate or Decimal("0")
    tax = (subtotal * rate / Decimal("100")).quantize(TWO, rounding=ROUND_HALF_UP)
    invoice.subtotal = subtotal
    invoice.tax_amount = tax
    invoice.total = (subtotal + tax).quantize(TWO, rounding=ROUND_HALF_UP)
    invoice.save(update_fields=["subtotal", "tax_amount", "total", "updated_at"])


@db_transaction.atomic
def mark_invoice_paid(invoice, user=None):
    """Mark invoice PAID, set paid_date, and create a linked INCOME transaction.

    Idempotent: re-marking an already-paid invoice does not duplicate.
    """
    from apps.categories.models import Category
    from apps.transactions.models import Transaction

    if invoice.status == invoice.Status.PAID:
        return invoice

    invoice.status = invoice.Status.PAID
    invoice.paid_date = timezone.localdate()
    invoice.save(update_fields=["status", "paid_date", "updated_at"])

    if not invoice.transactions.exists():
        category, _ = Category.objects.get_or_create(
            organization=invoice.organization,
            name="Оплата по счетам",
            type=Category.Type.INCOME,
            defaults={"color": "#10b981", "icon": "file-check"},
        )
        Transaction.objects.create(
            organization=invoice.organization,
            type=Transaction.Type.INCOME,
            amount=invoice.total,
            currency=invoice.currency,
            category=category,
            client=invoice.client,
            invoice=invoice,
            date=timezone.localdate(),
            description=f"Оплата по счёту {invoice.number}",
            created_by=user,
        )
    return invoice


def set_invoice_status(invoice, status, user=None):
    """Apply a status transition; PAID routes through mark_invoice_paid."""
    if status == invoice.Status.PAID:
        return mark_invoice_paid(invoice, user=user)
    invoice.status = status
    fields = ["status", "updated_at"]
    if status != invoice.Status.PAID:
        invoice.paid_date = None
        fields.append("paid_date")
    invoice.save(update_fields=fields)
    return invoice
