from urllib.parse import urlencode
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.views import LoginView
from django.db.models import Min, Prefetch, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.views.generic.edit import FormView

from products.models import Brand, Favorite, Order, Product, ProductImage, Variant
from products.gift_cards import total_active_balance
from products.models import GiftCard, GiftCardTransaction
from products.cart_utils import cart_total_items, get_cart

from .models import DeliveryAddress, UserProfile
from .brand_constants import FEATURED_HOME_BRANDS


def home(request):
    featured_products = (
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
        .order_by("-created_at")[:4]
    )
    return render(
        request,
        "core/home.html",
        {
            "featured_brands": FEATURED_HOME_BRANDS,
            "featured_products": featured_products,
        },
    )


def brands(request):
    brands_payload = [
        {
            "name": brand.name,
            "origin": brand.origin or "",
            "tags": brand.tags if isinstance(brand.tags, list) else [],
            "featured": bool(brand.featured),
            "slug": brand.slug,
        }
        for brand in Brand.objects.all().order_by("name")
    ]
    return render(request, "brands.html", {"brands_payload": brands_payload})


class SiteLoginView(LoginView):
    template_name = 'core/login.html'
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        n = ctx.get(self.redirect_field_name) or self.request.GET.get(self.redirect_field_name, "")
        ctx["next"] = n
        return ctx


class RegisterView(FormView):
    template_name = 'core/register.html'
    form_class = UserCreationForm
    success_url = reverse_lazy('login')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["next"] = self.request.GET.get("next", "")
        return ctx

    def get_success_url(self):
        next_path = (self.request.POST.get("next") or self.request.GET.get("next") or "").strip()
        if next_path and url_has_allowed_host_and_scheme(
            next_path,
            allowed_hosts={self.request.get_host()},
            require_https=self.request.is_secure(),
        ):
            return f"{reverse('login')}?{urlencode({'next': next_path})}"
        return str(reverse_lazy("login"))

    def form_valid(self, form):
        form.save()
        return super().form_valid(form)


