import re
import sys
import time

from deep_translator import GoogleTranslator

from django.core.management.base import BaseCommand
from django.db.models import Q

from products.models import Product


def is_russian(text: str) -> bool:
    cyrillic = len(re.findall(r"[а-яА-ЯёЁ]", text))
    latin = len(re.findall(r"[a-zA-Z]", text))
    if cyrillic + latin == 0:
        return True
    return cyrillic / (cyrillic + latin) > 0.3


def translate_text(text: str) -> str:
    translator = GoogleTranslator(source="en", target="ru")
    if len(text) <= 4500:
        return translator.translate(text)
    chunks = []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    current = ""
    for s in sentences:
        if len(current) + len(s) + 1 > 4500:
            chunks.append(current.strip())
            current = s
        else:
            current = f"{current} {s}" if current else s
    if current.strip():
        chunks.append(current.strip())
    translated = []
    for chunk in chunks:
        translated.append(translator.translate(chunk))
        time.sleep(0.5)
    return " ".join(translated)


class Command(BaseCommand):
    help = "Translate English product descriptions to Russian"

    def add_arguments(self, parser):
        parser.add_argument("--delay", type=float, default=1.0)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--batch-size", type=int, default=15)
        parser.add_argument("--batch-pause", type=int, default=60)

    def handle(self, *args, **options):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

        delay = max(options["delay"], 0.3)
        dry_run = options["dry_run"]
        limit = options["limit"]
        batch_size = options["batch_size"]
        batch_pause = options["batch_pause"]

        products = list(
            Product.objects.exclude(
                Q(description="") | Q(description__isnull=True)
            ).order_by("slug")
        )

        english_products = [p for p in products if not is_russian(p.description)]
        if limit > 0:
            english_products = english_products[:limit]

        total = len(english_products)
        if not total:
            self.stdout.write(self.style.WARNING("No English descriptions found."))
            return

        self.stderr.write(f"Found {total} English descriptions to translate")
        self.stderr.flush()

        updated = 0
        errors = 0
        requests_in_batch = 0

        for idx, product in enumerate(english_products, start=1):
            if requests_in_batch >= batch_size:
                self.stderr.write(
                    f"[{idx}/{total}] batch pause {batch_pause}s "
                    f"(+{updated} so far)..."
                )
                self.stderr.flush()
                time.sleep(batch_pause)
                requests_in_batch = 0

            try:
                translated = translate_text(product.description)
                if not translated or not translated.strip():
                    errors += 1
                    self.stderr.write(
                        f"[{idx}/{total}] EMPTY {product.slug}"
                    )
                    self.stderr.flush()
                    time.sleep(delay)
                    continue

                if not dry_run:
                    product.description = translated
                    product.save(update_fields=["description"])

                updated += 1
                requests_in_batch += 1

            except Exception as exc:
                errors += 1
                self.stderr.write(f"[{idx}/{total}] FAIL {product.slug}: {exc}")
                self.stderr.flush()

            if idx % 25 == 0 or idx == total:
                self.stderr.write(f"[{idx}/{total}] +{updated}")
                self.stderr.flush()

            time.sleep(delay)

        prefix = "DRY-RUN: " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{prefix}Done: translated {updated}, errors {errors}"
            )
        )
