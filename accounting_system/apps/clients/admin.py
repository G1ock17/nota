from django.contrib import admin

from .models import Client


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("name", "type", "inn", "email", "phone", "organization")
    list_filter = ("type", "organization")
    search_fields = ("name", "legal_name", "inn", "email", "phone")
    autocomplete_fields = ("organization",)
