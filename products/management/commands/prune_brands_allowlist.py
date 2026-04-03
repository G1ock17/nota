"""
Delete all products and brands whose slug is not on the allowlist.

Removes OrderItems that reference variants of deleted products first (Variant is PROTECTed).
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count
from django.utils.text import slugify

from products.models import Brand, Order, OrderItem, Product, Variant


# Display names from product owner; slugified for matching Brand.slug
ALLOWED_BRAND_NAMES = [
    "Amouage",
    "Attar Collection",
    "Burberry",
    "Byredo",
    "Bvlgari",
    "Chanel",
    "Creed",
    "Christian Dior",
    "Carolina Herrera",
    "Ex Nihilo",
    "Escentric Molecules",
    "Initio Parfums Prives",
    "Franck Boclet",
    "Frederic Malle",
    "Genyum",
    "Gucci",
    "Givenchy",
    "Giorgio Armani",
    "Giardini di Toscana",
    "Hugo Boss",
    "Hermes",
    "Hormone",
    "Jo Malone",
    "Jean Paul Gaultier",
    "Kajal",
    "Kilian",
    "Le Labo",
    "Lancome",
    "Louis Vuitton",
    "Montale",
    "Maison Francis Kurkdjian",
    "Marc-Antoine Barrois",
    "Marc Jacobs",
    "Nasomatto",
    "Nishane",
    "Narciso Rodriguez",
    "Orto Parisi",
    "Parfums de Marly",
    "Paco Rabanne",
    "Roja",
    "Sospiro Perfumes",
    "Tom Ford",
    "Trussardi",
    "Tiziana Terenzi",
    "Viktor & Rolf",
    "Versace",
    "Xerjoff",
    "Yves Saint Laurent",
    "Zarkoperfume",
    "Zadig et Voltaire",
    "Zoologist",
    "Zielinski & Rozen",
    "Emporio Armani",
    "Clive Christian",
    "Essential Parfums",
    "Vilhelm Parfumerie",
    "By Kilian",
]

# Same brands under different names in the database / import data
EXTRA_ALLOWED_SLUGS = frozenset(
    {
        "byredo-parfums",
        "francis-kurkdjian",
        "roja-dove",
    }
)


def build_allowed_slugs() -> frozenset[str]:
    slugs = {slugify(name.strip()) for name in ALLOWED_BRAND_NAMES if name.strip()}
    slugs |= EXTRA_ALLOWED_SLUGS
    return frozenset(slugs)


class Command(BaseCommand):
    help = "Delete brands and products not on the fixed allowlist."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print counts only, do not delete.",
        )

    def handle(self, *args, **options):
        allowed = build_allowed_slugs()
        bad_brands = Brand.objects.exclude(slug__in=allowed)
        bad_brand_ids = list(bad_brands.values_list("pk", flat=True))
        n_brands = len(bad_brand_ids)
        n_products = Product.objects.filter(brand_id__in=bad_brand_ids).count()
        variant_qs = Variant.objects.filter(product__brand_id__in=bad_brand_ids)
        n_variants = variant_qs.count()
        n_order_items = OrderItem.objects.filter(variant__in=variant_qs).count()

        self.stdout.write(
            f"Allowlist: {len(allowed)} slugs | "
            f"Removing brands: {n_brands}, products: {n_products}, "
            f"variants: {n_variants}, order_items: {n_order_items}"
        )

        if options["dry_run"]:
            return

        with transaction.atomic():
            if n_order_items:
                deleted_oi, _ = OrderItem.objects.filter(
                    variant__in=variant_qs
                ).delete()
                self.stdout.write(f"Deleted {deleted_oi} order item row(s).")
            empty_orders = Order.objects.annotate(_n=Count("items")).filter(_n=0)
            eo_count = empty_orders.count()
            if eo_count:
                empty_orders.delete()
                self.stdout.write(f"Deleted {eo_count} empty order(s).")

            prod_deleted, prod_details = Product.objects.filter(
                brand_id__in=bad_brand_ids
            ).delete()
            self.stdout.write(f"Product cascade delete: {prod_details}")

            brand_deleted, _ = Brand.objects.filter(pk__in=bad_brand_ids).delete()
            self.stdout.write(f"Deleted {brand_deleted} brand(s).")

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Remaining brands: {Brand.objects.count()}, "
                f"products: {Product.objects.count()}."
            )
        )
