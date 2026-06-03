from django import forms
from django.forms import inlineformset_factory

from .models import Invoice, InvoiceItem

INPUT = "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ["client", "status", "issue_date", "due_date", "tax_rate", "currency", "notes"]
        widgets = {
            "client": forms.Select(attrs={"class": INPUT}),
            "status": forms.Select(attrs={"class": INPUT}),
            "issue_date": forms.DateInput(attrs={"type": "date", "class": INPUT}),
            "due_date": forms.DateInput(attrs={"type": "date", "class": INPUT}),
            "tax_rate": forms.NumberInput(attrs={"class": INPUT, "step": "0.01", "id": "id_tax_rate"}),
            "currency": forms.Select(attrs={"class": INPUT}, choices=[
                ("RUB", "RUB ₽"), ("USD", "USD $"), ("EUR", "EUR €")]),
            "notes": forms.Textarea(attrs={"class": INPUT, "rows": 3}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        if organization is not None:
            from apps.clients.models import Client
            self.fields["client"].queryset = Client.objects.filter(organization=organization)


class InvoiceItemForm(forms.ModelForm):
    class Meta:
        model = InvoiceItem
        fields = ["name", "qty", "unit_price"]
        widgets = {
            "name": forms.TextInput(attrs={
                "class": INPUT, "placeholder": "Наименование позиции"}),
            "qty": forms.NumberInput(attrs={
                "class": INPUT + " js-qty", "step": "0.01", "min": "0"}),
            "unit_price": forms.NumberInput(attrs={
                "class": INPUT + " js-unit-price", "step": "0.01", "min": "0"}),
        }


InvoiceItemFormSet = inlineformset_factory(
    Invoice,
    InvoiceItem,
    form=InvoiceItemForm,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True,
)
