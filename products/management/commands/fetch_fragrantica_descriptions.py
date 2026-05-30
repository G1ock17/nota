import gzip
import json
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from products.models import Product


UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def com_to_ru(url: str) -> str:
    return url.replace(
        "https://www.fragrantica.com/perfume/",
        "https://www.fragrantica.ru/perfume/",
    )


def fetch_html(url: str, timeout: int = 20) -> str:
    req = Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    try:
        return gzip.decompress(raw).decode("utf-8", errors="replace")
    except (gzip.BadGzipFile, OSError):
        return raw.decode("utf-8", errors="replace")


def extract_description(html: str) -> str:
    match = re.search(
        r'itemprop="description"[^>]*>\s*(.*?)\s*</div>',
        html,
        re.DOTALL,
    )
    if not match:
        return ""

    block = match.group(1)
    block = re.sub(
        r"<blockquote[^>]*>.*?</blockquote>",
        "", block, flags=re.DOTALL | re.IGNORECASE,
    )
    block = re.sub(
        r'<div[^>]*class="[^"]*fragrantica-blockquote[^"]*"[^>]*>.*?</div>',
        "", block, flags=re.DOTALL | re.IGNORECASE,
    )

    text = re.sub(r"<[^>]+>", "", block)
    text = text.replace("&amp;", "&").replace("&#039;", "'").replace("&quot;", '"')
    text = re.sub(r"\s+", " ", text).strip()
    return text


class Command(BaseCommand):
    help = "Fetch fragrance descriptions from Fragrantica"

    def add_arguments(self, parser):
        parser.add_argument(
            "--json", type=str, default="need_products.json",
        )
        parser.add_argument("--slug", type=str, default="")
        parser.add_argument("--all", action="store_true")
        parser.add_argument("--delay", type=float, default=8.0)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--batch-size", type=int, default=5)
        parser.add_argument("--batch-pause", type=int, default=180)

    def handle(self, *args, **options):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

        json_path = Path(options["json"])
        if not json_path.exists():
            raise CommandError(f"JSON not found: {json_path}")

        with json_path.open("r", encoding="utf-8") as f:
            items = json.load(f)
        if not isinstance(items, list):
            raise CommandError("JSON must be an array")

        from products.management.commands.import_need_products import (
            product_slug_from_perfume,
            product_slug_from_url,
        )

        slug_to_url: dict[str, str] = {}
        for item in items:
            url = (item.get("url") or "").strip()
            if not url:
                continue
            for s in (product_slug_from_perfume(item), product_slug_from_url(item)):
                if s:
                    slug_to_url[s] = url

        only_slug = (options["slug"] or "").strip()
        fetch_all = options["all"]
        dry_run = options["dry_run"]
        delay = max(float(options["delay"]), 0.5)
        limit = int(options["limit"])
        batch_size = int(options["batch_size"])
        batch_pause = int(options["batch_pause"])

        qs = Product.objects.all().order_by("slug")
        if only_slug:
            qs = qs.filter(slug=only_slug)
        elif not fetch_all:
            qs = qs.filter(Q(description="") | Q(description__isnull=True))

        products = list(qs)
        if limit > 0:
            products = products[:limit]

        if not products:
            self.stdout.write(self.style.WARNING("No products to process."))
            return

        updated = 0
        no_url = 0
        fetch_err = 0
        empty_desc = 0
        skipped = 0
        total = len(products)
        requests_in_batch = 0

        for idx, product in enumerate(products, start=1):
            com_url = slug_to_url.get(product.slug)
            if not com_url:
                no_url += 1
                continue

            if requests_in_batch >= batch_size:
                self.stderr.write(
                    f"[{idx}/{total}] batch pause {batch_pause}s "
                    f"(+{updated} so far)..."
                )
                self.stderr.flush()
                time.sleep(batch_pause)
                requests_in_batch = 0

            ru_url = com_to_ru(com_url)
            urls_to_try = [ru_url, com_url]
            html = None

            for try_url in urls_to_try:
                for attempt in range(4):
                    try:
                        html = fetch_html(try_url, timeout=15)
                        break
                    except HTTPError as exc:
                        if exc.code == 429:
                            if try_url == ru_url:
                                break
                            wait = min(delay * (4 ** (attempt + 1)), 300)
                            self.stderr.write(
                                f"[{idx}/{total}] 429, waiting {wait:.0f}s..."
                            )
                            self.stderr.flush()
                            time.sleep(wait)
                            continue
                        if attempt == 3:
                            fetch_err += 1
                            self.stderr.write(
                                f"[{idx}/{total}] FAIL {product.slug}: {exc}"
                            )
                            self.stderr.flush()
                    except (URLError, TimeoutError, OSError) as exc:
                        if attempt == 3:
                            fetch_err += 1
                            self.stderr.write(
                                f"[{idx}/{total}] FAIL {product.slug}: {exc}"
                            )
                            self.stderr.flush()
                        else:
                            time.sleep(delay * 2)
                if html is not None:
                    break

            if html is None:
                time.sleep(delay)
                continue

            requests_in_batch += 1

            desc = extract_description(html)
            if not desc:
                empty_desc += 1
                time.sleep(delay)
                continue

            if product.description == desc:
                skipped += 1
                time.sleep(delay)
                continue

            if not dry_run:
                product.description = desc
                product.save(update_fields=["description"])

            updated += 1

            if idx % 25 == 0 or idx == total:
                self.stderr.write(f"[{idx}/{total}] +{updated}")
                self.stderr.flush()

            time.sleep(delay)

        prefix = "DRY-RUN: " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{prefix}Done: updated {updated}, "
                f"no URL {no_url}, fetch errors {fetch_err}, "
                f"empty descriptions {empty_desc}, "
                f"unchanged {skipped}"
            )
        )