@login_required
def account(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "update_profile":
            request.user.first_name = request.POST.get("first_name", "").strip()
            request.user.last_name = request.POST.get("last_name", "").strip()
            request.user.save(update_fields=["first_name", "last_name"])

            profile.phone = request.POST.get("phone", "").strip()
            birth_date_raw = request.POST.get("birth_date", "").strip()
            profile.birth_date = birth_date_raw or None
            profile.save(update_fields=["phone", "birth_date"])
            return redirect("account")

        if action == "add_address":
            country = request.POST.get("country", "").strip()
            city = request.POST.get("city", "").strip()
            region = request.POST.get("region", "").strip()
            postal_code = request.POST.get("postal_code", "").strip()
            address_line1 = request.POST.get("address_line1", "").strip()
            address_line2 = request.POST.get("address_line2", "").strip()
            make_default = request.POST.get("is_default") == "on"

            if country and city and region and postal_code and address_line1:
                if make_default:
                    DeliveryAddress.objects.filter(user=request.user).update(is_default=False)
                elif not DeliveryAddress.objects.filter(user=request.user).exists():
                    make_default = True
                DeliveryAddress.objects.create(
                    user=request.user,
                    country=country,
                    city=city,
                    region=region,
                    postal_code=postal_code,
                    address_line1=address_line1,
                    address_line2=address_line2,
                    is_default=make_default,
                )
            return redirect("account")

        if action == "set_default_address":
            address_id = request.POST.get("address_id")
            address = DeliveryAddress.objects.filter(
                id=address_id, user=request.user
            ).first()
            if address:
                DeliveryAddress.objects.filter(user=request.user).update(is_default=False)
                address.is_default = True
                address.save(update_fields=["is_default"])
            return redirect("account")

        if action == "update_address":
            address_id = request.POST.get("address_id")
            address = DeliveryAddress.objects.filter(
                id=address_id, user=request.user
            ).first()
            if address:
                country = request.POST.get("country", "").strip()
                city = request.POST.get("city", "").strip()
                region = request.POST.get("region", "").strip()
                postal_code = request.POST.get("postal_code", "").strip()
                address_line1 = request.POST.get("address_line1", "").strip()
                address_line2 = request.POST.get("address_line2", "").strip()
                make_default = request.POST.get("is_default") == "on"

                if country and city and region and postal_code and address_line1:
                    if make_default:
                        DeliveryAddress.objects.filter(user=request.user).update(
                            is_default=False
                        )
                    address.country = country
                    address.city = city
                    address.region = region
                    address.postal_code = postal_code
                    address.address_line1 = address_line1
                    address.address_line2 = address_line2
                    address.is_default = make_default or address.is_default
                    address.save(
                        update_fields=[
                            "country",
                            "city",
                            "region",
                            "postal_code",
                            "address_line1",
                            "address_line2",
                            "is_default",
                        ]
                    )
            return redirect("account")

        if action == "delete_address":
            address_id = request.POST.get("address_id")
            address = DeliveryAddress.objects.filter(
                id=address_id, user=request.user
            ).first()
            if address:
                was_default = address.is_default
                address.delete()
                if was_default:
                    new_default = DeliveryAddress.objects.filter(user=request.user).first()
                    if new_default:
                        new_default.is_default = True
                        new_default.save(update_fields=["is_default"])
            return redirect("account")

        if action == "activate_gift_card":
            code = (request.POST.get("gift_code") or "").strip().upper()
            if code:
                card = GiftCard.objects.filter(code=code).first()
                if not card:
                    return redirect(f"{reverse('account')}?section=gift&gift_error=not_found")
                if card.is_expired:
                    return redirect(f"{reverse('account')}?section=gift&gift_error=expired")
                if card.is_activated and card.user_id and card.user_id != request.user.id:
                    return redirect(f"{reverse('account')}?section=gift&gift_error=used_by_other")
                if card.is_activated and card.user_id == request.user.id:
                    return redirect(f"{reverse('account')}?section=gift&gift_error=already_mine")
                card.is_activated = True
                card.user = request.user
                card.activated_at = timezone.now()
                card.save(update_fields=["is_activated", "user", "activated_at", "updated_at"])
                GiftCardTransaction.objects.create(
                    gift_card=card,
                    amount=Decimal("0.00"),
                    type=GiftCardTransaction.TxType.ACTIVATION,
                )
                return redirect(f"{reverse('account')}?section=gift&gift_ok=1")
            return redirect(f"{reverse('account')}?section=gift&gift_error=empty")

    orders = (
        Order.objects.filter(user=request.user)
        .annotate(items_qty=Sum("items__quantity"))
        .prefetch_related("items__variant__product__brand", "items__variant__product__images")
        .order_by("-created_at")
    )
    recent_orders = orders[:4]
    total_orders = orders.count()
    total_spent = orders.aggregate(total=Sum("total_price")).get("total") or 0
    cart_count = cart_total_items(get_cart(request))
    addresses = DeliveryAddress.objects.filter(user=request.user)

    order_items_count = (
        Order.objects.filter(user=request.user)
        .aggregate(total_items=Sum("items__quantity"))
        .get("total_items")
        or 0
    )

    favorite_entries = list(
        Favorite.objects.filter(user=request.user)
        .select_related("product__brand", "product__category")
        .prefetch_related(
            Prefetch(
                "product__images",
                queryset=ProductImage.objects.order_by("-is_main", "id"),
            ),
            Prefetch(
                "product__variants",
                queryset=Variant.objects.order_by("volume"),
            ),
        )
        .order_by("-created_at")
    )
    gift_cards = GiftCard.objects.filter(user=request.user, is_activated=True).order_by("-activated_at")
    gift_total_balance = total_active_balance(request.user)

    return render(
        request,
        "core/account.html",
        {
            "profile": profile,
            "orders": orders,
            "recent_orders": recent_orders,
            "total_orders": total_orders,
            "total_spent": total_spent,
            "cart_count": cart_count,
            "order_items_count": order_items_count,
            "addresses": addresses,
            "favorite_entries": favorite_entries,
            "gift_cards": gift_cards,
            "gift_total_balance": gift_total_balance,
            "gift_error": request.GET.get("gift_error", ""),
            "gift_ok": request.GET.get("gift_ok") == "1",
        },
    )


@login_required
def order_detail(request, order_id: int):
    order = get_object_or_404(
        Order.objects.prefetch_related("items__variant__product__brand", "items__variant__product__images"),
        id=order_id,
        user=request.user,
    )
    return render(request, "core/order_detail.html", {"order": order})


def gift_cards_catalog(request):
    if request.method == "POST":
        nominal_raw = (request.POST.get("nominal") or "").strip()
        custom_raw = (request.POST.get("custom_nominal") or "").strip()
        email = (request.POST.get("email") or "").strip()
        raw_value = custom_raw or nominal_raw
        try:
            nominal = Decimal(raw_value)
        except (InvalidOperation, TypeError):
            return render(
                request,
                "core/gift_cards.html",
                {"purchase_error": "Укажите корректный номинал.", "presets": [1000, 2000, 5000]},
            )
        if nominal <= 0:
            return render(
                request,
                "core/gift_cards.html",
                {"purchase_error": "Номинал должен быть больше 0.", "presets": [1000, 2000, 5000]},
            )
        card = GiftCard.objects.create(
            code=GiftCard.generate_code(),
            nominal=nominal,
            balance=nominal,
            buyer_email=email,
        )
        GiftCardTransaction.objects.create(
            gift_card=card,
            amount=nominal,
            type=GiftCardTransaction.TxType.PURCHASE,
        )
        return render(
            request,
            "core/gift_cards.html",
            {
                "purchase_ok": True,
                "created_code": card.code,
                "presets": [1000, 2000, 5000],
            },
        )

    return render(request, "core/gift_cards.html", {"presets": [1000, 2000, 5000]})


@login_required
def account_gift_cards(request):
    return redirect(f"{reverse('account')}?section=gift")
