from decimal import Decimal, InvalidOperation

from django.db.models import DecimalField, Max, Min, Prefetch, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.views.generic import DetailView, ListView

from .models import Brand, Category, Product, ProductImage, Variant, FragranceNote


def parse_notes_filter_params(params):
    """
    Разбирает GET-параметры notes: значение может быть одним slug или группой «slug1,slug2»
    (одна логическая нота в разных реестрах). Поддерживается и старый формат — несколько ?notes=.
    """
    result = []
    for raw in params.getlist("notes"):
        raw = (raw or "").strip()
        if not raw:
            continue
        if "," in raw:
            for part in raw.split(","):
                t = part.strip()
                if t:
                    result.append(t)
        else:
            result.append(raw)
    seen = set()
    out = []
    for s in result:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def build_notes_catalog_unique():
    """
    Одна строка фильтра на уникальное имя ноты; в value — все slug этой ноты из разных реестров
    (через запятую), чтобы каталог отбирал товары с любой из связей.
    Только ноты, у которых есть хотя бы один товар в наличии (как в списке каталога).
    """
    groups = {}
    note_qs = (
        FragranceNote.objects.filter(products__variants__stock__gt=0)
        .distinct()
        .order_by("name")
    )
    for n in note_qs:
        key = (n.name or "").strip().lower()
        if not key:
            key = f"__slug__{n.slug}"
        if key not in groups:
            display = (n.name or "").strip() or n.slug
            groups[key] = {"name": display, "slugs": []}
        if n.slug not in groups[key]["slugs"]:
            groups[key]["slugs"].append(n.slug)
    result = []
    for _key in sorted(groups.keys(), key=lambda k: groups[k]["name"].lower()):
        slugs = sorted(groups[_key]["slugs"])
        result.append(
            {
                "name": groups[_key]["name"],
                "slugs": slugs,
                "value": ",".join(slugs),
            }
        )
    return result


def product_search_suggest(request):
    q = (request.GET.get("q") or "").strip()
    if len(q) < 2:
        return JsonResponse({"results": []})

    qs = (
        Product.objects.filter(Q(name__icontains=q) | Q(brand__name__icontains=q))
        .select_related("brand")
        .prefetch_related(
            Prefetch(
                "images",
                queryset=ProductImage.objects.order_by("-is_main", "id"),
            ),
        )
        .annotate(
            min_price=Min(
                "variants__price",
                filter=Q(variants__stock__gt=0),
            ),
        )
        .filter(min_price__isnull=False)
        .distinct()
        .order_by("name")[:10]
    )

    results = []
    for product in qs:
        img = product.images.first()
        min_p = product.min_price
        results.append(
            {
                "slug": product.slug,
                "name": product.name,
                "brand": product.brand.name,
                "image_url": img.image.url if img else "",
                "min_price": str(min_p) if min_p is not None else None,
            }
        )

    return JsonResponse({"results": results})


