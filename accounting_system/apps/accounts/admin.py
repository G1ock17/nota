from django.contrib import admin

from .models import Membership


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "role")
    list_filter = ("role", "organization")
    search_fields = ("user__username", "user__email", "organization__name")
    autocomplete_fields = ("organization",)
