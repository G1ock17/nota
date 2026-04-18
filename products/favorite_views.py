from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from .models import Favorite, Product


@require_POST
def favorite_toggle(request):
    if not request.user.is_authenticated:
        return HttpResponseBadRequest("Требуется вход")

    product_id_raw = request.POST.get("product_id")
    try:
        product_pk = int(product_id_raw)
    except (TypeError, ValueError):
        return HttpResponseBadRequest("Некорректный товар")

    product = get_object_or_404(Product, pk=product_pk)
    button = (request.POST.get("button") or "detail").strip()
    context = (request.POST.get("context") or "").strip()
    is_htmx = request.headers.get("HX-Request") == "true"

    existing = Favorite.objects.filter(user=request.user, product=product).first()

    if context == "account":
        if existing:
            existing.delete()
        if is_htmx:
            return HttpResponse()
        return redirect(f"{reverse('account')}?section=favorites")

    added_to_favorites = False
    if existing:
        existing.delete()
    else:
        Favorite.objects.get_or_create(user=request.user, product=product)
        added_to_favorites = True

    ctx = {"product": product, "button": button}
    if is_htmx:
        ctx["favorite_toast_added"] = added_to_favorites
        return render(request, "products/partials/favorite_htmx_response.html", ctx)

    if button == "catalog":
        tpl = "products/partials/favorite_btn_catalog.html"
    else:
        tpl = "products/partials/favorite_btn_detail.html"

    return render(request, tpl, ctx)


@login_required
@require_GET
def favorite_post_auth(request):
    """
    После входа или регистрации: добавить товар в избранное и вернуть на страницу `next`.
    """
    raw = request.GET.get("product")
    try:
        pk = int(raw)
    except (TypeError, ValueError):
        return redirect(reverse("products:catalog"))

    product = get_object_or_404(Product, pk=pk)
    Favorite.objects.get_or_create(user=request.user, product=product)

    next_url = (request.GET.get("next") or "").strip()
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect(reverse("products:product_detail", kwargs={"slug": product.slug}))
