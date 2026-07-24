from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0012_brand_featured_brand_origin_brand_tags_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="order",
            old_name="yookassa_payment_id",
            new_name="ozon_pay_order_id",
        ),
        migrations.AlterField(
            model_name="order",
            name="ozon_pay_order_id",
            field=models.CharField(
                blank=True,
                default="",
                max_length=64,
                verbose_name="Заказ Ozon Pay",
            ),
        ),
    ]
