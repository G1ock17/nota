import json
import re
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import pandas as pd
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from products.brand_aliases import canonical_brand_name
from products.display_names import strip_brand_prefix
from products.fragrantica_images import extract_fragrantica_id, save_product_thumbnail
from products.management.commands.import_decant_variants import (
    TARGET_VOLUMES as DECANT_VOLUMES,
    parse_decant_row,
)
from products.management.commands.import_need_products import split_csv_like
from products.management.commands.import_praise_variants import (
    DECANT_RE,
    NON_PERFUME_RE,
    VOL_RE,
    find_db_brand,
    name_match_allowed,
    norm_text,
    pick_best_row,
    score_match,
    should_import,
)
from products.management.commands.import_products import resolve_gender_category_slug
from products.models import Brand, Category, FragranceNote, Product, ProductImage, Variant
from products.pricing import parse_wholesale_price, retail_price

DEFAULT_JSON = r"C:\Users\glock\Desktop\missing_confirmed_v3_products.json"
DEFAULT_PRAISE = r"C:\Users\glock\Desktop\praise.xls"
DEFAULT_DECANTS = r"C:\Users\glock\Desktop\Мелкооптовыевпересчетенарубли_Отливанты.xls"


def product_slug_from_item(item: dict) -> str:
    brand = (item.get("brand") or "").strip()
    url = (item.get("fragrantica_url") or item.get("url") or "").strip()
    if url:
        tail = url.rstrip("/").split("/")[-1].replace(".html", "")
        tail = re.sub(r"-\d+$", "", tail)
        slug = f"{slugify(brand)}-{slugify(tail)}"[:255]
        if slug.strip("-"):
            return slug
    perfume = (item.get("perfume") or "").strip()
    return f"{slugify(brand)}-{slugify(perfume)}"[:255]


def load_praise_rows(path: Path, db_brands, db_brands_slug):
    df = pd.read_excel(path, sheet_name="TDSheet", engine="xlrd", header=None)
    by_brand = defaultdict(list)
    for _, row in df.iloc[9:].iterrows():
        if pd.isna(row[6]) or pd.isna(row[15]):
            continue
        raw = str(row[6]).strip()
        m = VOL_RE.search(raw)
        if not m:
            continue
        vol = float(m.group(1).replace(",", "."))
        vol_key = f"{int(vol)}ml" if vol == int(vol) else f"{vol}ml"
        is_decant = bool(DECANT_RE.search(raw))
        if not should_import(vol, is_decant):
            continue
        if vol >= 30 and NON_PERFUME_RE.search(raw):
            continue
        prefix = raw[: m.start()].strip()
        parts = re.split(r"\s{2,}", prefix, maxsplit=1)
        brand_raw = parts[0].strip()
        perfume = parts[1].strip() if len(parts) > 1 else ""
        brand = find_db_brand(brand_raw, db_brands, db_brands_slug)
        wholesale = parse_wholesale_price(row[15])
        if not brand or not perfume or wholesale is None:
            continue
        by_brand[brand.slug].append((perfume, vol_key, vol, is_decant, wholesale, raw))
    return by_brand


def load_decant_rows(path: Path, db_brands, db_brands_slug):
    df = pd.read_excel(path, sheet_name="TDSheet", engine="xlrd", header=None)
    by_brand = defaultdict(list)
    for _, row in df.iloc[11:].iterrows():
        if pd.isna(row[6]) or pd.isna(row[15]):
            continue
        parsed = parse_decant_row(row[6])
        if not parsed:
            continue
        brand_raw, perfume, vol_key = parsed
        brand = find_db_brand(brand_raw, db_brands, db_brands_slug)
        wholesale = parse_wholesale_price(row[15])
        if not brand or not perfume or wholesale is None:
            continue
        by_brand[brand.slug].append(
            (perfume, vol_key, wholesale, str(row[6]).strip())
        )
    return by_brand


def match_price_rows_by_name(name: str, rows: list, min_score: float):
    if not rows:
        return []
    exact = [c for c in rows if norm_text(c[0]) == norm_text(name)]
    if exact:
        return exact
    scored = [
        (score_match(name, c[0]), c)
        for c in rows
        if name_match_allowed(name, c[0], min_score)
    ]
    if not scored:
        return []
    scored.sort(key=lambda x: (-x[0], x[1][2] if len(x[1]) == 4 else x[1][4]))
    best_score = scored[0][0]
    return [c for s, c in scored if s >= best_score - 0.05]


