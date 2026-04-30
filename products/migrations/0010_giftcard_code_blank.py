from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0009_gift_cards"),
    ]

    operations = [
        migrations.AlterField(
            model_name="giftcard",
            name="code",
            field=models.CharField(blank=True, db_index=True, max_length=32, unique=True),
        ),
    ]