class SearchListView(ListView):
    model = Product
    template_name = "products/search.html"
    context_object_name = "product_list"
    paginate_by = 24

    def get_queryset(self):
        query = (self.request.GET.get("q") or "").strip()
        qs = (
            Product.objects.select_related("brand")
            .prefetch_related(
                Prefetch(
                    "images",
                    queryset=ProductImage.objects.order_by("-is_main", "id"),
                ),
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
            .filter(min_price__isnull=False)
        )
        if query:
            qs = qs.filter(Q(name__icontains=query) | Q(brand__name__icontains=query))
        return qs.distinct().order_by("name")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["current_query"] = (self.request.GET.get("q") or "").strip()
        return ctx


class CatalogListView(ListView):
    model = Product
    template_name = "products/catalog.html"
    context_object_name = "product_list"
    paginate_by = 24

    def get_template_names(self):
        if not self.request.headers.get("HX-Request"):
            return [self.template_name]
        if self.request.GET.get("load_more") == "1":
            return ["products/partials/catalog_load_more.html"]
        return ["products/partials/catalog_results.html"]

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
            .filter(min_price__isnull=False)
        )

        params = self.request.GET

        query = (params.get("q") or "").strip()
        if query:
            qs = qs.filter(Q(name__icontains=query) | Q(brand__name__icontains=query))

        category_slugs = params.getlist("category")
        if category_slugs:
            qs = qs.filter(category__slug__in=category_slugs)

        brand_slugs = params.getlist("brand")
        if brand_slugs:
            qs = qs.filter(brand__slug__in=brand_slugs)

        note_slugs = parse_notes_filter_params(params)
        if note_slugs:
            qs = qs.filter(notes__slug__in=note_slugs).distinct()

        years = []
        for year_raw in params.getlist("year"):
            try:
                years.append(int(year_raw))
            except (TypeError, ValueError):
                continue
        if years:
            qs = qs.filter(year__in=years)

        countries = [country.strip() for country in params.getlist("country") if country.strip()]
        if countries:
            qs = qs.filter(country__in=countries)

        volume = params.get("volume")
        if volume:
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
        if "load_more" in req:
            del req["load_more"]
        ctx["filter_query"] = req.urlencode()
        ctx["categories"] = Category.objects.all()
        ctx["brands"] = Brand.objects.all()
        notes_catalog_unique = build_notes_catalog_unique()
        ctx["notes_catalog_unique"] = notes_catalog_unique
        selected_notes_raw = self.request.GET.getlist("notes")
        expanded_slugs = set(parse_notes_filter_params(self.request.GET))
        selected_group_values = set()
        for g in notes_catalog_unique:
            gv = g["value"]
            if gv in selected_notes_raw or (set(g["slugs"]) & expanded_slugs):
                selected_group_values.add(gv)
        ctx["notes_selected_group_values"] = list(selected_group_values)
        ctx["notes_filter_selected_count"] = len(selected_group_values)
        ctx["current_sort"] = self.request.GET.get("sort", "newest")
        ctx["current_query"] = (self.request.GET.get("q") or "").strip()
        ctx["volume_choices"] = [
            (v, v)
            for v in Variant.objects.filter(stock__gt=0)
            .values_list("volume", flat=True)
            .distinct()
            .order_by("volume")
        ]
        ctx["selected_categories"] = self.request.GET.getlist("category")
        ctx["selected_brands"] = self.request.GET.getlist("brand")
        ctx["selected_notes"] = selected_notes_raw
        ctx["selected_years"] = self.request.GET.getlist("year")
        ctx["selected_countries"] = self.request.GET.getlist("country")
        ctx["available_years"] = (
            Product.objects.filter(variants__stock__gt=0)
            .exclude(year__isnull=True)
            .values_list("year", flat=True)
            .distinct()
            .order_by("-year")
        )
        ctx["available_countries"] = (
            Product.objects.filter(variants__stock__gt=0)
            .exclude(country="")
            .values_list("country", flat=True)
            .distinct()
            .order_by("country")
        )
        ctx["selected_volume"] = self.request.GET.get("volume", "")
        ctx["min_price"] = self.request.GET.get("min_price", "")
        ctx["max_price"] = self.request.GET.get("max_price", "")
        price_bounds = Variant.objects.filter(stock__gt=0).aggregate(
            min_price=Min("price"),
            max_price=Max("price"),
        )
        min_bound = price_bounds.get("min_price")
        max_bound = price_bounds.get("max_price")
        slider_min = int(min_bound) if min_bound is not None else 0
        slider_max = int(max_bound) if max_bound is not None else 100000
        if slider_max <= slider_min:
            slider_max = slider_min + 1
        ctx["price_slider_min"] = slider_min
        ctx["price_slider_max"] = slider_max
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
            .filter(min_price__isnull=False)
            .order_by("-created_at")[:4]
        )
        return ctx
