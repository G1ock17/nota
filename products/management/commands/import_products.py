import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.error import URLError, HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from django.core.management.base import BaseCommand, CommandError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils.text import slugify

from products.models import Brand, Category, FragranceNote, Product, ProductImage, Variant


def split_csv_like(value):
    if not value:
        return []
    # In source JSON values often have many spaces/newlines between commas.
    normalized = re.sub(r"\s+", " ", str(value)).strip()
    return [item.strip(" ,") for item in normalized.split(",") if item.strip(" ,")]


def parse_price(value):
    if value is None:
        return None
    text = str(value)
    text = text.replace("₽", "").replace(" ", "").replace("\u00a0", "").replace(",", ".")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def fetch_image_bytes(url):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=20) as resp:
        return resp.read()


def infer_filename(url, fallback_slug, index):
    path = urlparse(url).path or ""
    tail = path.split("/")[-1] if path else ""
    tail = tail.split("?")[0]
    ext = ".jpg"
    if "." in tail:
        ext = "." + tail.split(".")[-1].lower()
        if len(ext) > 6:
            ext = ".jpg"
    return f"{fallback_slug}-{index}{ext}"


def resolve_gender_category_slug(gender_value, default_category_slug):
    normalized = (gender_value or "").strip().lower()
    normalized = normalized.replace("ё", "е")

    if normalized in {"мужские", "мужской", "для мужчин", "male", "man", "men"}:
        return "man"
    if normalized in {"женские", "женский", "для женщин", "female", "woman", "women"}:
        return "woman"
    if normalized in {"унисекс", "unisex", "for everyone"}:
        return "unisex"

    # Если значение "Пол" отсутствует или не распознано — оставляем fallback из аргумента.
    return default_category_slug


