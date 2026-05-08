import re

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

User = get_user_model()


class RegistrationForm(forms.Form):
    email = forms.EmailField(
        max_length=254,
        widget=forms.EmailInput(attrs={
            "placeholder": "email@example.com",
            "autocomplete": "email",
        }),
    )
    password1 = forms.CharField(
        min_length=8,
        widget=forms.PasswordInput(attrs={
            "placeholder": "Минимум 8 символов",
            "autocomplete": "new-password",
        }),
    )
    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            "placeholder": "Повторите пароль",
            "autocomplete": "new-password",
        }),
    )
    agree_terms = forms.BooleanField(
        error_messages={"required": "Необходимо принять условия использования."},
    )
    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        if User.objects.filter(email=email).exists():
            raise ValidationError("Аккаунт с таким email уже существует.")
        return email

    def clean_password1(self):
        pw = self.cleaned_data["password1"]
        validate_password(pw)
        return pw

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Пароли не совпадают.")
        return cleaned

    def save(self):
        email = self.cleaned_data["email"]
        username = email
        password = self.cleaned_data["password1"]
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            is_active=False,
        )
        return user


class LoginForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            "placeholder": "email@example.com",
            "autocomplete": "email",
        }),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            "placeholder": "Пароль",
            "autocomplete": "current-password",
        }),
    )


class ProfileSetupForm(forms.Form):
    first_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Имя"}),
    )
    phone = forms.CharField(
        max_length=32,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "+7 (___) ___-__-__"}),
    )
    country = forms.CharField(
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Страна"}),
    )
    city = forms.CharField(
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Город"}),
    )
    address_line1 = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Улица, дом, квартира"}),
    )
    postal_code = forms.CharField(
        max_length=32,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Индекс"}),
    )

    def clean_phone(self):
        phone = self.cleaned_data.get("phone", "").strip()
        if phone:
            digits = re.sub(r"[^\d+]", "", phone)
            if len(digits) < 7:
                raise ValidationError("Введите корректный номер телефона.")
        return phone
