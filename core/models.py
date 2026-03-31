from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    phone = models.CharField(max_length=32, blank=True)
    birth_date = models.DateField(null=True, blank=True)

    def __str__(self) -> str:
        return f"Profile: {self.user.username}"


class DeliveryAddress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="delivery_addresses")
    country = models.CharField(max_length=120)
    city = models.CharField(max_length=120)
    region = models.CharField(max_length=120)
    postal_code = models.CharField(max_length=32)
    address_line1 = models.CharField(max_length=255)
    address_line2 = models.CharField(max_length=255, blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_default", "-created_at"]

    def __str__(self) -> str:
        return f"{self.user.username}: {self.city}, {self.address_line1}"
