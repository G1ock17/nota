from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from products.brand_aliases import canonical_brand_name
from products.models import Brand, Product

# (slug источника, slug цели) — объединение дублей в БД
PRESET_MERGES: list[tuple[str, str]] = [
    ("by-kilian", "kilian"),
]


class Command(BaseCommand):
    help = "Переносит товары с одного бренда на другой и удаляет пустой бренд-дубль"

    def add_arguments(self, parser):
        parser.add_argument(
            "--from-slug",
            type=str,
            help="Slug бренда-источника (например: by-kilian)",
        )
        parser.add_argument(
            "--into-slug",
            type=str,
            help="Slug целевого бренда (например: kilian)",
        )
        parser.add_argument(
            "--preset",
            action="store_true",
            help="Выполнить встроенные объединения (by-kilian → kilian)",
        )
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        merges: list[tuple[str, str]] = []
        if options["preset"]:
            merges.extend(PRESET_MERGES)
        from_slug = (options["from_slug"] or "").strip()
        into_slug = (options["into_slug"] or "").strip()
        if from_slug and into_slug:
            merges.append((from_slug, into_slug))
        if not merges:
            raise CommandError("Укажите --preset или пару --from-slug / --into-slug")

        dry_run = options["dry_run"]
        for source_slug, target_slug in merges:
            self._merge_one(source_slug, target_slug, dry_run=dry_run)

    def _merge_one(self, source_slug: str, target_slug: str, *, dry_run: bool) -> None:
        source = Brand.objects.filter(slug=source_slug).first()
        target = Brand.objects.filter(slug=target_slug).first()
        if source is None:
            self.stdout.write(self.style.WARNING(f"Бренд не найден: {source_slug}"))
            return
        if target is None:
            raise CommandError(f"Целевой бренд не найден: {target_slug}")

        count = Product.objects.filter(brand=source).count()
        self.stdout.write(
            f"{source.name} ({source_slug}) -> {target.name} ({target_slug}): "
            f"{count} товаров"
        )
        if dry_run:
            return

        with transaction.atomic():
            Product.objects.filter(brand=source).update(brand=target)
            canonical = canonical_brand_name(target.name)
            if target.name != canonical:
                target.name = canonical
                target.save(update_fields=["name"])
            source.delete()

        self.stdout.write(self.style.SUCCESS(f"Объединено, бренд {source_slug} удалён."))
