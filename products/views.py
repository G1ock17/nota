from decimal import Decimal, InvalidOperation

from django.db.models import DecimalField, Min, Prefetch, Q, Value
from django.db.models.functions import Coalesce
from django.views.generic import ListView

from .models import Brand, Category, Product, ProductImage, Variant, FragranceNote


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

        category = params.get("category")
        if category:
            qs = qs.filter(category__slug=category)

        brand = params.get("brand")
        if brand:
            qs = qs.filter(brand__slug=brand)

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
        ctx["fragrance_notes"] = FragranceNote.objects.all()
        ctx["current_sort"] = self.request.GET.get("sort", "newest")
        ctx["volume_choices"] = Variant.Volume.choices
        ctx["selected_category"] = self.request.GET.get("category", "")
        ctx["selected_brand"] = self.request.GET.get("brand", "")
        ctx["selected_notes"] = self.request.GET.getlist("notes")
        ctx["selected_volume"] = self.request.GET.get("volume", "")
        ctx["min_price"] = self.request.GET.get("min_price", "")
        ctx["max_price"] = self.request.GET.get("max_price", "")
        return ctx
