"""Бренды, представленные в каталоге (есть товары в наличии)."""

from django.db.models import Count, Q

from products.models import Brand

FEATURED_HOME_SLUGS = [
    "giorgio-armani",
    "chanel",
    "givenchy",
    "dior",
    "yves-saint-laurent",
    "burberry",
    "xerjoff",
    "by-kilian",
    "parfums-de-marly",
    "bvlgari",
    "creed",
    "tom-ford",
    "amouage",
    "louis-vuitton",
    "hermes",
    "gucci",
]


def brands_with_available_products():
    return (
        Brand.objects.annotate(
            available_products=Count(
                "products",
                filter=Q(products__variants__stock__gt=0),
                distinct=True,
            ),
        )
        .filter(available_products__gt=0)
        .order_by("-featured", "name")
    )


def catalog_brand_choices():
    """Список (название, slug) для каталога — все бренды с товарами."""
    return [(brand.name, brand.slug) for brand in brands_with_available_products()]


def featured_home_brands():
    """16 топовых брендов для главной страницы."""
    brands = (
        Brand.objects.filter(slug__in=FEATURED_HOME_SLUGS)
        .annotate(
            available_products=Count(
                "products",
                filter=Q(products__variants__stock__gt=0),
                distinct=True,
            ),
        )
        .filter(available_products__gt=0)
    )
    order = {slug: i for i, slug in enumerate(FEATURED_HOME_SLUGS)}
    sorted_brands = sorted(brands, key=lambda b: order.get(b.slug, 999))
    return [(b.name, b.slug) for b in sorted_brands]
