from django.contrib import admin

from .models import (
    Brand,
    Category,
    Favorite,
    FragranceNote,
    GiftCard,
    GiftCardTransaction,
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


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "created_at")
    list_filter = ("created_at",)
    search_fields = ("user__username", "product__name")
    autocomplete_fields = ("user", "product")


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
        "gift_card_debit",
        "payable_amount",
        "created_at",
    )
    list_filter = ("status", "delivery_method", "created_at")
    list_editable = ("status", "tracking_number")
    search_fields = ("email", "first_name", "last_name", "phone", "user__username")
    readonly_fields = ("created_at",)
    inlines = (OrderItemInline,)


class GiftCardTransactionInline(admin.TabularInline):
    model = GiftCardTransaction
    extra = 0
    readonly_fields = ("type", "amount", "order", "created_at")
    can_delete = False


@admin.register(GiftCard)
class GiftCardAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "nominal",
        "balance",
        "is_activated",
        "user",
        "expires_at",
        "created_at",
    )
    list_filter = ("is_activated", "created_at")
    search_fields = ("code", "user__username", "user__email", "buyer_email")
    readonly_fields = ("activated_at", "created_at", "updated_at")
    inlines = (GiftCardTransactionInline,)
    autocomplete_fields = ("user",)

    def get_readonly_fields(self, request, obj=None):
        ro = list(self.readonly_fields)
        if obj:
            ro.insert(0, "code")
        return tuple(ro)

    def save_model(self, request, obj, form, change):
        if not (obj.code or "").strip():
            obj.code = GiftCard.generate_code()
        super().save_model(request, obj, form, change)


@admin.register(GiftCardTransaction)
class GiftCardTransactionAdmin(admin.ModelAdmin):
    list_display = ("gift_card", "type", "amount", "order", "created_at")
    list_filter = ("type", "created_at")
    search_fields = ("gift_card__code", "order__id")
    autocomplete_fields = ("gift_card", "order")
