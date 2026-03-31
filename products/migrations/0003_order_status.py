from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0002_order_orderitem"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="status",
            field=models.CharField(
                choices=[
                    ("new", "Новый"),
                    ("processing", "В обработке"),
                    ("shipped", "Отправлен"),
                    ("delivered", "Доставлен"),
                    ("cancelled", "Отменен"),
                ],
                default="new",
                max_length=32,
            ),
        ),
    ]
