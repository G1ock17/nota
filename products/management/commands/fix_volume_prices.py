from django.core.management.base import BaseCommand
from django.db import transaction

from products.models import Product, Variant
from products.pricing import enforce_monotonic_volume_prices


class Command(BaseCommand):
    help = "Исправить цены: больший объём не может стоить меньше меньшего"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        to_update = []
        examples = []

        for product in Product.objects.prefetch_related("variants"):
            variants = list(product.variants.all())
            if len(variants) < 2:
                continue
            before = {variant.id: variant.price for variant in variants}
            changed = enforce_monotonic_volume_prices(variants)
            for variant in changed:
                if variant.price != before[variant.id]:
                    to_update.append(variant)
                    if len(examples) < 5:
                        examples.append((product, variant, before[variant.id]))

        self.stdout.write(f"Исправить вариантов: {len(to_update)}")
        if examples:
            self.stdout.write("Примеры:")
            for product, variant, old_price in examples:
                self.stdout.write(
                    f"  {product.brand.name} | {product.name} | "
                    f"{variant.volume}: {old_price} -> {variant.price}"
                )

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY-RUN — данные не сохранены"))
            return

        if not to_update:
            self.stdout.write(self.style.NOTICE("Нечего исправлять."))
            return

        with transaction.atomic():
            Variant.objects.bulk_update(to_update, ["price"], batch_size=500)

        self.stdout.write(
            self.style.SUCCESS(f"Готово: обновлено {len(to_update)} вариантов.")
        )
