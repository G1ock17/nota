from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0005_product_country_product_year"),
    ]

    operations = [
        migrations.AlterField(
            model_name="variant",
            name="volume",
            field=models.CharField(max_length=32),
        ),
    ]
