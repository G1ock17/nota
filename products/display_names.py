"""Название аромата без префикса бренда."""

import re


def strip_brand_prefix(name: str, brand_name: str) -> str:
    """
    «Tom Ford Noir de Noir» + бренд «Tom Ford» → «Noir de Noir».
    Если префикса нет или после удаления пусто — возвращает исходное имя.
    """
    product_name = (name or "").strip()
    brand = (brand_name or "").strip()
    if not product_name or not brand:
        return product_name

    if not product_name.lower().startswith(brand.lower()):
        return product_name

    remainder = product_name[len(brand) :]
    remainder = re.sub(r"^[\s\-–—:]+", "", remainder).strip()
    return remainder or product_name
