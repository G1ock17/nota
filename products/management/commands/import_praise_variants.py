import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from products.brand_aliases import canonical_brand_name
from products.models import Brand, Product, Variant
from products.pricing import retail_price

VOL_RE = re.compile(r"\s+(\d+(?:[.,]\d+)?)\s*ml\b", re.I)
DECANT_RE = re.compile(
    r"\bsample\b|\bmini\b|atomiser|refill|\bpen\b|\d+[.,]\d+\s*ml",
    re.I,
)
CONC_RE = re.compile(r"\b(ed[ptc]|extrait|parfum|cologne|absolue|absolu)\b", re.I)
NOISE_RE = re.compile(
    r"\btest\b|\bmen\b|\bwomen\b|\bhombre\b|\bhomme\b|\bfemme\b|\blady\b|\bunisex\b",
    re.I,
)

BRAND_OVERRIDES = {
    "c.dior": "Dior",
    "c.dior homme": "Dior",
    "a.dunhill": "Dunhill",
    "pdm": "Parfums de Marly",
    "mfk": "Maison Francis Kurkdjian",
    "j-m": "Jo Malone London",
    "y.s.l": "Yves Saint Laurent",
    "yves saint laurent": "Yves Saint Laurent",
    "h.boss": "Hugo Boss",
    "t.ford": "Tom Ford",
    "a.c.d": "Acqua di Parma",
    "acqua di parma": "Acqua di Parma",
    "boadicea the victorious": "Boadicea the Victorious",
}


def parse_price(value):
    if value is None:
        return None
    text = str(value).replace(" ", "").replace(",", ".")
    try:
        price = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    if price is None or price <= 0:
        return None
    return retail_price(price)


def norm_text(value: str) -> str:
    s = (value or "").lower()
    s = s.replace("'", "'").replace("'", "'")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = CONC_RE.sub(" ", s)
    s = NOISE_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def resolve_brand(raw: str) -> str:
    key = raw.strip().lower()
    if key in BRAND_OVERRIDES:
        return BRAND_OVERRIDES[key]
    return canonical_brand_name(raw)


def find_db_brand(raw: str, db_brands, db_brands_slug):
    from django.utils.text import slugify

    name = resolve_brand(raw)
    brand = db_brands.get(name.lower())
    if brand:
        return brand
    rs = slugify(name)
    for slug, brand in db_brands_slug.items():
        if rs == slug or rs.endswith("-" + slug) or slug.endswith("-" + rs):
            return brand
    prs = slugify(raw)
    for slug, brand in db_brands_slug.items():
        if prs in slug or slug in prs:
            return brand
    return None


def score_match(db_name: str, praise_name: str) -> float:
    a = set(norm_text(db_name).split())
    b = set(norm_text(praise_name).split())
    if not a or not b:
        return 0.0
    return len(a & b) / max(len(a), len(b))


def should_import(vol: float, is_decant: bool) -> bool:
    if vol in (5, 10):
        return True
    if vol >= 30 and not is_decant:
        return True
    return False


def pick_best_row(rows):
    """Одна строка прайса на объём: без TEST, затем минимальная цена."""

    def sort_key(row):
        raw = row[5].lower()
        is_test = "test" in raw
        return (is_test, row[4])

    return min(rows, key=sort_key)


