from django.core.management.base import BaseCommand
from django.db import transaction

from products.display_names import strip_brand_prefix
from products.models import Product


class Command(BaseCommand):
    help = "Убирает имя бренда из начала названия аромата (в поле name)"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Только показать изменения")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        updated = 0
        unchanged = 0
        samples: list[str] = []

        qs = Product.objects.select_related("brand").order_by("id")
        with transaction.atomic():
            for product in qs.iterator(chunk_size=500):
                brand_name = product.brand.name if product.brand_id else ""
                new_name = strip_brand_prefix(product.name, brand_name)
                if new_name == product.name:
                    unchanged += 1
                    continue
                if len(samples) < 12:
                    samples.append(f"  {product.name!r} -> {new_name!r}")
                if not dry_run:
                    product.name = new_name
                    product.save(update_fields=["name"])
                updated += 1

            if dry_run:
                transaction.set_rollback(True)

        for line in samples:
            self.stdout.write(line)
        if updated > len(samples):
            self.stdout.write(f"  ... и ещё {updated - len(samples)}")

        prefix = "DRY-RUN: " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Обновлено: {updated}, без изменений: {unchanged}"
            )
        )
