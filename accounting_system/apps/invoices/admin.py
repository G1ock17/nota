from django.contrib import admin

from .models import Invoice, InvoiceItem


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0
    readonly_fields = ("amount",)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("number", "client", "status", "issue_date", "due_date", "total", "organization")
    list_filter = ("status", "organization", "currency")
    search_fields = ("number", "client__name")
    date_hierarchy = "issue_date"
    inlines = (InvoiceItemInline,)
    readonly_fields = ("subtotal", "tax_amount", "total")
    autocomplete_fields = ("organization", "client")

    def get_readonly_fields(self, request, obj=None):
        ro = list(self.readonly_fields)
        if obj:  # editing existing -> number is immutable
            ro.append("number")
        return tuple(ro)

    def save_model(self, request, obj, form, change):
        from .services import next_invoice_number
        if not obj.number:
            obj.number = next_invoice_number(obj.organization)
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        from .services import recalc_invoice
        recalc_invoice(form.instance)
