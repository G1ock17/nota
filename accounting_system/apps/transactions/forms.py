from django import forms

from apps.categories.models import Category
from apps.clients.models import Client

from .models import Transaction

INPUT = "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"


class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ["type", "amount", "currency", "category", "client", "date",
                  "description", "notes"]
        widgets = {
            "type": forms.Select(attrs={"class": INPUT}),
            "amount": forms.NumberInput(attrs={"class": INPUT, "step": "0.01", "min": "0"}),
            "currency": forms.Select(attrs={"class": INPUT}, choices=[
                ("RUB", "RUB ₽"), ("USD", "USD $"), ("EUR", "EUR €")]),
            "category": forms.Select(attrs={"class": INPUT}),
            "client": forms.Select(attrs={"class": INPUT}),
            "date": forms.DateInput(attrs={"type": "date", "class": INPUT}),
            "description": forms.TextInput(attrs={"class": INPUT}),
            "notes": forms.Textarea(attrs={"class": INPUT, "rows": 2}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        if organization is not None:
            self.fields["category"].queryset = Category.objects.filter(organization=organization)
            self.fields["client"].queryset = Client.objects.filter(organization=organization)
        self.fields["client"].required = False

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount is not None and amount <= 0:
            raise forms.ValidationError("Сумма должна быть больше нуля.")
        return amount

    def clean(self):
        cleaned = super().clean()
        ttype, category = cleaned.get("type"), cleaned.get("category")
        if ttype and category and ttype != "TRANSFER":
            if category.type != ttype:
                self.add_error("category", "Тип категории не совпадает с типом операции.")
        return cleaned


class CsvImportForm(forms.Form):
    file = forms.FileField(
        label="CSV-файл",
        widget=forms.ClearableFileInput(attrs={"class": INPUT, "accept": ".csv"}),
        help_text="Колонки: date, type, amount, category, currency, client, description",
    )

    def clean_file(self):
        f = self.cleaned_data["file"]
        if not f.name.lower().endswith(".csv"):
            raise forms.ValidationError("Загрузите файл в формате .csv")
        if f.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Файл слишком большой (макс. 5 МБ).")
        return f
