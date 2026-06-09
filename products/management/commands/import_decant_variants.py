import re
from collections import defaultdict
from pathlib import Path

import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from products.management.commands.import_praise_variants import (
    find_db_brand,
    match_product_rows,
    pick_best_row,
)
from products.models import Brand, Product, Variant
from products.pricing import parse_wholesale_price, retail_price

DECANT_VOL_RE = re.compile(
    r"^(?P<brand>.+?)\s{2,}(?P<perfume>.+?)\s+(?P<vol>\d+(?:[.,]\d+)?)\s*ml\b",
    re.I,
)
TARGET_VOLUMES = frozenset({"5ml", "10ml"})


def parse_decant_row(raw: str):
    raw = str(raw).strip()
    if "отлив" not in raw.lower():
        return None
    if "atomiser" in raw.lower():
        return None
    m = DECANT_VOL_RE.match(raw)
    if not m:
        return None
    vol = float(m.group("vol").replace(",", "."))
    vol_key = f"{int(vol)}ml" if vol == int(vol) else f"{vol}ml"
    if vol_key not in TARGET_VOLUMES:
        return None
    return m.group("brand").strip(), m.group("perfume").strip(), vol_key


class Command(BaseCommand):
    help = (
        "Добавить/обновить 5ml/10ml отливанты из прайса для товаров в БД"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "file",
            type=str,
            nargs="?",
            default=r"C:\Users\glock\Desktop\Мелкооптовыевпересчетенарубли_Отливанты.xls",
            help="Путь к xls с отливантами",
        )
        parser.add_argument("--dry-run", action="store_true", help="Без записи в БД")
        parser.add_argument(
            "--update",
            action="store_true",
            help="Обновлять цену существующих отливантов",
        )
        parser.add_argument(
            "--stock",
            type=int,
            default=10,
            help="Остаток для новых вариантов",
        )
        parser.add_argument(
            "--min-score",
            type=float,
            default=0.65,
            help="Минимальное совпадение названия (0–1)",
        )
        parser.add_argument(
            "--prune-stale",
            action="store_true",
            help="Удалить 5ml/10ml, которых нет в актуальном прайсе отливантов",
        )

    def handle(self, *args, **options):
        file_path = Path(options["file"])
        if not file_path.exists():
            raise CommandError(f"Файл не найден: {file_path}")

        dry_run = options["dry_run"]
        allow_update = options["update"]
        stock_default = max(int(options["stock"]), 0)
        min_score = float(options["min_score"])
        prune_stale = options["prune_stale"]

        df = pd.read_excel(file_path, sheet_name="TDSheet", engine="xlrd", header=None)

        db_brands = {b.name.lower(): b for b in Brand.objects.all()}
        db_brands_slug = {b.slug: b for b in Brand.objects.all()}

        decants_by_brand = defaultdict(list)
        parsed_rows = 0
        for _, row in df.iloc[11:].iterrows():
            if pd.isna(row[6]) or pd.isna(row[15]):
                continue
            item = parse_decant_row(row[6])
            if not item:
                continue
            brand_raw, perfume, vol_key = item
            brand = find_db_brand(brand_raw, db_brands, db_brands_slug)
            wholesale = parse_wholesale_price(row[15])
            if not brand or not perfume or wholesale is None:
                continue
            parsed_rows += 1
            decants_by_brand[brand.slug].append(
                (perfume, vol_key, float(vol_key[:-2]), True, wholesale, str(row[6]).strip())
            )

        existing_variants = {
            (v.product_id, v.volume): v
            for v in Variant.objects.filter(volume__in=TARGET_VOLUMES).only(
                "id", "product_id", "volume", "price", "stock"
            )
        }

        to_create: list[Variant] = []
        to_update: list[Variant] = []
        to_delete: list[int] = []
        matched_products = 0
        skipped_existing = 0

        for product in Product.objects.select_related("brand"):
            cands = decants_by_brand.get(product.brand.slug, [])
            if not cands:
                continue

            matched = match_product_rows(product.name, cands, min_score)
            if not matched:
                continue

            by_volume = defaultdict(list)
            for row in matched:
                by_volume[row[1]].append(row)

            product_hits = 0
            praise_volumes: set[str] = set()
            for volume in sorted(TARGET_VOLUMES, key=lambda v: int(v[:-2])):
                rows = by_volume.get(volume)
                if not rows:
                    continue
                praise_volumes.add(volume)
                best = pick_best_row(rows)
                price = retail_price(best[4])
                key = (product.id, volume)
                existing = existing_variants.get(key)
                if existing is None:
                    to_create.append(
                        Variant(
                            product=product,
                            volume=volume,
                            price=price,
                            stock=stock_default,
                        )
                    )
                    product_hits += 1
                elif allow_update and existing.price != price:
                    existing.price = price
                    to_update.append(existing)
                    product_hits += 1
                elif existing is not None:
                    skipped_existing += 1

            if prune_stale and allow_update and praise_volumes:
                for key, variant in existing_variants.items():
                    if key[0] != product.id:
                        continue
                    if variant.volume not in TARGET_VOLUMES:
                        continue
                    if variant.volume not in praise_volumes:
                        to_delete.append(variant.id)

            if product_hits or praise_volumes:
                matched_products += 1

        self.stdout.write(
            f"Строк отливантов 5/10ml в файле: {parsed_rows}\n"
            f"Товаров в БД: {Product.objects.count()}\n"
            f"Товаров с отливантами: {matched_products}\n"
            f"Пропущено (цена без изменений): {skipped_existing}\n"
            f"Создать вариантов: {len(to_create)}\n"
            f"Обновить цен: {len(to_update)}\n"
            f"Удалить устаревших: {len(to_delete)}"
        )

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDRY-RUN — данные не сохранены"))
            for v in to_create[:8]:
                self.stdout.write(
                    f"  {v.product.brand.name} | {v.product.name} | {v.volume} | {v.price}"
                )
            return

        if not to_create and not to_update and not to_delete:
            self.stdout.write(self.style.NOTICE("Нечего импортировать."))
            return

        with transaction.atomic():
            if to_delete:
                Variant.objects.filter(id__in=to_delete).delete()
            if to_create:
                Variant.objects.bulk_create(to_create, ignore_conflicts=True)
            if to_update:
                Variant.objects.bulk_update(to_update, ["price"])

        self.stdout.write(
            self.style.SUCCESS(
                f"\nГотово: создано {len(to_create)}, обновлено {len(to_update)}, "
                f"удалено {len(to_delete)}."
            )
        )
