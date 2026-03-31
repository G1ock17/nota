from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0003_order_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="tracking_number",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AlterField(
            model_name="order",
            name="status",
            field=models.CharField(
                choices=[
                    ("new", "Новый"),
                    ("paid", "Оплачен"),
                    ("assembling", "В сборке"),
                    ("shipped", "Отправлен"),
                    ("delivered", "Доставлен"),
                ],
                default="new",
                max_length=32,
            ),
        ),
    ]
