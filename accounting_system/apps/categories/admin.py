from django.contrib import admin

from .models import Category


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "type", "organization", "parent", "color")
    list_filter = ("type", "organization")
    search_fields = ("name",)
    autocomplete_fields = ("organization", "parent")
