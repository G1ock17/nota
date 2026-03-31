from django.contrib import admin
from .models import DeliveryAddress, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone", "birth_date")
    search_fields = ("user__username", "user__email", "phone")


@admin.register(DeliveryAddress)
class DeliveryAddressAdmin(admin.ModelAdmin):
    list_display = ("user", "city", "address_line1", "is_default", "created_at")
    list_filter = ("is_default", "country", "created_at")
    search_fields = ("user__username", "city", "address_line1", "postal_code")
