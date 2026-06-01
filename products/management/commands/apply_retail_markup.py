from django.core.management.base import BaseCommand
from django.db import transaction

from products.models import Variant
from products.pricing import retail_price


class Command(BaseCommand):
    help = "Применить розничную наценку ко всем вариантам и округлить до 100 ₽"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Без записи в БД")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        variants = list(Variant.objects.only("id", "price"))
        updated = []

        samples = []
        for variant in variants:
            old_price = variant.price
            new_price = retail_price(old_price)
            if new_price != old_price:
                variant.price = new_price
                updated.append(variant)
                if len(samples) < 5:
                    samples.append((old_price, new_price))

        self.stdout.write(
            f"Вариантов всего: {len(variants)}\n"
            f"Изменится цен: {len(updated)}"
        )

        if samples:
            self.stdout.write("\nПримеры:")
            for old_price, new_price in samples:
                self.stdout.write(f"  {old_price} -> {new_price}")

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDRY-RUN — данные не сохранены"))
            return

        if not updated:
            self.stdout.write(self.style.NOTICE("Все цены уже с наценкой."))
            return

        with transaction.atomic():
            Variant.objects.bulk_update(updated, ["price"], batch_size=500)

        self.stdout.write(
            self.style.SUCCESS(f"\nГотово: обновлено {len(updated)} вариантов.")
        )
