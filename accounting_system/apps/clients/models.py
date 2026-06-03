from django.db import models
from django.urls import reverse

from apps.core.models import OrganizationOwned, TimeStampedModel


class Client(TimeStampedModel, OrganizationOwned):
    class Type(models.TextChoices):
        INDIVIDUAL = "INDIVIDUAL", "Физ. лицо"
        COMPANY = "COMPANY", "Компания"

    name = models.CharField(max_length=255)
    legal_name = models.CharField(max_length=255, blank=True)
    inn = models.CharField("ИНН", max_length=12, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    type = models.CharField(max_length=12, choices=Type.choices, default=Type.COMPANY)
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self):
        return reverse("clients:detail", kwargs={"pk": self.pk})
