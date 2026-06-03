from django.db import models

from apps.core.models import OrganizationOwned, TimeStampedModel


class Category(TimeStampedModel, OrganizationOwned):
    class Type(models.TextChoices):
        INCOME = "INCOME", "Доход"
        EXPENSE = "EXPENSE", "Расход"

    name = models.CharField(max_length=120)
    type = models.CharField(max_length=10, choices=Type.choices)
    color = models.CharField(max_length=7, default="#6366f1")
    icon = models.CharField(max_length=32, blank=True, default="tag")
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children"
    )

    class Meta:
        ordering = ["type", "name"]
        unique_together = (("organization", "name", "type"),)
        verbose_name_plural = "categories"

    def __str__(self) -> str:
        return self.name

    @property
    def is_income(self) -> bool:
        return self.type == self.Type.INCOME
