import logging
from decimal import Decimal, InvalidOperation

import requests as http_requests

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, get_user_model
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.db.models import Min, Prefetch, Q, Sum
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import strip_tags
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone

from products.models import Brand, Favorite, FragranceNote, Order, Product, ProductImage, Variant
from products.gift_cards import total_active_balance
from products.models import GiftCard, GiftCardTransaction
from products.cart_utils import cart_total_items, get_cart

from .forms import LoginForm, ProfileSetupForm, RegistrationForm
from .models import DeliveryAddress, LoginAttempt, UserProfile
from .rate_limit import (
    ACTION_PASSWORD_RESET,
    ACTION_REGISTER,
    ACTION_RESEND_VERIFY,
    record_attempt,
    recent_attempts,
)
from products.brand_catalog import catalog_brand_choices, featured_home_brands
from .podbor_matching import parse_quiz_answers, raw_to_match_pct, score_product

User = get_user_model()
logger = logging.getLogger(__name__)

MAX_LOGIN_ATTEMPTS = 5
LOGIN_COOLDOWN_MINUTES = 15
MAX_PASSWORD_RESET_ATTEMPTS = 5
PASSWORD_RESET_COOLDOWN_MINUTES = 15
MAX_RESEND_VERIFY_ATTEMPTS = 3
RESEND_VERIFY_COOLDOWN_MINUTES = 15
MAX_REGISTER_ATTEMPTS = 10
REGISTER_COOLDOWN_MINUTES = 60


def _get_client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    return xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "0.0.0.0")


def _verify_captcha(token: str, ip: str) -> bool:
    secret = getattr(settings, "YANDEX_CAPTCHA_SERVER_KEY", "")
    if not secret:
        return True
    if not (token or "").strip():
        return False
    try:
        resp = http_requests.get(
            "https://smartcaptcha.yandexcloud.net/validate",
            params={"secret": secret, "token": token, "ip": ip},
            timeout=5,
        )
        return resp.json().get("status") == "ok"
    except Exception:
        logger.exception("Yandex SmartCaptcha verification failed")
        # Fail-closed: при ошибке проверки капча считается не пройденной.
        return False


def _send_verification_email(request, user, profile):
    token = profile.generate_email_token()
    verify_url = request.build_absolute_uri(
        reverse("email_verify", kwargs={"token": token})
    )
    subject = "Подтвердите ваш email — Accord"
    html = render_to_string("core/emails/email_verification.html", {
        "user": user,
        "verify_url": verify_url,
    })
    send_mail(
        subject,
        strip_tags(html),
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        html_message=html,
        fail_silently=True,
    )


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
            "featured_brands": featured_home_brands(),
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


def register_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    captcha_key = getattr(settings, "YANDEX_CAPTCHA_CLIENT_KEY", "")

    if request.method == "POST":
        form = RegistrationForm(request.POST)
        ip = _get_client_ip(request)

        if recent_attempts(ip, ACTION_REGISTER, REGISTER_COOLDOWN_MINUTES) >= MAX_REGISTER_ATTEMPTS:
            form.add_error(None, "Слишком много попыток регистрации. Попробуйте позже.")
            return render(request, "core/register.html", {
                "form": form, "captcha_key": captcha_key,
            })

        captcha_token = request.POST.get("smart-token", "")
        if captcha_key and not _verify_captcha(captcha_token, ip):
            record_attempt(ip, ACTION_REGISTER)
            form.add_error(None, "Пожалуйста, подтвердите, что вы не робот.")
            return render(request, "core/register.html", {
                "form": form, "captcha_key": captcha_key,
            })

        if form.is_valid():
            user = form.save()
            profile, _ = UserProfile.objects.get_or_create(user=user)
            _send_verification_email(request, user, profile)
            LoginAttempt.objects.filter(ip_address=ip, username=ACTION_REGISTER).delete()
            return render(request, "core/register_done.html", {"email": user.email})

        record_attempt(ip, ACTION_REGISTER)
    else:
        form = RegistrationForm()

    return render(request, "core/register.html", {
        "form": form,
        "captcha_key": captcha_key,
    })