def variants_for_product_name(name, brand_slug, praise_rows, decant_rows, min_score):
    """Собрать лучшие цены по объёмам из praise (флаконы + 5/10) и отливантов."""
    by_volume = defaultdict(list)

    for row in match_price_rows_by_name(name, praise_rows, min_score):
        by_volume[row[1]].append(("praise", row))

    for row in match_price_rows_by_name(name, decant_rows, min_score):
        vol_key = row[1]
        if vol_key in DECANT_VOLUMES:
            by_volume[vol_key].append(("decant", row))

    result = {}
    for volume, rows in by_volume.items():
        praise_rows_only = [r[1] for r in rows if r[0] == "praise"]
        decant_rows_only = [r[1] for r in rows if r[0] == "decant"]
        wholesale = None
        if praise_rows_only:
            wholesale = pick_best_row(praise_rows_only)[4]
        elif decant_rows_only:
            wholesale = min(decant_rows_only, key=lambda r: r[2])[2]
        if wholesale is not None:
            result[volume] = retail_price(wholesale)
    return result


class Command(BaseCommand):
    help = (
        "Импорт ароматов из missing_confirmed JSON с объёмами и ценами "
        "из praise.xls (флаконы) и прайса отливантов (5/10 ml)"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "file",
            nargs="?",
            default=DEFAULT_JSON,
            help="JSON с новыми ароматами",
        )
        parser.add_argument(
            "--praise-file",
            default=DEFAULT_PRAISE,
            help="Прайс флаконов praise.xls",
        )
        parser.add_argument(
            "--decants-file",
            default=DEFAULT_DECANTS,
            help="Прайс отливантов xls",
        )
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--update", action="store_true", help="Обновлять существующие товары")
        parser.add_argument("--stock", type=int, default=10)
        parser.add_argument("--min-score", type=float, default=0.65)
        parser.add_argument("--skip-images", action="store_true")

    def handle(self, *args, **options):
        json_path = Path(options["file"])
        praise_path = Path(options["praise_file"])
        decants_path = Path(options["decants_file"])
        for path in (json_path, praise_path, decants_path):
            if not path.exists():
                raise CommandError(f"Файл не найден: {path}")

        with json_path.open(encoding="utf-8") as f:
            items = json.load(f)
        if not isinstance(items, list):
            raise CommandError("Ожидался JSON-массив.")

        dry_run = options["dry_run"]
        allow_update = options["update"]
        stock_default = max(int(options["stock"]), 0)
        min_score = float(options["min_score"])
        skip_images = options["skip_images"]

        db_brands = {b.name.lower(): b for b in Brand.objects.all()}
        db_brands_slug = {b.slug: b for b in Brand.objects.all()}
        praise_by_brand = load_praise_rows(praise_path, db_brands, db_brands_slug)
        decants_by_brand = load_decant_rows(decants_path, db_brands, db_brands_slug)

        brand_by_slug = {b.slug: b for b in Brand.objects.all()}
        category_by_slug = {c.slug: c for c in Category.objects.all()}
        note_lookup = {
            (n.name.lower(), n.type): n.id
            for n in FragranceNote.objects.only("id", "name", "type").iterator(chunk_size=2000)
        }
        product_by_slug = {
            p.slug: p for p in Product.objects.select_related("brand").iterator(chunk_size=500)
        }
        existing_variants = {
            (v.product_id, v.volume): v
            for v in Variant.objects.only("id", "product_id", "volume", "price")
        }

        notes_map = (
            ("top", FragranceNote.NoteType.TOP),
            ("middle", FragranceNote.NoteType.MIDDLE),
            ("base", FragranceNote.NoteType.BASE),
        )

        def resolve_brand(brand_name: str):
            canonical_name = canonical_brand_name(brand_name)
            bslug = slugify(canonical_name)[:255]
            brand = brand_by_slug.get(bslug)
            if brand is None:
                brand = Brand.objects.create(name=canonical_name, slug=bslug)
                brand_by_slug[bslug] = brand
                db_brands[canonical_name.lower()] = brand
                db_brands_slug[bslug] = brand
            return brand

        created_products = 0
        updated_products = 0
        skipped_products = 0
        created_variants = 0
        updated_variants = 0
        no_price_match = []
        images_attached = 0

        for idx, item in enumerate(items, start=1):
            raw_name = (item.get("perfume") or "").strip()
            brand_name = (item.get("brand") or "Без бренда").strip()
            name = strip_brand_prefix(raw_name, canonical_brand_name(brand_name))
            product_slug = product_slug_from_item(item)
            if not name or not product_slug:
                skipped_products += 1
                continue

            category_slug = resolve_gender_category_slug(item.get("gender"), "unisex")
            category = category_by_slug.get(category_slug)
            if not category:
                self.stdout.write(
                    self.style.WARNING(
                        f"[{idx}] Пропуск: категория '{category_slug}' не найдена для '{name}'"
                    )
                )
                skipped_products += 1
                continue

            country = (item.get("country") or "").strip()
            year_value = item.get("year")
            try:
                year = int(str(year_value).strip()) if year_value else None
            except (TypeError, ValueError):
                year = None
            description = (item.get("description") or "").strip()

            note_ids = []
            for field_key, note_type in notes_map:
                for note_name in split_csv_like(item.get(field_key, "")):
                    nid = note_lookup.get((note_name.lower(), note_type))
                    if nid:
                        note_ids.append(nid)

            brand = resolve_brand(brand_name)
            product = product_by_slug.get(product_slug)
            is_created = product is None

            if is_created:
                if dry_run:
                    product = Product(
                        slug=product_slug,
                        name=name,
                        description=description,
                        brand=brand,
                        category=category,
                        year=year,
                        country=country,
                    )
                    created_products += 1
                else:
                    with transaction.atomic():
                        product = Product.objects.create(
                            slug=product_slug,
                            name=name,
                            description=description,
                            brand=brand,
                            category=category,
                            year=year,
                            country=country,
                        )
                        if note_ids:
                            product.notes.set(note_ids)
                        product_by_slug[product_slug] = product
                    created_products += 1
            elif allow_update:
                changed_fields = []
                if product.name != name:
                    product.name = name
                    changed_fields.append("name")
                if product.description != description and description:
                    product.description = description
                    changed_fields.append("description")
                if product.brand_id != brand.id:
                    product.brand = brand
                    changed_fields.append("brand")
                if product.category_id != category.id:
                    product.category = category
                    changed_fields.append("category")
                if product.year != year:
                    product.year = year
                    changed_fields.append("year")
                if product.country != country:
                    product.country = country
                    changed_fields.append("country")
                if not dry_run:
                    with transaction.atomic():
                        if changed_fields:
                            product.save(update_fields=changed_fields)
                            updated_products += 1
                        if note_ids:
                            product.notes.set(note_ids)
                elif changed_fields or note_ids:
                    updated_products += 1
            else:
                skipped_products += 1

            praise_rows = praise_by_brand.get(brand.slug, [])
            decant_rows = decants_by_brand.get(brand.slug, [])
            volume_prices = variants_for_product_name(
                name, brand.slug, praise_rows, decant_rows, min_score
            )

            if not volume_prices:
                no_price_match.append(f"{brand_name} | {name}")
            else:
                for volume, price in sorted(
                    volume_prices.items(),
                    key=lambda kv: int(re.match(r"\d+", kv[0]).group()),
                ):
                    if is_created or product is not None:
                        if dry_run:
                            key_exists = (
                                not is_created
                                and (product.id, volume) in existing_variants
                            )
                            if not key_exists:
                                created_variants += 1
                            elif allow_update:
                                existing = existing_variants.get((product.id, volume))
                                if existing and existing.price != price:
                                    updated_variants += 1
                            continue

                        key = (product.id, volume)
                        existing = existing_variants.get(key)
                        if existing is None:
                            variant = Variant.objects.create(
                                product=product,
                                volume=volume,
                                price=price,
                                stock=stock_default,
                            )
                            existing_variants[key] = variant
                            created_variants += 1
                        elif allow_update and existing.price != price:
                            existing.price = price
                            existing.save(update_fields=["price"])
                            updated_variants += 1

            if skip_images or dry_run or product is None:
                continue
            if product.images.exists() and not (is_created or allow_update):
                continue
            perfume_id = extract_fragrantica_id(item.get("fragrantica_url") or "")
            if not perfume_id:
                continue
            try:
                save_product_thumbnail(product, perfume_id, replace=allow_update or is_created)
                images_attached += 1
            except RuntimeError as exc:
                self.stdout.write(
                    self.style.WARNING(f"Фото не загружено для '{name}': {exc}")
                )

        self.stdout.write(
            f"\nJSON: {len(items)} позиций\n"
            f"Создано товаров: {created_products}\n"
            f"Обновлено товаров: {updated_products}\n"
            f"Пропущено товаров: {skipped_products}\n"
            f"Создано вариантов: {created_variants}\n"
            f"Обновлено вариантов: {updated_variants}\n"
            f"Без цен в прайсах: {len(no_price_match)}\n"
            f"Фото загружено: {images_attached}"
        )
        if no_price_match:
            self.stdout.write("\nБез совпадения в praise/отливантах:")
            for line in no_price_match[:20]:
                self.stdout.write(f"  {line}")
            if len(no_price_match) > 20:
                self.stdout.write(f"  … ещё {len(no_price_match) - 20}")

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDRY-RUN — данные не сохранены"))
