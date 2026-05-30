import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from products.management.commands.import_products import (
    resolve_gender_category_slug,
    split_csv_like,
)
from products.brand_aliases import canonical_brand_name
from products.display_names import strip_brand_prefix
from products.fragrantica_images import extract_fragrantica_id, save_product_thumbnail
from products.models import Brand, Category, FragranceNote, Product, ProductImage, Variant

IMAGE_EXTENSIONS = {".avif", ".webp", ".jpg", ".jpeg", ".png", ".gif"}


def parse_default_price(value):
    if value is None:
        return None
    text = str(value).replace(" ", "").replace(",", ".")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def fragrantica_tail_slug(url: str) -> str:
    tail = url.rstrip("/").split("/")[-1].replace(".html", "")
    return re.sub(r"-\d+$", "", tail)


def product_slug_from_url(item: dict) -> str:
    brand = (item.get("brand") or "").strip()
    url = (item.get("url") or "").strip()
    if not url:
        return ""
    return f"{slugify(brand)}-{slugify(fragrantica_tail_slug(url))}"[:255]


def product_slug_from_perfume(item: dict) -> str:
    brand = (item.get("brand") or "").strip()
    perfume = (item.get("perfume") or "").strip()
    return f"{slugify(brand)}-{slugify(perfume)}"[:255]


def resolve_product_slug(item: dict, image_folder_names: set[str]) -> str:
    url_slug = product_slug_from_url(item)
    perfume_slug = product_slug_from_perfume(item)
    if url_slug and url_slug in image_folder_names:
        return url_slug
    if perfume_slug in image_folder_names:
        return perfume_slug
    return perfume_slug or url_slug