def email_verify(request, token: str):
    try:
        profile = UserProfile.objects.select_related("user").get(email_token=token)
    except UserProfile.DoesNotExist:
        return render(request, "core/email_verify_result.html", {"status": "invalid"})

    if not profile.is_email_token_valid():
        return render(request, "core/email_verify_result.html", {"status": "expired"})

    profile.email_verified = True
    profile.email_token = ""
    profile.save(update_fields=["email_verified", "email_token"])

    user = profile.user
    user.is_active = True
    user.save(update_fields=["is_active"])

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return redirect("profile_setup")


def resend_verification(request):
    if request.method == "POST":
        ip = _get_client_ip(request)
        if recent_attempts(ip, ACTION_RESEND_VERIFY, RESEND_VERIFY_COOLDOWN_MINUTES) >= MAX_RESEND_VERIFY_ATTEMPTS:
            return render(request, "core/register_done.html", {
                "email": request.POST.get("email", "").strip().lower(),
                "resent": True,
                "rate_limited": True,
            })

        email = request.POST.get("email", "").strip().lower()
        try:
            user = User.objects.get(email=email, is_active=False)
            profile, _ = UserProfile.objects.get_or_create(user=user)
            if not profile.email_verified:
                _send_verification_email(request, user, profile)
        except User.DoesNotExist:
            pass
        record_attempt(ip, ACTION_RESEND_VERIFY)
        return render(request, "core/register_done.html", {
            "email": email,
            "resent": True,
        })
    return redirect("register")


def login_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    ip = _get_client_ip(request)
    attempts = LoginAttempt.recent_failures(ip, LOGIN_COOLDOWN_MINUTES)
    locked = attempts >= MAX_LOGIN_ATTEMPTS
    next_url = request.GET.get("next", "")

    if request.method == "POST":
        next_url = request.POST.get("next", next_url)
        form = LoginForm(request.POST)

        if locked:
            form.add_error(None, f"Слишком много попыток. Подождите {LOGIN_COOLDOWN_MINUTES} минут.")
            return render(request, "core/login.html", {
                "form": form, "next": next_url, "locked": True,
            })

        if form.is_valid():
            email = form.cleaned_data["email"].lower()
            password = form.cleaned_data["password"]

            try:
                user_obj = User.objects.get(email=email)
            except User.DoesNotExist:
                user_obj = None

            user = None
            if user_obj:
                user = authenticate(request, username=user_obj.username, password=password)

            if user is not None:
                if not user.is_active:
                    profile, _ = UserProfile.objects.get_or_create(user=user)
                    if not profile.email_verified:
                        return render(request, "core/register_done.html", {
                            "email": email,
                            "not_verified": True,
                        })
                login(request, user)
                LoginAttempt.objects.filter(ip_address=ip).delete()
                redir = next_url.strip()
                if redir and url_has_allowed_host_and_scheme(
                    redir, allowed_hosts={request.get_host()},
                    require_https=request.is_secure(),
                ):
                    return redirect(redir)
                return redirect("home")
            else:
                LoginAttempt.objects.create(ip_address=ip, username=email)
                remaining = MAX_LOGIN_ATTEMPTS - attempts - 1
                if remaining <= 0:
                    form.add_error(None, f"Слишком много попыток. Подождите {LOGIN_COOLDOWN_MINUTES} минут.")
                else:
                    form.add_error(None, f"Неверный email или пароль. Осталось попыток: {remaining}")
    else:
        form = LoginForm()

    return render(request, "core/login.html", {
        "form": form,
        "next": next_url,
        "locked": locked,
    })


