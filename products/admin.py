from django.contrib import admin

from .models import (
    Brand,
    Category,
    FragranceNote,
    Order,
    OrderItem,
    Product,
    ProductImage,
    Variant,
)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0


class VariantInline(admin.TabularInline):
    model = Variant
    extra = 0


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("variant", "quantity", "price", "line_total")
    can_delete = False


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)


@admin.register(FragranceNote)
class FragranceNoteAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "type")
    list_filter = ("type",)
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "brand", "category", "year", "country", "created_at")
    list_filter = ("category", "brand", "year", "country")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "description", "country")
    filter_horizontal = ("notes",)
    inlines = (ProductImageInline, VariantInline)


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ("product", "is_main")
    list_filter = ("is_main",)


@admin.register(Variant)
class VariantAdmin(admin.ModelAdmin):
    list_display = ("product", "volume", "price", "stock")
    list_filter = ("volume",)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "email",
        "status",
        "tracking_number",
        "delivery_method",
        "total_price",
        "created_at",
    )
    list_filter = ("status", "delivery_method", "created_at")
    list_editable = ("status", "tracking_number")
    search_fields = ("email", "first_name", "last_name", "phone", "user__username")
    readonly_fields = ("created_at",)
    inlines = (OrderItemInline,)
