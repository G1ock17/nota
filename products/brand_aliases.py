"""Единое имя бренда при разных написаниях в источниках данных."""

from django.utils.text import slugify

# slug или нормализованное имя → каноническое отображаемое имя
_CANONICAL_BY_SLUG: dict[str, str] = {
    "by-kilian": "By Kilian",
    "kilian": "By Kilian",
    "byredo-parfums": "Byredo",
    "francis-kurkdjian": "Maison Francis Kurkdjian",
    "roja-dove": "Roja",
}


def canonical_brand_name(name: str) -> str:
    raw = (name or "").strip()
    if not raw:
        return raw
    key = slugify(raw)
    return _CANONICAL_BY_SLUG.get(key, raw)
