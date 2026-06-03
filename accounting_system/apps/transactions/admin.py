from django.contrib import admin

from .models import Transaction


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("date", "type", "amount", "currency", "category", "client", "organization")
    list_filter = ("type", "currency", "organization", "category")
    search_fields = ("description", "notes", "client__name")
    date_hierarchy = "date"
    autocomplete_fields = ("organization", "category", "client", "invoice")
    readonly_fields = ("created_at", "updated_at")
