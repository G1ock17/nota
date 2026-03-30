"""
Management command: заполнение БД демо-данными для каталога парфюмерии.
Запуск: python manage.py seed_db
Опции: --products N (по умолчанию случайно 50–100), --seed для воспроизводимости random.
"""

from __future__ import annotations

import base64
import random
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from products.models import Brand, Category, FragranceNote, Product, ProductImage, Variant

# Минимальный валидный JPEG (крошечное изображение), если сеть недоступна
_MINIMAL_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/"
    "2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/"
    "wAARCABAAEADASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAX/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/"
    "8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCwAA8A/9k="
)


CATEGORIES = [
    "Niche",
    "Designer",
    "Luxury",
    "Unisex",
    "Arabic",
]

BRANDS = [
    "Dior",
    "Chanel",
    "Tom Ford",
    "Maison Francis Kurkdjian",
    "Byredo",
    "Le Labo",
    "Xerjoff",
    "Amouage",
    "Initio",
    "Mancera",
    "Montale",
    "Parfums de Marly",
    "Kilian",
    "Nishane",
    "Creed",
    "Guerlain",
    "Yves Saint Laurent",
    "Hermès",
    "Acqua di Parma",
    "Frédéric Malle",
]

# (name, type) — 41 нота (30–50), включая все из ТЗ
NOTE_DEFINITIONS: list[tuple[str, str]] = [
    ("Bergamot", FragranceNote.NoteType.TOP),
    ("Lemon", FragranceNote.NoteType.TOP),
    ("Grapefruit", FragranceNote.NoteType.TOP),
    ("Pink Pepper", FragranceNote.NoteType.TOP),
    ("Mint", FragranceNote.NoteType.TOP),
    ("Orange", FragranceNote.NoteType.TOP),
    ("Neroli", FragranceNote.NoteType.TOP),
    ("Apple", FragranceNote.NoteType.TOP),
    ("Blackcurrant", FragranceNote.NoteType.TOP),
    ("Tangerine", FragranceNote.NoteType.TOP),
    ("Lime", FragranceNote.NoteType.TOP),
    ("Aldehydes", FragranceNote.NoteType.TOP),
    ("Ginger", FragranceNote.NoteType.TOP),
    ("Rose", FragranceNote.NoteType.MIDDLE),
    ("Jasmine", FragranceNote.NoteType.MIDDLE),
    ("Lavender", FragranceNote.NoteType.MIDDLE),
    ("Cinnamon", FragranceNote.NoteType.MIDDLE),
    ("Cardamom", FragranceNote.NoteType.MIDDLE),
    ("Iris", FragranceNote.NoteType.MIDDLE),
    ("Violet", FragranceNote.NoteType.MIDDLE),
    ("Ylang-Ylang", FragranceNote.NoteType.MIDDLE),
    ("Geranium", FragranceNote.NoteType.MIDDLE),
    ("Peony", FragranceNote.NoteType.MIDDLE),
    ("Nutmeg", FragranceNote.NoteType.MIDDLE),
    ("Saffron", FragranceNote.NoteType.MIDDLE),
    ("Fig", FragranceNote.NoteType.MIDDLE),
    ("Honey", FragranceNote.NoteType.MIDDLE),
    ("Oud", FragranceNote.NoteType.BASE),
    ("Amber", FragranceNote.NoteType.BASE),
    ("Musk", FragranceNote.NoteType.BASE),
    ("Vanilla", FragranceNote.NoteType.BASE),
    ("Sandalwood", FragranceNote.NoteType.BASE),
    ("Patchouli", FragranceNote.NoteType.BASE),
    ("Vetiver", FragranceNote.NoteType.BASE),
    ("Cedar", FragranceNote.NoteType.BASE),
    ("Tonka Bean", FragranceNote.NoteType.BASE),
    ("Leather", FragranceNote.NoteType.BASE),
    ("Tobacco", FragranceNote.NoteType.BASE),
    ("Benzoin", FragranceNote.NoteType.BASE),
    ("Oakmoss", FragranceNote.NoteType.BASE),
    ("Cashmere Wood", FragranceNote.NoteType.BASE),
]

ADJECTIVES = [
    "Velvet",
    "Midnight",
    "Royal",
    "Noir",
    "Lumière",
    "Éclat",
    "Absolu",
    "Intense",
    "Signature",
    "Heritage",
    "Satin",
    "Crimson",
    "Obsidian",
    "Amber",
    "Ivory",
    "Sapphire",
]

NOUNS = [
    "Oud",
    "Amber",
    "Rose",
    "Santal",
    "Cuir",
    "Iris",
    "Musk",
    "Nuit",
    "Or",
    "Jasmin",
    "Vetiver",
    "Patchouli",
    "Ambre",
    "Bois",
    "Encens",
]

