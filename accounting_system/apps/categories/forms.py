from django import forms

from .models import Category

INPUT = "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "type", "color", "icon", "parent"]
        widgets = {
            "name": forms.TextInput(attrs={"class": INPUT}),
            "type": forms.Select(attrs={"class": INPUT}),
            "color": forms.TextInput(attrs={"type": "color", "class": "h-10 w-16 rounded border border-slate-300"}),
            "icon": forms.TextInput(attrs={"class": INPUT}),
            "parent": forms.Select(attrs={"class": INPUT}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        qs = Category.objects.none()
        if organization is not None:
            qs = Category.objects.filter(organization=organization)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
        self.fields["parent"].queryset = qs
        self.fields["parent"].required = False

    def clean(self):
        cleaned = super().clean()
        org = self.organization
        name, ctype = cleaned.get("name"), cleaned.get("type")
        if org and name and ctype:
            dup = Category.objects.filter(organization=org, name=name, type=ctype)
            if self.instance.pk:
                dup = dup.exclude(pk=self.instance.pk)
            if dup.exists():
                raise forms.ValidationError("Категория с таким именем и типом уже существует.")
        return cleaned
