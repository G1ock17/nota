"""Загрузка превью ароматов с fimgs.net (Fragrantica)."""

import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.core.files.base import ContentFile
from django.utils.text import slugify

FRAGRANTICA_THUMB_URL = "https://fimgs.net/mdimg/perfume-thumbs/dark-375x500.{perfume_id}.avif"

# slug товара → ID Fragrantica, если URL нет в need_products.json
SLUG_TO_FRAGRANTICA_ID: dict[str, str] = {
    "creed-les-royales-exclusives-pure-white-cologne": "13391",
}


def extract_fragrantica_id(url: str) -> str | None:
    match = re.search(r"-(\d+)\.html\s*$", (url or "").strip(), re.I)
    return match.group(1) if match else None


def fragrantica_thumb_url(perfume_id: str) -> str:
    return FRAGRANTICA_THUMB_URL.format(perfume_id=perfume_id)


def fetch_image_bytes(url: str, *, timeout: int = 25) -> bytes:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def product_slug_from_url_item(item: dict) -> str:
    from products.management.commands.import_need_products import product_slug_from_url

    return product_slug_from_url(item)


def product_slug_from_perfume_item(item: dict) -> str:
    from products.management.commands.import_need_products import product_slug_from_perfume

    return product_slug_from_perfume(item)


def find_fragrantica_url(product_slug: str, product_name: str, items: list[dict]) -> str | None:
    for item in items:
        url = (item.get("url") or "").strip()
        if not url:
            continue
        perfume_slug = product_slug_from_perfume_item(item)
        url_slug = product_slug_from_url_item(item)
        if product_slug in {perfume_slug, url_slug}:
            return url

    name_slug = slugify(product_name)
    if name_slug:
        for item in items:
            if slugify((item.get("perfume") or "").strip()) == name_slug:
                return (item.get("url") or "").strip() or None

    for item in items:
        perfume_slug = slugify((item.get("perfume") or "").strip())
        if perfume_slug and perfume_slug in product_slug:
            return (item.get("url") or "").strip() or None

    return None


def resolve_fragrantica_id(product_slug: str, product_name: str, items: list[dict]) -> str | None:
    override = SLUG_TO_FRAGRANTICA_ID.get(product_slug)
    if override:
        return override
    url = find_fragrantica_url(product_slug, product_name, items)
    if url:
        return extract_fragrantica_id(url)
    return None


def download_fragrantica_thumbnail(perfume_id: str) -> bytes:
    url = fragrantica_thumb_url(perfume_id)
    try:
        return fetch_image_bytes(url)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise RuntimeError(f"Не удалось скачать {url}: {exc}") from exc


def save_product_thumbnail(product, perfume_id: str, *, replace: bool = False) -> None:
    from products.models import ProductImage

    if replace:
        product.images.all().delete()
    elif product.images.exists():
        return

    content = download_fragrantica_thumbnail(perfume_id)
    filename = f"{product.slug}-fragrantica-{perfume_id}.avif"
    image_obj = ProductImage(product=product, is_main=True)
    image_obj.image.save(filename, ContentFile(content), save=True)
