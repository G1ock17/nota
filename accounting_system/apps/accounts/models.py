from django.conf import settings
from django.db import models

from apps.core.models import Organization


class Membership(models.Model):
    """Links a user to an organization with a role."""

    class Role(models.TextChoices):
        OWNER = "OWNER", "Владелец"
        ACCOUNTANT = "ACCOUNTANT", "Бухгалтер"
        VIEWER = "VIEWER", "Наблюдатель"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.ACCOUNTANT)

    class Meta:
        ordering = ["organization__name"]
        unique_together = (("user", "organization"),)

    def __str__(self) -> str:
        return f"{self.user} @ {self.organization} ({self.get_role_display()})"

    @property
    def is_owner(self) -> bool:
        return self.role == self.Role.OWNER

    @property
    def can_edit(self) -> bool:
        return self.role in {self.Role.OWNER, self.Role.ACCOUNTANT}