@login_required
def profile_setup(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = ProfileSetupForm(request.POST)
        if form.is_valid():
            d = form.cleaned_data
            if d.get("first_name"):
                request.user.first_name = d["first_name"]
                request.user.save(update_fields=["first_name"])
            if d.get("phone"):
                profile.phone = d["phone"]
            profile.profile_completed = True
            profile.save(update_fields=["phone", "profile_completed"])

            if d.get("city") and d.get("address_line1"):
                DeliveryAddress.objects.create(
                    user=request.user,
                    country=d.get("country", ""),
                    city=d["city"],
                    region="",
                    postal_code=d.get("postal_code", ""),
                    address_line1=d["address_line1"],
                    is_default=True,
                )
            messages.success(request, "Профиль успешно заполнен!")
            return redirect("account")
    else:
        form = ProfileSetupForm(initial={
            "first_name": request.user.first_name,
            "phone": profile.phone,
        })

    return render(request, "core/profile_setup.html", {"form": form})


def password_reset_request(request):
    if request.user.is_authenticated:
        return redirect("home")

    sent = False
    email_value = ""

    if request.method == "POST":
        ip = _get_client_ip(request)
        if recent_attempts(ip, ACTION_PASSWORD_RESET, PASSWORD_RESET_COOLDOWN_MINUTES) >= MAX_PASSWORD_RESET_ATTEMPTS:
            sent = True
            return render(request, "core/password_reset.html", {
                "sent": sent,
                "email": request.POST.get("email", "").strip().lower(),
                "rate_limited": True,
            })

        email_value = request.POST.get("email", "").strip().lower()
        if email_value:
            try:
                user = User.objects.get(email=email_value, is_active=True)
                profile, _ = UserProfile.objects.get_or_create(user=user)
                token = profile.generate_email_token()
                reset_url = request.build_absolute_uri(
                    reverse("password_reset_confirm", kwargs={"token": token})
                )
                html = render_to_string("core/emails/password_reset.html", {
                    "user": user,
                    "reset_url": reset_url,
                })
                send_mail(
                    "Восстановление пароля — Accord",
                    strip_tags(html),
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                    html_message=html,
                    fail_silently=True,
                )
            except User.DoesNotExist:
                pass
            record_attempt(ip, ACTION_PASSWORD_RESET)
            sent = True

    return render(request, "core/password_reset.html", {
        "sent": sent,
        "email": email_value,
    })


def password_reset_confirm(request, token: str):
    try:
        profile = UserProfile.objects.select_related("user").get(email_token=token)
    except UserProfile.DoesNotExist:
        return render(request, "core/password_reset_confirm.html", {"status": "invalid"})

    if not profile.is_email_token_valid():
        return render(request, "core/password_reset_confirm.html", {"status": "expired"})

    error = ""
    if request.method == "POST":
        pw1 = request.POST.get("password1", "")
        pw2 = request.POST.get("password2", "")

        if not pw1 or len(pw1) < 8:
            error = "Пароль должен быть не менее 8 символов."
        elif pw1 != pw2:
            error = "Пароли не совпадают."
        else:
            from django.contrib.auth.password_validation import validate_password
            from django.core.exceptions import ValidationError
            try:
                validate_password(pw1, profile.user)
            except ValidationError as e:
                error = e.messages[0]

        if not error:
            profile.user.set_password(pw1)
            profile.user.save(update_fields=["password"])
            profile.email_token = ""
            profile.save(update_fields=["email_token"])
            return render(request, "core/password_reset_confirm.html", {"status": "success"})

    return render(request, "core/password_reset_confirm.html", {
        "status": "form",
        "token": token,
        "error": error,
    })


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
    raise Http404("Gift cards are temporarily unavailable.")


@login_required
def account_gift_cards(request):
    raise Http404("Gift cards are temporarily unavailable.")


def podbor(request):
    return render(request, "core/podbor.html")


_AVOID_NOTE_FILTERS = {
    "vanilla": (
        Q(notes__name__icontains="ваниль") | Q(notes__name__icontains="vanilla")
    ),
    "musk": (
        Q(notes__name__icontains="мускус") | Q(notes__name__icontains="musk")
    ),
    "patchouli": (
        Q(notes__name__icontains="пачули") | Q(notes__name__icontains="patchouli")
    ),
    "citrus": (
        Q(notes__name__icontains="лимон") | Q(notes__name__icontains="lemon")
        | Q(notes__name__icontains="грейпфрут") | Q(notes__name__icontains="grapefruit")
        | Q(notes__name__icontains="мандарин") | Q(notes__name__icontains="mandarin")
        | Q(notes__name__icontains="цитрус") | Q(notes__name__icontains="citrus")
        | Q(notes__name__icontains="бергамот") | Q(notes__name__icontains="bergamot")
    ),
    "oud": (
        Q(notes__name__icontains="уд") | Q(notes__name__icontains="oud")
        | Q(notes__name__icontains="агар") | Q(notes__name__icontains="agarwood")
    ),
    "rose": (
        Q(notes__name__icontains="роза") | Q(notes__name__icontains="rose")
    ),
    "tobacco": (
        Q(notes__name__icontains="табак") | Q(notes__name__icontains="tobacco")
    ),
    "leather": (
        Q(notes__name__icontains="кожа") | Q(notes__name__icontains="leather")
    ),
    "incense": (
        Q(notes__name__icontains="ладан") | Q(notes__name__icontains="incense")
        | Q(notes__name__icontains="олибанум") | Q(notes__name__icontains="olibanum")
    ),
}

_GENDER_SLUGS = {
    "male":   ["man", "men", "male", "мужской"],
    "female": ["woman", "women", "female", "женский"],
    "unisex": ["unisex", "унисекс"],
}


def podbor_results(request):
    """JSON endpoint: return up to 6 catalog products ranked by quiz answers."""
    answers = parse_quiz_answers(request.GET)

    qs = (
        Product.objects.select_related("brand", "category")
        .prefetch_related(
            Prefetch("images", queryset=ProductImage.objects.order_by("-is_main", "id")),
            Prefetch("variants", queryset=Variant.objects.order_by("price")),
            "notes",
        )
        .annotate(min_price=Min("variants__price", filter=Q(variants__stock__gt=0)))
        .filter(min_price__isnull=False)
    )

    if answers.budget and answers.budget < 999_000:
        qs = qs.filter(min_price__lte=answers.budget)

    for key in answers.avoid:
        avoid_q = _AVOID_NOTE_FILTERS.get(key)
        if avoid_q:
            avoid_ids = Product.objects.filter(avoid_q).values_list("id", flat=True)
            qs = qs.exclude(id__in=avoid_ids)

    candidates = list(qs[:200])
    scored: list[tuple[float, Product]] = []

    for product in candidates:
        sample = product.smallest_in_stock_variant()
        if not sample:
            continue

        note_names: list[str] = []
        note_types: dict[str, str] = {}
        for note in product.notes.all():
            note_names.append(note.name)
            note_types[note.name] = note.type

        raw = score_product(
            note_names=note_names,
            note_types=note_types,
            product_name=product.name,
            description=product.description,
            min_price=float(product.min_price),
            answers=answers,
        )
        scored.append((raw, product))

    scored.sort(key=lambda pair: pair[0], reverse=True)

    results = []
    for rank, (raw, product) in enumerate(scored[:6]):
        sample = product.smallest_in_stock_variant()
        if not sample:
            continue

        image_url = None
        for img in product.images.all():
            if img.is_main:
                image_url = request.build_absolute_uri(img.image.url)
                break
        if image_url is None:
            for img in product.images.all():
                image_url = request.build_absolute_uri(img.image.url)
                break

        notes: dict[str, list[str]] = {"top": [], "middle": [], "base": []}
        for note in product.notes.all():
            if note.type in notes:
                notes[note.type].append(note.name)

        results.append({
            "id": product.id,
            "name": product.name,
            "brand": product.brand.name,
            "slug": product.slug,
            "image_url": image_url,
            "price": float(sample.price),
            "variant_id": sample.id,
            "sample_volume": sample.get_volume_display(),
            "notes": notes,
            "match_pct": raw_to_match_pct(raw, rank),
        })

    return JsonResponse({"results": results})


INFO_PAGES = {
    "delivery": ("Доставка", "core/info/delivery.html"),
    "returns": ("Возврат", "core/info/returns.html"),
    "about": ("О нас", "core/info/about.html"),
    "contacts": ("Контакты", "core/info/contacts.html"),
    "privacy": ("Политика конфиденциальности", "core/info/privacy.html"),
    "offer": ("Оферта", "core/info/offer.html"),
    "requisites": ("Контакты и реквизиты", "core/info/requisites.html"),
}


def info_page(request, page):
    entry = INFO_PAGES.get(page)
    if not entry:
        raise Http404
    page_title, template = entry
    return render(request, template, {"page_title": page_title})
