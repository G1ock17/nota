import decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0008_favorite"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="gift_card_debit",
            field=models.DecimalField(
                decimal_places=2,
                default=decimal.Decimal("0.00"),
                max_digits=12,
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="payable_amount",
            field=models.DecimalField(
                decimal_places=2,
                default=decimal.Decimal("0.00"),
                max_digits=12,
            ),
        ),
        migrations.CreateModel(
            name="GiftCard",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(db_index=True, max_length=32, unique=True)),
                ("nominal", models.DecimalField(decimal_places=2, max_digits=12)),
                ("balance", models.DecimalField(decimal_places=2, max_digits=12)),
                ("is_activated", models.BooleanField(default=False)),
                ("buyer_email", models.EmailField(blank=True, max_length=254)),
                ("activated_at", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="gift_cards",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="GiftCardTransaction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                (
                    "type",
                    models.CharField(
                        choices=[
                            ("debit", "Списание"),
                            ("credit", "Пополнение"),
                            ("purchase", "Покупка"),
                            ("activation", "Активация"),
                        ],
                        max_length=16,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "gift_card",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="transactions",
                        to="products.giftcard",
                    ),
                ),
                (
                    "order",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="gift_card_transactions",
                        to="products.order",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="giftcardtransaction",
            constraint=models.UniqueConstraint(
                condition=models.Q(order__isnull=False, type="debit"),
                fields=("gift_card", "order", "type"),
                name="unique_gift_card_debit_per_order",
            ),
        ),
    ]
