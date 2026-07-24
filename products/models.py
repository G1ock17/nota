import re
from datetime import timedelta
from decimal import Decimal
import secrets

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.text import slugify

from products.display_names import strip_brand_prefix

User = get_user_model()


def parse_volume_ml(value) -> float | None:
    """Число миллилитров из строки поля volume; None, если не извлечь."""
    value = (value or "").strip()
    match = re.match(r"^(\d+(?:[.,]\d+)?)\s*ml$", value, flags=re.I)
    if match:
        return float(match.group(1).replace(",", "."))
    match2 = re.match(r"^(\d+(?:[.,]\d+)?)", value)
    if match2:
        return float(match2.group(1).replace(",", "."))
    return None


def sort_volume_strings(volumes):
    """Уникальные строки объёмов по возрастанию числа мл (30, 50, 100, не 100, 30, 50)."""
    uniq = list(dict.fromkeys(volumes))

    def key(s):
        ml = parse_volume_ml(s)
        return (ml is None, ml if ml is not None else 0, (s or "").lower())

    uniq.sort(key=key)
    return uniq


class Category(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:255]
        super().save(*args, **kwargs)


class Brand(models.Model):
    name = models.CharField(max_length=100)
    origin = models.CharField(max_length=100, default="")
    tags = models.JSONField(default=list)
    featured = models.BooleanField(default=False)
    slug = models.SlugField(max_length=255, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:255]
        super().save(*args, **kwargs)


class FragranceNote(models.Model):
    class NoteType(models.TextChoices):
        TOP = "top", "Top"
        MIDDLE = "middle", "Middle"
        BASE = "base", "Base"

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    type = models.CharField(max_length=16, choices=NoteType.choices)

    class Meta:
        ordering = ["type", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_type_display()})"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:255]
        super().save(*args, **kwargs)


class Product(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
    )
    brand = models.ForeignKey(
        Brand,
        on_delete=models.PROTECT,
        related_name="products",
    )
    year = models.PositiveIntegerField(null=True, blank=True)
    country = models.CharField(max_length=120, blank=True)
    notes = models.ManyToManyField(FragranceNote, related_name="products", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name

    @property
    def display_name(self) -> str:
        """Совпадает с name после нормализации при сохранении."""
        return self.name

    def save(self, *args, **kwargs):
        if self.brand_id:
            brand_name = ""
            if getattr(self, "brand", None) is not None:
                brand_name = self.brand.name
            if not brand_name:
                brand_name = (
                    Brand.objects.filter(pk=self.brand_id)
                    .values_list("name", flat=True)
                    .first()
                    or ""
                )
            self.name = strip_brand_prefix(self.name, brand_name)
        if not self.slug:
            self.slug = slugify(self.name)[:255]
        super().save(*args, **kwargs)

    def first_in_stock_variant(self):
        for variant in self.variants.all():
            if variant.stock > 0:
                return variant
        return None

    def smallest_in_stock_variant(self):
        """Вариант с минимальным числовым объёмом среди тех, что в наличии (для карточки каталога)."""
        best = None
        best_ml = None
        for variant in self.variants.all():
            if variant.stock <= 0:
                continue
            ml = variant.numeric_volume_ml()
            if ml is None:
                continue
            if best is None or ml < best_ml:
                best = variant
                best_ml = ml
        if best is not None:
            return best
        return self.first_in_stock_variant()

    def variants_sorted_by_volume_numeric(self, *, in_stock_only: bool = False):
        """Варианты по возрастанию числового объёма (для карточки товара и т.п.)."""
        variants = [
            v for v in self.variants.all() if (not in_stock_only or v.stock > 0)
        ]

        def sort_key(v):
            ml = v.numeric_volume_ml()
            return (ml is None, ml if ml is not None else 0, (v.volume or "").lower())

        variants.sort(key=sort_key)
        return variants

    @property
    def is_new(self) -> bool:
        """Новинка: первые 60 дней после появления в каталоге."""
        return self.created_at >= timezone.now() - timedelta(days=60)


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(upload_to="products/%Y/%m/")
    is_main = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_main", "id"]

    def __str__(self) -> str:
        return f"{self.product.name} image"


class Variant(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="variants",
    )
    volume = models.CharField(max_length=32)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField(default=0)

    class Meta:
        ordering = ["volume"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "volume"],
                name="unique_product_volume",
            )
        ]

    def __str__(self) -> str:
        return f"{self.product.name} {self.volume}"

    def get_volume_display(self) -> str:
        """
        Backward-compatible display helper after removing fixed choices.
        Shows `50 ml` for values like `50ml`, otherwise returns raw value.
        """
        value = (self.volume or "").strip()
        match = re.match(r"^(\d+(?:[.,]\d+)?)\s*ml$", value, flags=re.I)
        if match:
            return f"{match.group(1).replace(',', '.')} ml"
        return value

    def numeric_volume_ml(self):
        """Число миллилитров для сортировки; None, если из строки не извлечь."""
        return parse_volume_ml(self.volume)


