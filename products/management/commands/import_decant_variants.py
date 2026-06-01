import re
from collections import defaultdict
from pathlib import Path

import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from products.management.commands.import_praise_variants import (
    find_db_brand,
    norm_text,
    parse_price,
    score_match,
)
from products.models import Brand, Product, Variant
from products.pricing import retail_price

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
        "Добавить 5ml/10ml отливанты из прайса для товаров в БД, "
        "у которых таких объёмов ещё нет"
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

    def handle(self, *args, **options):
        file_path = Path(options["file"])
        if not file_path.exists():
            raise CommandError(f"Файл не найден: {file_path}")

        dry_run = options["dry_run"]
        stock_default = max(int(options["stock"]), 0)
        min_score = float(options["min_score"])

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
            price = parse_price(row[15])
            if not brand or not perfume or price is None:
                continue
            parsed_rows += 1
            decants_by_brand[brand.slug].append(
                (perfume, vol_key, price, str(row[6]).strip())
            )

        existing = {
            (v.product_id, v.volume)
            for v in Variant.objects.filter(volume__in=TARGET_VOLUMES).only(
                "product_id", "volume"
            )
        }

        to_create: list[Variant] = []
        matched_products = 0
        skipped_existing = 0

        for product in Product.objects.select_related("brand"):
            cands = decants_by_brand.get(product.brand.slug, [])
            if not cands:
                continue

            exact = [c for c in cands if norm_text(c[0]) == norm_text(product.name)]
            if exact:
                matched = exact
            else:
                scored = [
                    (score_match(product.name, c[0]), c)
                    for c in cands
                    if score_match(product.name, c[0]) >= min_score
                ]
                if not scored:
                    continue
                scored.sort(key=lambda x: (-x[0], x[1][2]))
                best_score = scored[0][0]
                matched = [c for s, c in scored if s >= best_score - 0.05]

            by_volume = defaultdict(list)
            for row in matched:
                by_volume[row[1]].append(row)

            product_hits = 0
            for volume in sorted(TARGET_VOLUMES, key=lambda v: int(v[:-2])):
                rows = by_volume.get(volume)
                if not rows:
                    continue
                if (product.id, volume) in existing:
                    skipped_existing += 1
                    continue
                best = min(rows, key=lambda r: r[2])
                to_create.append(
                    Variant(
                        product=product,
                        volume=volume,
                        price=best[2],
                        stock=stock_default,
                    )
                )
                product_hits += 1

            if product_hits:
                matched_products += 1

        self.stdout.write(
            f"Строк отливантов 5/10ml в файле: {parsed_rows}\n"
            f"Товаров в БД: {Product.objects.count()}\n"
            f"Товаров с новыми отливантами: {matched_products}\n"
            f"Пропущено (объём уже есть): {skipped_existing}\n"
            f"Создать вариантов: {len(to_create)}"
        )

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDRY-RUN — данные не сохранены"))
            for v in to_create[:8]:
                self.stdout.write(
                    f"  {v.product.brand.name} | {v.product.name} | {v.volume} | {v.price}"
                )
            return

        if not to_create:
            self.stdout.write(self.style.NOTICE("Нечего импортировать."))
            return

        with transaction.atomic():
            Variant.objects.bulk_create(to_create, ignore_conflicts=True)

        self.stdout.write(
            self.style.SUCCESS(f"\nГотово: создано {len(to_create)} вариантов.")
        )