class Command(BaseCommand):
    help = (
        "Добавить/обновить варианты (5ml, 10ml, флаконы) из praise.xls "
        "для товаров, уже существующих в БД"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "file",
            type=str,
            nargs="?",
            default=r"C:\Users\glock\Desktop\praise.xls",
            help="Путь к praise.xls",
        )
        parser.add_argument("--dry-run", action="store_true", help="Без записи в БД")
        parser.add_argument(
            "--update",
            action="store_true",
            help="Обновлять цену существующих вариантов",
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

    def handle(self, *args, **options):
        file_path = Path(options["file"])
        if not file_path.exists():
            raise CommandError(f"Файл не найден: {file_path}")

        dry_run = options["dry_run"]
        allow_update = options["update"]
        stock_default = max(int(options["stock"]), 0)
        min_score = float(options["min_score"])

        df = pd.read_excel(file_path, sheet_name="TDSheet", engine="xlrd", header=None)

        db_brands = {b.name.lower(): b for b in Brand.objects.all()}
        db_brands_slug = {b.slug: b for b in Brand.objects.all()}

        praise_by_brand = defaultdict(list)
        skipped_rows = 0
        for _, row in df.iloc[9:].iterrows():
            if pd.isna(row[6]) or pd.isna(row[15]):
                continue
            raw = str(row[6]).strip()
            m = VOL_RE.search(raw)
            if not m:
                skipped_rows += 1
                continue
            vol = float(m.group(1).replace(",", "."))
            vol_key = f"{int(vol)}ml" if vol == int(vol) else f"{vol}ml"
            is_decant = bool(DECANT_RE.search(raw))
            if not should_import(vol, is_decant):
                continue
            prefix = raw[: m.start()].strip()
            parts = re.split(r"\s{2,}", prefix, maxsplit=1)
            brand_raw = parts[0].strip()
            perfume = parts[1].strip() if len(parts) > 1 else ""
            brand = find_db_brand(brand_raw, db_brands, db_brands_slug)
            price = parse_price(row[15])
            if not brand or not perfume or price is None:
                continue
            praise_by_brand[brand.slug].append(
                (perfume, vol_key, vol, is_decant, price, raw)
            )

        products = list(Product.objects.select_related("brand"))
        existing_variants = {
            (v.product_id, v.volume): v
            for v in Variant.objects.only("id", "product_id", "volume", "price", "stock")
        }

        to_create = []
        to_update = []
        matched_products = 0
        unmatched_products = 0

        for product in products:
            cands = praise_by_brand.get(product.brand.slug, [])
            if not cands:
                unmatched_products += 1
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
                    unmatched_products += 1
                    continue
                scored.sort(key=lambda x: (-x[0], x[1][4]))
                best_score = scored[0][0]
                matched = [c for s, c in scored if s >= best_score - 0.05]

            by_volume = defaultdict(list)
            for row in matched:
                by_volume[row[1]].append(row)

            product_hits = 0
            for volume, rows in by_volume.items():
                best = pick_best_row(rows)
                key = (product.id, volume)
                existing = existing_variants.get(key)
                if existing is None:
                    to_create.append(
                        Variant(
                            product=product,
                            volume=volume,
                            price=best[4],
                            stock=stock_default,
                        )
                    )
                    product_hits += 1
                elif allow_update and existing.price != best[4]:
                    existing.price = best[4]
                    to_update.append(existing)
                    product_hits += 1

            if product_hits:
                matched_products += 1
            else:
                unmatched_products += 1

        self.stdout.write(
            f"Строк прайса (подходящих): {sum(len(v) for v in praise_by_brand.values())}\n"
            f"Товаров в БД: {len(products)}\n"
            f"С новыми/обновлёнными вариантами: {matched_products}\n"
            f"Без совпадений в praise: {unmatched_products}\n"
            f"Создать вариантов: {len(to_create)}\n"
            f"Обновить цен: {len(to_update)}"
        )

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDRY-RUN — данные не сохранены"))
            if to_create[:5]:
                self.stdout.write("\nПримеры новых вариантов:")
                for v in to_create[:5]:
                    self.stdout.write(f"  {v.product.brand.name} | {v.product.name} | {v.volume} | {v.price}")
            return

        if not to_create and not to_update:
            self.stdout.write(self.style.NOTICE("Нечего импортировать."))
            return

        with transaction.atomic():
            if to_create:
                Variant.objects.bulk_create(to_create, ignore_conflicts=True)
            if to_update:
                Variant.objects.bulk_update(to_update, ["price"])

        self.stdout.write(
            self.style.SUCCESS(
                f"\nГотово: создано {len(to_create)}, обновлено {len(to_update)}."
            )
        )