class Order(models.Model):
    class DeliveryMethod(models.TextChoices):
        COURIER = "courier", "Доставка курьером"

    class Status(models.TextChoices):
        NEW = "new", "Новый"
        PAID = "paid", "Оплачен"
        ASSEMBLING = "assembling", "В сборке"
        SHIPPED = "shipped", "Отправлен"
        DELIVERED = "delivered", "Доставлен"

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="orders",
        null=True,
        blank=True,
    )
    email = models.EmailField()
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=32)
    country = models.CharField(max_length=120)
    address_line1 = models.CharField(max_length=255)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120)
    region = models.CharField(max_length=120)
    postal_code = models.CharField(max_length=32)
    delivery_method = models.CharField(
        max_length=32,
        choices=DeliveryMethod.choices,
        default=DeliveryMethod.COURIER,
    )
    order_note = models.TextField(blank=True)
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.NEW,
    )
    tracking_number = models.CharField(max_length=120, blank=True)
    total_price = models.DecimalField(max_digits=12, decimal_places=2)
    gift_card_debit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    payable_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    ozon_pay_order_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="Заказ Ozon Pay",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        who = self.user.username if self.user_id else self.email
        return f"Order #{self.pk} - {who}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey(Variant, on_delete=models.PROTECT, related_name="order_items")
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self) -> str:
        return f"Order #{self.order_id}: {self.variant} x {self.quantity}"


class Favorite(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="product_favorites",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="favorite_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "product"],
                name="unique_favorite_user_product",
            )
        ]

    def __str__(self) -> str:
        return f"{self.user_id} ♥ {self.product_id}"


class GiftCard(models.Model):
    code = models.CharField(max_length=32, unique=True, db_index=True, blank=True)
    nominal = models.DecimalField(max_digits=12, decimal_places=2)
    balance = models.DecimalField(max_digits=12, decimal_places=2)
    is_activated = models.BooleanField(default=False)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="gift_cards",
        null=True,
        blank=True,
    )
    buyer_email = models.EmailField(blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.code} ({self.balance})"

    @staticmethod
    def generate_code() -> str:
        while True:
            part1 = secrets.token_hex(2).upper()
            part2 = secrets.token_hex(2).upper()
            code = f"GIFT-{part1}-{part2}"
            if not GiftCard.objects.filter(code=code).exists():
                return code

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_at and timezone.now() > self.expires_at)


class GiftCardTransaction(models.Model):
    class TxType(models.TextChoices):
        DEBIT = "debit", "Списание"
        CREDIT = "credit", "Пополнение"
        PURCHASE = "purchase", "Покупка"
        ACTIVATION = "activation", "Активация"

    gift_card = models.ForeignKey(
        GiftCard,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    type = models.CharField(max_length=16, choices=TxType.choices)
    order = models.ForeignKey(
        Order,
        on_delete=models.SET_NULL,
        related_name="gift_card_transactions",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["gift_card", "order", "type"],
                condition=models.Q(type="debit", order__isnull=False),
                name="unique_gift_card_debit_per_order",
            )
        ]

    def __str__(self) -> str:
        return f"{self.gift_card.code}: {self.type} {self.amount}"