class Command(BaseCommand):
    help = "Импорт товаров из all_products.json с привязкой нот"

    def add_arguments(self, parser):
        parser.add_argument("file", type=str, help="Путь к JSON-файлу с товарами")
        parser.add_argument("--dry-run", action="store_true", help="Проверка без записи в БД")
        parser.add_argument("--update", action="store_true", help="Обновлять существующие товары")
        parser.add_argument(
            "--default-category",
            type=str,
            default="unisex",
            help="Slug категории по умолчанию, если в товаре нет поля 'Пол'",
        )
        parser.add_argument(
            "--volume",
            type=str,
            default="50ml",
            help="Объём варианта (например: 50ml), если в JSON только одна цена",
        )
        parser.add_argument(
            "--stock",
            type=int,
            default=10,
            help="Остаток для создаваемого/обновляемого варианта",
        )
        parser.add_argument(
            "--skip-images",
            action="store_true",
            help="Не скачивать изображения (сильно ускоряет импорт тысяч товаров)",
        )
        parser.add_argument(
            "--progress-every",
            type=int,
            default=500,
            help="Печатать прогресс каждые N товаров (0 — отключить)",
        )

    def handle(self, *args, **options):
        file_path = Path(options["file"])
        if not file_path.exists():
            raise CommandError(f"Файл не найден: {file_path}")

        with file_path.open("r", encoding="utf-8") as f:
            raw = json.load(f)

        products_data = raw if isinstance(raw, list) else raw.get("products", [])
        if not products_data:
            raise CommandError("В JSON нет товаров (ожидался список или ключ 'products').")

        dry_run = options["dry_run"]
        allow_update = options["update"]
        default_category_slug = (options["default_category"].strip() or "unisex").lower()
        default_volume = options["volume"]
        stock_default = max(int(options["stock"]), 0)
        skip_images = options["skip_images"]
        progress_every = max(int(options["progress_every"]), 0)
        verbosity = options.get("verbosity", 1)
        total = len(products_data)

        created = 0
        updated = 0
        skipped = 0
        missing_note_warnings = 0
        max_note_warnings = 50

        if dry_run:
            existing_slugs = set(Product.objects.values_list("slug", flat=True))
            for idx, item in enumerate(products_data, start=1):
                name = (item.get("name") or "").strip()
                if not name:
                    if verbosity >= 2:
                        self.stdout.write(self.style.WARNING(f"[{idx}] Пропуск: пустое имя товара"))
                    skipped += 1
                    continue

                specs = item.get("specs") or {}
                source_url = item.get("url") or item.get("link")
                slug_from_url = ""
                if source_url:
                    slug_from_url = source_url.rstrip("/").split("/")[-1].strip()
                product_slug = slugify(slug_from_url or name)[:255]
                if not product_slug:
                    if verbosity >= 2:
                        self.stdout.write(
                            self.style.WARNING(f"[{idx}] Пропуск: не удалось сформировать slug для '{name}'")
                        )
                    skipped += 1
                    continue

                price = parse_price(item.get("price"))
                note_count = 0
                for spec_key, note_type in (
                    ("Верхние ноты", FragranceNote.NoteType.TOP),
                    ("Ноты сердца", FragranceNote.NoteType.MIDDLE),
                    ("Базовые ноты", FragranceNote.NoteType.BASE),
                ):
                    note_count += len(split_csv_like(specs.get(spec_key, "")))

                exists = product_slug in existing_slugs
                action = "обновится" if (exists and allow_update) else ("существует" if exists else "создастся")
                if verbosity >= 2:
                    self.stdout.write(
                        f"[DRY-RUN] {name} ({product_slug}) — {action}, "
                        f"нот: {note_count}, цена: {price if price is not None else 'нет'}"
                    )
                if progress_every and idx % progress_every == 0:
                    self.stdout.write(f"DRY-RUN: обработано {idx}/{total}")
            self.stdout.write(self.style.WARNING("\nDRY-RUN завершён — данные НЕ сохранены"))
            return

        # --- Однократная загрузка справочников (избегаем N+1 на 12k+ строк) ---
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
            ("Верхние ноты", FragranceNote.NoteType.TOP),
            ("Ноты сердца", FragranceNote.NoteType.MIDDLE),
            ("Базовые ноты", FragranceNote.NoteType.BASE),
        )

        def resolve_brand(brand_name: str):
            bslug = slugify(brand_name)[:255]
            b = brand_by_slug.get(bslug)
            if b is None:
                b = Brand.objects.create(name=brand_name, slug=bslug)
                brand_by_slug[bslug] = b
            return b

        for idx, item in enumerate(products_data, start=1):
            name = (item.get("name") or "").strip()
            if not name:
                if verbosity >= 2:
                    self.stdout.write(self.style.WARNING(f"[{idx}] Пропуск: пустое имя товара"))
                skipped += 1
                continue

            specs = item.get("specs") or {}
            brand_name = (item.get("brand") or specs.get("Бренд") or "Без бренда").strip()
            category_slug = resolve_gender_category_slug(specs.get("Пол"), default_category_slug)
            description = (item.get("description") or "").strip()
            price = parse_price(item.get("price"))
            year_value = specs.get("Год создания") or specs.get("Год")
            try:
                year = int(str(year_value).strip()) if year_value else None
            except (TypeError, ValueError):
                year = None
            country = (specs.get("Страна") or specs.get("Страна производства") or "").strip()

            slug_from_url = ""
            source_url = item.get("url") or item.get("link")
            if source_url:
                slug_from_url = source_url.rstrip("/").split("/")[-1].strip()
            product_slug = slugify(slug_from_url or name)[:255]
            if not product_slug:
                if verbosity >= 2:
                    self.stdout.write(
                        self.style.WARNING(f"[{idx}] Пропуск: не удалось сформировать slug для '{name}'")
                    )
                skipped += 1
                continue

            note_pairs = []
            for spec_key, note_type in notes_map:
                for note_name in split_csv_like(specs.get(spec_key, "")):
                    note_pairs.append((note_name, note_type))

            category = category_by_slug.get(category_slug)
            if not category:
                self.stdout.write(
                    self.style.WARNING(
                        f"[{idx}] Пропуск: категория со slug='{category_slug}' не найдена для '{name}'"
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
                            f"⚠ Нота не найдена в БД: name='{note_name}', type='{note_type}' для '{name}'"
                        )
                    )
                    missing_note_warnings += 1

            # Короткая транзакция только на БД — без HTTP по картинкам.
            with transaction.atomic():
                brand = resolve_brand(brand_name)
                product = product_by_slug.get(product_slug)
                is_created = False
                changed = False

                if product is None:
                    product = Product.objects.create(
                        slug=product_slug,
                        name=name,
                        description=description,
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
                    if product.description != description:
                        product.description = description
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
                            update_fields=[
                                "name",
                                "description",
                                "brand",
                                "category",
                                "year",
                                "country",
                            ]
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

                if price is not None:
                    v = variant_by_product_id.get(product.id)
                    if v is None:
                        v = Variant.objects.create(
                            product=product,
                            volume=default_volume,
                            price=price,
                            stock=stock_default,
                        )
                        variant_by_product_id[product.id] = v
                    elif v.price != price or v.stock != stock_default:
                        v.price = price
                        v.stock = stock_default
                        v.save(update_fields=["price", "stock"])

            if not skip_images:
                image_urls = item.get("images")
                if not image_urls:
                    single_image = str(item.get("image") or "").strip()
                    image_urls = [single_image] if single_image else []
                if isinstance(image_urls, list):
                    product = product_by_slug[product_slug]
                    if allow_update:
                        product.images.all().delete()
                    if not product.images.exists():
                        for img_idx, img_url in enumerate(image_urls, start=1):
                            img_url = str(img_url).strip()
                            if not img_url:
                                continue
                            try:
                                content = fetch_image_bytes(img_url)
                            except (URLError, HTTPError, TimeoutError, ValueError) as exc:
                                self.stdout.write(
                                    self.style.WARNING(
                                        f"⚠ Не удалось скачать картинку '{img_url}' для '{name}': {exc}"
                                    )
                                )
                                continue

                            file_name = infer_filename(img_url, product.slug, img_idx)
                            image_obj = ProductImage(product=product, is_main=(img_idx == 1))
                            image_obj.image.save(file_name, ContentFile(content), save=True)

            if verbosity >= 2:
                if is_created:
                    self.stdout.write(self.style.SUCCESS(f"✓ Создан товар: {name}"))
                elif allow_update and changed:
                    self.stdout.write(self.style.SUCCESS(f"✓ Обновлён товар: {name}"))
                else:
                    self.stdout.write(f"→ Без изменений: {name}")

            if progress_every and idx % progress_every == 0:
                self.stdout.write(
                    f"Прогресс: {idx}/{total} (создано {created}, обновлено {updated}, пропущено {skipped})"
                )

        if missing_note_warnings >= max_note_warnings:
            self.stdout.write(
                self.style.WARNING(
                    f"… и ещё отсутствующих нот не показано (лимит сообщений {max_note_warnings})."
                )
            )

        if skip_images:
            self.stdout.write(self.style.NOTICE("Изображения пропущены (--skip-images)."))

        self.stdout.write(
            self.style.SUCCESS(
                f"\nИмпорт товаров завершён!\n"
                f"Создано: {created} | Обновлено: {updated} | Пропущено: {skipped}"
            )
        )