DESC_OPENERS = [
    "Композиция открывается",
    "Первые ноты дарят",
    "С первых секунд ощущается",
    "Аромат мгновенно погружает в",
]

DESC_MIDDLES = [
    "в сердце раскрывается благородная глубина, где тёплые аккорды переплетаются с дымной чувственностью.",
    "в пирамиде гармонично сочетаются древесные и цветочные оттенки, создавая образ уверенной элегантности.",
    "сердце композиции подчёркивает утончённость баланса между свежестью и насыщенным шлейфом.",
]

DESC_CLOSERS = [
    "Шлейф оставляет стойкое, дорогое впечатление — для вечера и особых моментов.",
    "Идеален для тех, кто ценит стойкость, характер и безупречный стиль.",
    "Подходит как завершение образа: деликатно, но с характером и долгим звучанием на коже.",
]


def _fetch_placeholder_file(seed: str) -> ContentFile:
    """Загружает JPEG с via.placeholder.com; при ошибке — локальный минимальный JPEG."""
    safe = urllib.parse.quote(seed[:20])
    url = f"https://via.placeholder.com/300x400.jpg?text={safe}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "nota-seed/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        if data:
            return ContentFile(data, name=f"ph_{slugify(seed)[:50]}.jpg")
    except (urllib.error.URLError, OSError, TimeoutError, ValueError):
        pass
    return ContentFile(_MINIMAL_JPEG, name=f"fb_{slugify(seed)[:50]}.jpg")


def _pick_notes_for_product(notes: list[FragranceNote], k: int) -> list[FragranceNote]:
    """3–6 нот; при k ≥ 3 стараемся включить top, middle и base."""
    tops = [n for n in notes if n.type == FragranceNote.NoteType.TOP]
    mids = [n for n in notes if n.type == FragranceNote.NoteType.MIDDLE]
    bases = [n for n in notes if n.type == FragranceNote.NoteType.BASE]
    k = min(k, len(notes))
    chosen: list[FragranceNote] = []
    if k >= 3 and tops and mids and bases:
        chosen = [random.choice(tops), random.choice(mids), random.choice(bases)]
        rest_pool = [n for n in notes if n not in chosen]
        need = k - 3
        if need > 0 and rest_pool:
            chosen.extend(random.sample(rest_pool, k=min(need, len(rest_pool))))
        while len(chosen) < k:
            extra = random.choice(notes)
            if extra not in chosen:
                chosen.append(extra)
    else:
        chosen = random.sample(notes, k=k)
    return chosen


