"""Idempotent demo data seeder.

Usage: python manage.py seed_demo
Creates an organization, an owner superuser (admin/admin12345), default
categories, a few clients, sample transactions and one invoice.
"""
import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Membership
from apps.categories.models import Category
from apps.clients.models import Client
from apps.core.models import Organization
from apps.invoices.models import Invoice, InvoiceItem
from apps.invoices.services import next_invoice_number, recalc_invoice
from apps.transactions.models import Transaction

User = get_user_model()

DEFAULT_CATEGORIES = [
    ("Выручка от услуг", "INCOME", "#10b981", "trending-up"),
    ("Продажа товаров", "INCOME", "#22c55e", "shopping-cart"),
    ("Зарплата", "EXPENSE", "#ef4444", "users"),
    ("Аренда", "EXPENSE", "#f97316", "home"),
    ("Налоги", "EXPENSE", "#eab308", "landmark"),
    ("Маркетинг", "EXPENSE", "#8b5cf6", "megaphone"),
]


class Command(BaseCommand):
    help = "Seed demo data (idempotent)."

    @transaction.atomic
    def handle(self, *args, **options):
        org, _ = Organization.objects.get_or_create(
            slug="demo", defaults={"name": "Демо-организация", "currency": "RUB"}
        )

        owner = User.objects.filter(is_superuser=True).first()
        if owner is None:
            owner = User.objects.create_superuser(
                "admin", "admin@example.com", "admin12345"
            )
            self.stdout.write(self.style.SUCCESS("Создан суперпользователь admin / admin12345"))

        Membership.objects.get_or_create(
            user=owner, organization=org, defaults={"role": Membership.Role.OWNER}
        )

        cats = {}
        for name, ctype, color, icon in DEFAULT_CATEGORIES:
            cat, _ = Category.objects.get_or_create(
                organization=org, name=name, type=ctype,
                defaults={"color": color, "icon": icon},
            )
            cats[name] = cat

        clients = []
        for name, ctype in [("ООО Ромашка", "COMPANY"), ("ИП Иванов", "INDIVIDUAL"),
                            ("АО Север", "COMPANY")]:
            client, _ = Client.objects.get_or_create(
                organization=org, name=name, defaults={"type": ctype}
            )
            clients.append(client)

        if not Transaction.objects.filter(organization=org).exists():
            today = timezone.localdate()
            income_cats = [c for c in cats.values() if c.type == "INCOME"]
            expense_cats = [c for c in cats.values() if c.type == "EXPENSE"]
            for i in range(60):
                day = today - timedelta(days=random.randint(0, 330))
                if random.random() < 0.5:
                    cat = random.choice(income_cats)
                    ttype, amount = "INCOME", Decimal(random.randint(15000, 250000))
                else:
                    cat = random.choice(expense_cats)
                    ttype, amount = "EXPENSE", Decimal(random.randint(3000, 120000))
                Transaction.objects.create(
                    organization=org, type=ttype, amount=amount, currency="RUB",
                    category=cat, client=random.choice(clients), date=day,
                    description=f"Операция #{i + 1}", created_by=owner,
                )
            self.stdout.write(self.style.SUCCESS("Создано 60 демо-транзакций"))

        if not Invoice.objects.filter(organization=org).exists():
            inv = Invoice.objects.create(
                organization=org, client=clients[0], status="SENT",
                number=next_invoice_number(org),
                due_date=timezone.localdate() + timedelta(days=14),
                tax_rate=Decimal("20.00"), currency="RUB", created_by=owner,
            )
            InvoiceItem.objects.create(invoice=inv, name="Консультация", qty=Decimal("10"),
                                       unit_price=Decimal("5000"))
            InvoiceItem.objects.create(invoice=inv, name="Внедрение", qty=Decimal("1"),
                                       unit_price=Decimal("80000"))
            recalc_invoice(inv)
            self.stdout.write(self.style.SUCCESS(f"Создан счёт {inv.number}"))

        self.stdout.write(self.style.SUCCESS("Демо-данные готовы."))
