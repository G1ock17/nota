from django import forms

INPUT = "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"


class ShopOrdersImportForm(forms.Form):
    file = forms.FileField(
        label="Файл заказов",
        widget=forms.FileInput(attrs={
            "class": INPUT,
            "accept": ".csv,.tsv,.txt,.xlsx,text/csv",
        }),
        help_text="Экспорт из phpMyAdmin: CSV или Excel (.xlsx). Лишние колонки (адрес, доставка) игнорируются.",
    )

    def clean_file(self):
        f = self.cleaned_data["file"]
        name = f.name.lower()
        if not any(name.endswith(ext) for ext in (".csv", ".tsv", ".txt", ".xlsx")):
            raise forms.ValidationError("Загрузите .csv, .tsv или .xlsx")
        if f.size > 15 * 1024 * 1024:
            raise forms.ValidationError("Файл слишком большой (макс. 15 МБ).")
        return f
