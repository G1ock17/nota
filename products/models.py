from django.db import models
from django.utils.text import slugify


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
    class Volume(models.TextChoices):
        ML30 = "30ml", "30 ml"
        ML50 = "50ml", "50 ml"
        ML100 = "100ml", "100 ml"

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="variants",
    )
    volume = models.CharField(max_length=16, choices=Volume.choices)
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
