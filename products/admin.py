from django.contrib import admin

from .models import Brand, Category, FragranceNote, Product, ProductImage, Variant


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0


class VariantInline(admin.TabularInline):
    model = Variant
    extra = 0


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
    list_display = ("name", "slug", "brand", "category", "created_at")
    list_filter = ("category", "brand")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "description")
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
