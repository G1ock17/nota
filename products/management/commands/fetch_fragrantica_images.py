import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from products.fragrantica_images import (
    find_fragrantica_url,
    resolve_fragrantica_id,
    save_product_thumbnail,
)
from products.models import Product


class Command(BaseCommand):
    help = (
        "Скачивает недостающие фото с fimgs.net по ID из URL Fragrantica "
        "(need_products.json или встроенные переопределения slug→id)"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            type=str,
            default="need_products.json",
            help="JSON с полем url для сопоставления slug→Fragrantica ID",
        )
        parser.add_argument(
            "--slug",
            type=str,
            default="",
            help="Обработать только один товар (slug)",
        )
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Заменить существующие изображения",
        )
        parser.add_argument(
            "--all-products",
            action="store_true",
            help="Не только без фото, а все товары из JSON/переопределений",
        )

    def handle(self, *args, **options):
        json_path = Path(options["json"])
        if not json_path.exists():
            raise CommandError(f"JSON не найден: {json_path}")

        with json_path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, list):
            raise CommandError("Ожидался JSON-массив.")

        only_slug = (options["slug"] or "").strip()
        replace = bool(options["replace"])
        all_products = bool(options["all_products"])

        qs = Product.objects.all()
        if only_slug:
            qs = qs.filter(slug=only_slug)
        elif not all_products:
            qs = qs.annotate(image_count=Count("images")).filter(image_count=0)

        products = list(qs.order_by("slug"))
        if not products:
            self.stdout.write(self.style.WARNING("Нет товаров для обработки."))
            return

        attached = 0
        skipped_has_image = 0
        no_id = 0
        failed = 0

        for product in products:
            if product.images.exists() and not replace:
                skipped_has_image += 1
                continue

            perfume_id = resolve_fragrantica_id(product.slug, product.name, raw)
            if not perfume_id:
                no_id += 1
                if int(options.get("verbosity", 1)) >= 2:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Нет Fragrantica ID: {product.slug} ({product.name})"
                        )
                    )
                continue

            try:
                save_product_thumbnail(product, perfume_id, replace=replace)
                attached += 1
                if int(options.get("verbosity", 1)) >= 2:
                    url_hint = find_fragrantica_url(product.slug, product.name, raw) or ""
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"OK {product.slug} <- id {perfume_id}"
                            + (f" ({url_hint})" if url_hint else "")
                        )
                    )
            except RuntimeError as exc:
                failed += 1
                self.stdout.write(self.style.ERROR(f"FAIL {product.slug}: {exc}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"\nГотово: загружено {attached}, "
                f"уже с фото {skipped_has_image}, "
                f"без ID {no_id}, ошибок {failed}."
            )
        )
