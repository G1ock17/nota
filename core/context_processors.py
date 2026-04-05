from products.cart_utils import cart_total_items, get_cart
from products.models import ProductImage

from .brand_constants import MEGA_MENU_BRANDS

_MEGA_PLACEHOLDER = (
    "https://images.unsplash.com/photo-1528740561666-dc2479dc08ab"
    "?auto=format&fit=crop&w=96&q=70"
)


def cart_context(request):
    return {"cart_item_count": cart_total_items(get_cart(request))}


def nav_mega_menu(request):
    slugs = [pair[1] for pair in MEGA_MENU_BRANDS]
    slug_to_url = {}
    qs = (
        ProductImage.objects.filter(product__brand__slug__in=slugs)
        .select_related("product__brand")
        .order_by("product__brand__slug", "-is_main", "id")
    )
    for img in qs:
        s = img.product.brand.slug
        if s not in slug_to_url:
            slug_to_url[s] = img.image.url

    items = [
        {
            "name": name,
            "slug": slug,
            "thumb_url": slug_to_url.get(slug) or _MEGA_PLACEHOLDER,
        }
        for name, slug in MEGA_MENU_BRANDS
    ]
    return {"nav_mega_brands": items}