class Command(BaseCommand):
    help = "Заполняет БД демо-данными (категории, бренды, ноты, товары, варианты, изображения)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--products",
            type=int,
            default=None,
            help="Число товаров (если не задано — случайно от 50 до 100).",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=None,
            help="Seed для random (воспроизводимость).",
        )

    def handle(self, *args, **options):
        n_products = options["products"]
        if n_products is None:
            n_products = random.randint(50, 100)
        if not 50 <= n_products <= 100:
            self.stderr.write(
                self.style.ERROR("Число товаров должно быть от 50 до 100 (или опустите --products)."),
            )
            return

        if options["seed"] is not None:
            random.seed(options["seed"])

        with transaction.atomic():
            self._clear()
            categories = self._seed_categories()
            brands = self._seed_brands()
            notes = self._seed_notes()
            products = self._seed_products(n_products, categories, brands, notes)
            self._seed_variants_bulk(products)
            self._seed_images(products)

        self.stdout.write(
            self.style.SUCCESS(
                f"Готово: {len(categories)} категорий, {len(brands)} брендов, {len(notes)} нот, "
                f"{len(products)} товаров, варианты 30/50/100 мл, изображения.",
            ),
        )

    def _clear(self) -> None:
        Product.objects.all().delete()
        Category.objects.all().delete()
        Brand.objects.all().delete()
        FragranceNote.objects.all().delete()

    def _seed_categories(self) -> list[Category]:
        out: list[Category] = []
        for name in CATEGORIES:
            obj, _ = Category.objects.get_or_create(name=name, defaults={"slug": slugify(name)})
            out.append(obj)
        return out

    def _seed_brands(self) -> list[Brand]:
        out: list[Brand] = []
        for name in BRANDS:
            obj, _ = Brand.objects.get_or_create(name=name, defaults={"slug": slugify(name)})
            out.append(obj)
        return out

    def _seed_notes(self) -> list[FragranceNote]:
        out: list[FragranceNote] = []
        for name, ntype in NOTE_DEFINITIONS:
            obj, _ = FragranceNote.objects.get_or_create(
                name=name,
                defaults={"slug": slugify(name), "type": ntype},
            )
            out.append(obj)
        return out

    def _unique_product_name(self, used: set[str]) -> str:
        for _ in range(500):
            name = f"{random.choice(ADJECTIVES)} {random.choice(NOUNS)}"
            if name not in used:
                used.add(name)
                return name
            name = f"{random.choice(ADJECTIVES)} {random.choice(NOUNS)} {random.randint(1, 9999)}"
            if name not in used:
                used.add(name)
                return name
        raise RuntimeError("Не удалось сгенерировать уникальное имя товара")

    def _make_description(self) -> str:
        return (
            f"{random.choice(DESC_OPENERS)} атмосферу редких ингредиентов и тонкой работы парфюмера. "
            f"{random.choice(DESC_MIDDLES)} "
            f"{random.choice(DESC_CLOSERS)}"
        )

    def _category_assignments(self, categories: list[Category], n: int) -> list[Category]:
        k = len(categories)
        base = n // k
        rem = n % k
        seq: list[Category] = []
        for i, c in enumerate(categories):
            seq.extend([c] * (base + (1 if i < rem else 0)))
        random.shuffle(seq)
        return seq

    def _brand_assignments(self, brands: list[Brand], n: int) -> list[Brand]:
        """У каждого бренда несколько товаров: минимум по 3 слота, затем добор."""
        seq: list[Brand] = []
        min_per = 3
        if n < len(brands) * min_per:
            min_per = max(1, n // len(brands))
        for b in brands:
            seq.extend([b] * min_per)
        while len(seq) < n:
            seq.append(random.choice(brands))
        random.shuffle(seq)
        return seq[:n]

    def _seed_products(
        self,
        n_products: int,
        categories: list[Category],
        brands: list[Brand],
        notes: list[FragranceNote],
    ) -> list[Product]:
        cat_seq = self._category_assignments(categories, n_products)
        brand_seq = self._brand_assignments(brands, n_products)
        used_names: set[str] = set()
        to_create: list[Product] = []
        for i in range(n_products):
            name = self._unique_product_name(used_names)
            slug = slugify(name)
            if Product.objects.filter(slug=slug).exists():
                slug = f"{slug}-{i}"
            to_create.append(
                Product(
                    name=name,
                    slug=slug,
                    description=self._make_description(),
                    category=cat_seq[i],
                    brand=brand_seq[i],
                ),
            )
        created = Product.objects.bulk_create(to_create)

        note_by_id = {n.id: n for n in notes}
        for p in created:
            k_notes = random.randint(3, 6)
            chosen = _pick_notes_for_product(notes, k_notes)
            p.notes.set(chosen)

        note_counts: dict[int, int] = {n.id: 0 for n in notes}
        for p in created:
            for nid in p.notes.values_list("id", flat=True):
                note_counts[nid] = note_counts.get(nid, 0) + 1
        low_ids = [nid for nid, c in note_counts.items() if c < 2]
        for nid in low_ids:
            n = note_by_id[nid]
            targets = [p for p in created if not p.notes.filter(pk=n.pk).exists()][:2]
            for p in targets:
                current = list(p.notes.all())
                if len(current) >= 6:
                    current.pop()
                current.append(n)
                p.notes.set(current)

        return created

    def _seed_variants_bulk(self, products: list[Product]) -> None:
        volumes = [
            (Variant.Volume.ML30, Decimal("40"), Decimal("80")),
            (Variant.Volume.ML50, Decimal("70"), Decimal("120")),
            (Variant.Volume.ML100, Decimal("100"), Decimal("250")),
        ]
        variants: list[Variant] = []
        for p in products:
            for vol, lo, hi in volumes:
                price = Decimal(str(round(random.uniform(float(lo), float(hi)), 2)))
                stock = random.randint(0, 50)
                variants.append(
                    Variant(product=p, volume=vol, price=price, stock=stock),
                )
        Variant.objects.bulk_create(variants)

        out_count = max(1, len(products) // 10)
        zero_products = random.sample(products, out_count)
        for p in zero_products:
            Variant.objects.filter(product=p).update(stock=0)

    def _seed_images(self, products: list[Product]) -> None:
        for p in products:
            n_img = random.randint(1, 3)
            main_idx = random.randrange(n_img)
            for i in range(n_img):
                cf = _fetch_placeholder_file(f"{p.slug}-{i}")
                img = ProductImage(product=p, is_main=(i == main_idx))
                img.image.save(f"{p.pk}_{i}.jpg", cf, save=True)
