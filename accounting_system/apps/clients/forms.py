from django import forms

from .models import Client

INPUT = "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ["name", "legal_name", "inn", "type", "email", "phone", "address", "notes"]
        widgets = {
            "name": forms.TextInput(attrs={"class": INPUT}),
            "legal_name": forms.TextInput(attrs={"class": INPUT}),
            "inn": forms.TextInput(attrs={"class": INPUT}),
            "type": forms.Select(attrs={"class": INPUT}),
            "email": forms.EmailInput(attrs={"class": INPUT}),
            "phone": forms.TextInput(attrs={"class": INPUT}),
            "address": forms.Textarea(attrs={"class": INPUT, "rows": 2}),
            "notes": forms.Textarea(attrs={"class": INPUT, "rows": 3}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization

    def clean_inn(self):
        inn = (self.cleaned_data.get("inn") or "").strip()
        if inn and not inn.isdigit():
            raise forms.ValidationError("ИНН должен содержать только цифры.")
        if inn and len(inn) not in (10, 12):
            raise forms.ValidationError("ИНН должен содержать 10 или 12 цифр.")
        return inn
