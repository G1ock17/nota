import csv
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from products.models import Product, ProductImage


class Command(BaseCommand):
    help = "Импорт локальных изображений товаров из CSV (product_slug,image_path,is_main,...)"

    def add_arguments(self, parser):
        parser.add_argument(
            "csv_file",
            type=str,
            help="Путь к CSV-файлу (например: product_images.csv)",
        )
        parser.add_argument(
            "--base-dir",
            type=str,
            default=".",
            help="Базовая директория для относительных путей image_path (по умолчанию: .)",
        )
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Удалять существующие изображения товара перед импортом (рекомендуется для повторного запуска).",
        )

    def handle(self, *args, **options):
        csv_path = Path(options["csv_file"]).resolve()
        base_dir = Path(options["base_dir"]).resolve()
        replace_existing = bool(options["replace"])
        verbosity = int(options.get("verbosity", 1))

        if not csv_path.exists():
            raise CommandError(f"CSV-файл не найден: {csv_path}")
        if not base_dir.exists():
            raise CommandError(f"Базовая директория не найдена: {base_dir}")

        created = 0
        missing_products = 0
        missing_files = 0
        invalid_rows = 0
        replaced_products = set()

        with csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            required = {"product_slug", "image_path"}
            if not required.issubset(set(reader.fieldnames or [])):
                raise CommandError(
                    f"CSV должен содержать колонки: {', '.join(sorted(required))}. "
                    f"Найдено: {reader.fieldnames}"
                )

            for row_idx, row in enumerate(reader, start=2):
                slug = (row.get("product_slug") or "").strip()
                raw_image_path = (row.get("image_path") or "").strip()
                is_main_raw = (row.get("is_main") or "").strip().lower()

                if not slug or not raw_image_path:
                    invalid_rows += 1
                    if verbosity >= 2:
                        self.stdout.write(
                            self.style.WARNING(
                                f"[row {row_idx}] Пропуск: пустой product_slug или image_path"
                            )
                        )
                    continue

                product = Product.objects.filter(slug=slug).first()
                if product is None:
                    missing_products += 1
                    if verbosity >= 2:
                        self.stdout.write(
                            self.style.WARNING(
                                f"[row {row_idx}] Товар не найден по slug='{slug}'"
                            )
                        )
                    continue

                image_path = Path(raw_image_path)
                absolute_image_path = image_path if image_path.is_absolute() else (base_dir / image_path)
                absolute_image_path = absolute_image_path.resolve()
                if not absolute_image_path.exists() or not absolute_image_path.is_file():
                    missing_files += 1
                    if verbosity >= 2:
                        self.stdout.write(
                            self.style.WARNING(
                                f"[row {row_idx}] Файл не найден: {absolute_image_path}"
                            )
                        )
                    continue

                if replace_existing and product.id not in replaced_products:
                    with transaction.atomic():
                        product.images.all().delete()
                    replaced_products.add(product.id)

                is_main = is_main_raw in {"1", "true", "yes", "y"}
                filename = f"{slug}-{created + 1}{absolute_image_path.suffix.lower()}"

                with absolute_image_path.open("rb") as image_f:
                    image_obj = ProductImage(product=product, is_main=is_main)
                    image_obj.image.save(filename, File(image_f), save=True)
                    created += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Импорт изображений завершён: "
                f"создано {created}, "
                f"товары не найдены {missing_products}, "
                f"файлы не найдены {missing_files}, "
                f"некорректные строки {invalid_rows}."
            )
        )