def find_product_images(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    files = [
        p
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    ]
    files.sort(key=lambda p: p.name)
    return files


class Command(BaseCommand):
    help = (
        "Импорт ароматов из need_products.json (Fragrantica) "
        "с локальными фото из need_import_images/<slug>/"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "file",
            type=str,
            nargs="?",
            default="need_products.json",
            help="Путь к JSON (по умолчанию: need_products.json)",
        )
        parser.add_argument(
            "--images-dir",
            type=str,
            default="need_import_images",
            help="Папка с подпапками slug/1.avif (по умолчанию: need_import_images)",
        )
        parser.add_argument("--dry-run", action="store_true", help="Проверка без записи в БД")
        parser.add_argument("--update", action="store_true", help="Обновлять существующие товары")
        parser.add_argument(
            "--default-category",
            type=str,
            default="unisex",
            help="Slug категории по умолчанию",
        )
        parser.add_argument("--volume", type=str, default="50ml", help="Объём варианта")
        parser.add_argument("--stock", type=int, default=10, help="Остаток варианта")
        parser.add_argument(
            "--default-price",
            type=str,
            default="",
            help="Цена варианта (₽), если в JSON нет цены; без значения вариант не создаётся",
        )
        parser.add_argument(
            "--skip-images",
            action="store_true",
            help="Не загружать локальные изображения",
        )
        parser.add_argument(
            "--progress-every",
            type=int,
            default=100,
            help="Печатать прогресс каждые N товаров (0 — отключить)",
        )

    def handle(self, *args, **options):
        file_path = Path(options["file"])
        images_dir = Path(options["images_dir"])
        if not file_path.exists():
            raise CommandError(f"Файл не найден: {file_path}")
        if not images_dir.exists() and not options["skip_images"]:
            raise CommandError(f"Папка с изображениями не найдена: {images_dir}")

        with file_path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, list):
            raise CommandError("Ожидался JSON-массив товаров.")

        default_price = parse_default_price(options["default_price"] or None)
        dry_run = options["dry_run"]
        allow_update = options["update"]
        default_category_slug = (options["default_category"].strip() or "unisex").lower()
        default_volume = options["volume"]
        stock_default = max(int(options["stock"]), 0)
        skip_images = options["skip_images"]
        progress_every = max(int(options["progress_every"]), 0)
        verbosity = int(options.get("verbosity", 1))

        image_folder_names = (
            {p.name for p in images_dir.iterdir() if p.is_dir()} if images_dir.exists() else set()
        )

        # Дедупликация по slug (в JSON бывают повторы).
        deduped: dict[str, dict] = {}
        for item in raw:
            perfume = (item.get("perfume") or "").strip()
            if not perfume:
                continue
            slug = resolve_product_slug(item, image_folder_names)
            if not slug:
                continue
            deduped[slug] = item

        products_data = list(deduped.values())
        total = len(products_data)

        if dry_run:
            existing = set(Product.objects.values_list("slug", flat=True))
            would_create = 0
            with_images = 0
            for item in products_data:
                slug = resolve_product_slug(item, image_folder_names)
                if slug not in existing:
                    would_create += 1
                folder = images_dir / slug
                if find_product_images(folder):
                    with_images += 1
            self.stdout.write(
                self.style.WARNING(
                    f"DRY-RUN: уникальных товаров {total}, новых ~{would_create}, "
                    f"с локальными фото ~{with_images}, default_price={default_price}"
                )
            )
            return

        brand_by_slug = {b.slug: b for b in Brand.objects.all()}
        category_by_slug = {c.slug: c for c in Category.objects.all()}
        note_lookup = {}
        for n in FragranceNote.objects.only("id", "name", "type").iterator(chunk_size=2000):
            note_lookup[(n.name.lower(), n.type)] = n.id

        product_by_slug = {
            p.slug: p for p in Product.objects.select_related("brand", "category").iterator(chunk_size=500)
        }
        variant_by_product_id = {
            v.product_id: v
            for v in Variant.objects.filter(volume=default_volume).only("id", "product_id", "price", "stock")
        }

        notes_map = (
            ("top", FragranceNote.NoteType.TOP),
            ("middle", FragranceNote.NoteType.MIDDLE),
            ("base", FragranceNote.NoteType.BASE),
        )

        def resolve_brand(brand_name: str):
            canonical_name = canonical_brand_name(brand_name)
            bslug = slugify(canonical_name)[:255]
            b = brand_by_slug.get(bslug)
            if b is None:
                b = Brand.objects.create(name=canonical_name, slug=bslug)
                brand_by_slug[bslug] = b
            elif b.name != canonical_name:
                b.name = canonical_name
                b.save(update_fields=["name"])
            return b

        created = 0
        updated = 0
        skipped = 0
        images_attached = 0
        missing_images = 0
        missing_note_warnings = 0
        max_note_warnings = 50

        for idx, item in enumerate(products_data, start=1):
            raw_name = (item.get("perfume") or "").strip()
            brand_name = (item.get("brand") or "Без бренда").strip()
            name = strip_brand_prefix(raw_name, canonical_brand_name(brand_name))
            product_slug = resolve_product_slug(item, image_folder_names)
            if not name or not product_slug:
                skipped += 1
                continue

            category_slug = resolve_gender_category_slug(item.get("gender"), default_category_slug)
            country = (item.get("country") or "").strip()
            year_value = item.get("year")
            try:
                year = int(str(year_value).strip()) if year_value else None
            except (TypeError, ValueError):
                year = None

            note_pairs = []
            for field_key, note_type in notes_map:
                for note_name in split_csv_like(item.get(field_key, "")):
                    note_pairs.append((note_name, note_type))

            category = category_by_slug.get(category_slug)
            if not category:
                if verbosity >= 1:
                    self.stdout.write(
                        self.style.WARNING(
                            f"[{idx}] Пропуск: категория '{category_slug}' не найдена для '{name}'"
                        )
                    )
                skipped += 1
                continue

            note_ids = []
            for note_name, note_type in note_pairs:
                nid = note_lookup.get((note_name.lower(), note_type))
                if nid:
                    note_ids.append(nid)
                elif missing_note_warnings < max_note_warnings:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Нота не найдена: '{note_name}' ({note_type}) — '{name}'"
                        )
                    )
                    missing_note_warnings += 1

            with transaction.atomic():
                brand = resolve_brand(brand_name)
                product = product_by_slug.get(product_slug)
                is_created = False
                changed = False

                if product is None:
                    product = Product.objects.create(
                        slug=product_slug,
                        name=name,
                        description="",
                        brand=brand,
                        category=category,
                        year=year,
                        country=country,
                    )
                    product_by_slug[product_slug] = product
                    is_created = True
                    created += 1
                elif allow_update:
                    if product.name != name:
                        product.name = name
                        changed = True
                    if product.brand_id != brand.id:
                        product.brand = brand
                        changed = True
                    if product.category_id != category.id:
                        product.category = category
                        changed = True
                    if product.year != year:
                        product.year = year
                        changed = True
                    if product.country != country:
                        product.country = country
                        changed = True
                    if changed:
                        product.save(
                            update_fields=["name", "brand", "category", "year", "country"]
                        )
                        updated += 1
                    else:
                        skipped += 1
                else:
                    skipped += 1

                if note_ids:
                    product.notes.set(note_ids)
                else:
                    product.notes.clear()

                if default_price is not None:
                    v = variant_by_product_id.get(product.id)
                    if v is None:
                        v = Variant.objects.create(
                            product=product,
                            volume=default_volume,
                            price=default_price,
                            stock=stock_default,
                        )
                        variant_by_product_id[product.id] = v
                    elif allow_update and (v.price != default_price or v.stock != stock_default):
                        v.price = default_price
                        v.stock = stock_default
                        v.save(update_fields=["price", "stock"])

            if not skip_images:
                image_files = find_product_images(images_dir / product_slug)
                if not image_files:
                    missing_images += 1
                    source_url = (item.get("url") or "").strip()
                    perfume_id = extract_fragrantica_id(source_url)
                    if perfume_id and (is_created or allow_update):
                        try:
                            save_product_thumbnail(
                                product,
                                perfume_id,
                                replace=allow_update,
                            )
                            images_attached += 1
                            missing_images -= 1
                        except RuntimeError as exc:
                            if verbosity >= 2:
                                self.stdout.write(
                                    self.style.WARNING(
                                        f"Fragrantica фото не загружено для '{name}': {exc}"
                                    )
                                )
                elif is_created or allow_update:
                    if allow_update:
                        product.images.all().delete()
                    if is_created or not product.images.exists():
                        for img_idx, image_path in enumerate(image_files, start=1):
                            filename = f"{product_slug}-{img_idx}{image_path.suffix.lower()}"
                            with image_path.open("rb") as image_f:
                                image_obj = ProductImage(
                                    product=product,
                                    is_main=(img_idx == 1),
                                )
                                image_obj.image.save(filename, File(image_f), save=True)
                                images_attached += 1

            if progress_every and idx % progress_every == 0:
                self.stdout.write(
                    f"Прогресс: {idx}/{total} (создано {created}, обновлено {updated})"
                )

        if missing_note_warnings >= max_note_warnings:
            self.stdout.write(
                self.style.WARNING(
                    f"… ещё отсутствующих нот не показано (лимит {max_note_warnings})."
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nИмпорт завершён.\n"
                f"Уникальных в JSON: {total} | Создано: {created} | Обновлено: {updated} | "
                f"Пропущено (уже есть): {skipped}\n"
                f"Изображений загружено: {images_attached} | Товаров без фото: {missing_images}"
            )
        )
        if default_price is None:
            self.stdout.write(
                self.style.NOTICE(
                    "Варианты с ценой не созданы — передайте --default-price, "
                    "чтобы товары отображались в каталоге."
                )
            )
