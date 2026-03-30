from decimal import Decimal, InvalidOperation

from django.db.models import DecimalField, Min, Prefetch, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.views.generic import DetailView, ListView

from .models import Brand, Category, Product, ProductImage, Variant, FragranceNote


def catalog_pagination_entries(page_obj):
    """
    Numbers to show under the catalog: current ±2 (up to 5 pages), plus first/last
    and ellipses when there is a gap. None in the list means an ellipsis span.
    """
    paginator = page_obj.paginator
    num_pages = paginator.num_pages
    current = page_obj.number
    if num_pages <= 1:
        return []

    half = 2
    left = max(1, current - half)
    right = min(num_pages, current + half)
    target_width = min(5, num_pages)
    while right - left + 1 < target_width:
        if left > 1:
            left -= 1
        elif right < num_pages:
            right += 1
        else:
            break

    window = list(range(left, right + 1))
    last = num_pages
    entries = []

    if left > 1:
        entries.append(1)
        if window[0] > 2:
            entries.append(None)
    entries.extend(window)
    if right < last:
        if right < last - 1:
            entries.append(None)
        entries.append(last)

    return entries


class CatalogListView(ListView):
    model = Product
    template_name = "products/catalog.html"
    context_object_name = "product_list"
    paginate_by = 12

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["products/partials/catalog_results.html"]
        return [self.template_name]

    def get_queryset(self):
        qs = (
            Product.objects.select_related("category", "brand")
            .prefetch_related(
                Prefetch(
                    "images",
                    queryset=ProductImage.objects.order_by("-is_main", "id"),
                ),
                "notes",
                Prefetch(
                    "variants",
                    queryset=Variant.objects.order_by("volume"),
                ),
            )
            .annotate(
                min_price=Min(
                    "variants__price",
                    filter=Q(variants__stock__gt=0),
                ),
            )
        )

        params = self.request.GET

        category_slugs = params.getlist("category")
        if category_slugs:
            qs = qs.filter(category__slug__in=category_slugs)

        brand_slugs = params.getlist("brand")
        if brand_slugs:
            qs = qs.filter(brand__slug__in=brand_slugs)

        note_slugs = params.getlist("notes")
        if note_slugs:
            qs = qs.filter(notes__slug__in=note_slugs).distinct()

        volume = params.get("volume")
        if volume:
            if volume in dict(Variant.Volume.choices):
                qs = qs.filter(variants__volume=volume).distinct()

        price_q = Q()
        min_p = params.get("min_price")
        max_p = params.get("max_price")
        if min_p:
            try:
                price_q &= Q(variants__price__gte=Decimal(min_p))
            except (InvalidOperation, ValueError, TypeError):
                pass
        if max_p:
            try:
                price_q &= Q(variants__price__lte=Decimal(max_p))
            except (InvalidOperation, ValueError, TypeError):
                pass
        if price_q:
            qs = qs.filter(price_q).distinct()

        sort = params.get("sort", "newest")
        dec_field = DecimalField(max_digits=12, decimal_places=2)
        high = Value(Decimal("999999999.99"), output_field=dec_field)
        low = Value(Decimal("0"), output_field=dec_field)

        if sort == "price_asc":
            qs = qs.annotate(
                _order_price=Coalesce("min_price", high),
            ).order_by("_order_price", "name")
        elif sort == "price_desc":
            qs = qs.annotate(
                _order_price=Coalesce("min_price", low),
            ).order_by("-_order_price", "name")
        elif sort == "name":
            qs = qs.order_by("name")
        elif sort == "popularity":
            qs = qs.annotate(
                _popularity=Coalesce(Sum("variants__stock"), Value(0)),
            ).order_by("-_popularity", "-created_at")
        else:
            qs = qs.order_by("-created_at")

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        req = self.request.GET.copy()
        if "page" in req:
            del req["page"]
        ctx["filter_query"] = req.urlencode()
        ctx["categories"] = Category.objects.all()
        ctx["brands"] = Brand.objects.all()
        ctx["notes_top"] = FragranceNote.objects.filter(
            type=FragranceNote.NoteType.TOP
        ).order_by("name")
        ctx["notes_middle"] = FragranceNote.objects.filter(
            type=FragranceNote.NoteType.MIDDLE
        ).order_by("name")
        ctx["notes_base"] = FragranceNote.objects.filter(
            type=FragranceNote.NoteType.BASE
        ).order_by("name")
        ctx["current_sort"] = self.request.GET.get("sort", "newest")
        ctx["volume_choices"] = Variant.Volume.choices
        ctx["selected_categories"] = self.request.GET.getlist("category")
        ctx["selected_brands"] = self.request.GET.getlist("brand")
        ctx["selected_notes"] = self.request.GET.getlist("notes")
        ctx["selected_volume"] = self.request.GET.get("volume", "")
        ctx["min_price"] = self.request.GET.get("min_price", "")
        ctx["max_price"] = self.request.GET.get("max_price", "")
        page_obj = ctx.get("page_obj")
        if page_obj is not None:
            ctx["catalog_pagination_entries"] = catalog_pagination_entries(page_obj)
        else:
            ctx["catalog_pagination_entries"] = []
        return ctx


class ProductDetailView(DetailView):
    model = Product
    template_name = "products/product_detail.html"
    context_object_name = "product"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        return (
            Product.objects.select_related("category", "brand")
            .prefetch_related(
                Prefetch(
                    "images",
                    queryset=ProductImage.objects.order_by("-is_main", "id"),
                ),
                "notes",
                Prefetch(
                    "variants",
                    queryset=Variant.objects.order_by("price", "volume"),
                ),
            )
            .annotate(
                min_price=Min(
                    "variants__price",
                    filter=Q(variants__stock__gt=0),
                ),
            )
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        product = self.object
        ctx["in_stock_variants"] = product.variants.filter(stock__gt=0).order_by(
            "volume"
        )
        notes = list(product.notes.all())
        ctx["top_notes"] = [n for n in notes if n.type == FragranceNote.NoteType.TOP]
        ctx["middle_notes"] = [n for n in notes if n.type == FragranceNote.NoteType.MIDDLE]
        ctx["base_notes"] = [n for n in notes if n.type == FragranceNote.NoteType.BASE]

        ctx["related_products"] = (
            Product.objects.filter(category=product.category)
            .exclude(pk=product.pk)
            .select_related("brand")
            .prefetch_related(
                Prefetch(
                    "images",
                    queryset=ProductImage.objects.order_by("-is_main", "id"),
                )
            )
            .annotate(
                min_price=Min(
                    "variants__price",
                    filter=Q(variants__stock__gt=0),
                ),
            )
            .order_by("-created_at")[:4]
        )
        return ctx
