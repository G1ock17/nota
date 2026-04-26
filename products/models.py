import re
from datetime import timedelta

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.text import slugify

User = get_user_model()


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
    name = models.CharField(max_length=255)
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

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:255]
        super().save(*args, **kwargs)

    def first_in_stock_variant(self):
        for variant in self.variants.all():
            if variant.stock > 0:
                return variant
        return None

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
