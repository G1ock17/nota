from django.contrib import admin
from .models import DeliveryAddress, LoginAttempt, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone", "birth_date", "email_verified", "profile_completed")
    list_filter = ("email_verified", "profile_completed")
    search_fields = ("user__username", "user__email", "phone")
    readonly_fields = ("email_token", "email_token_created")


@admin.register(DeliveryAddress)
class DeliveryAddressAdmin(admin.ModelAdmin):
    list_display = ("user", "city", "address_line1", "is_default", "created_at")
    list_filter = ("is_default", "country", "created_at")
    search_fields = ("user__username", "city", "address_line1", "postal_code")


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ("ip_address", "username", "attempted_at")
    list_filter = ("attempted_at",)
    search_fields = ("ip_address", "username")
