from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.views import LoginView
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic.edit import FormView

from products.models import Order
from products.cart_utils import cart_total_items, get_cart

from .models import DeliveryAddress, UserProfile
from .brand_constants import FEATURED_HOME_BRANDS


def home(request):
    return render(request, "core/home.html", {"featured_brands": FEATURED_HOME_BRANDS})


class SiteLoginView(LoginView):
    template_name = 'core/login.html'
    redirect_authenticated_user = True


class RegisterView(FormView):
    template_name = 'core/register.html'
    form_class = UserCreationForm
    success_url = reverse_lazy('login')

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
