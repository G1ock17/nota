import secrets

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    phone = models.CharField(max_length=32, blank=True)
    birth_date = models.DateField(null=True, blank=True)

    email_verified = models.BooleanField(default=False)
    email_token = models.CharField(max_length=64, blank=True, db_index=True)
    email_token_created = models.DateTimeField(null=True, blank=True)
    profile_completed = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f"Profile: {self.user.username}"

    def generate_email_token(self) -> str:
        self.email_token = secrets.token_urlsafe(48)
        self.email_token_created = timezone.now()
        self.save(update_fields=["email_token", "email_token_created"])
        return self.email_token

    def is_email_token_valid(self) -> bool:
        if not self.email_token or not self.email_token_created:
            return False
        return timezone.now() - self.email_token_created < timezone.timedelta(hours=24)


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


class LoginAttempt(models.Model):
    """Tracks failed login attempts for rate limiting."""
    ip_address = models.GenericIPAddressField(db_index=True)
    username = models.CharField(max_length=150, blank=True)
    attempted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["ip_address", "attempted_at"])]

    @classmethod
    def recent_failures(cls, ip: str, minutes: int = 15) -> int:
        cutoff = timezone.now() - timezone.timedelta(minutes=minutes)
        return cls.objects.filter(ip_address=ip, attempted_at__gte=cutoff).count()

    @classmethod
    def cleanup_old(cls, hours: int = 24):
        cutoff = timezone.now() - timezone.timedelta(hours=hours)
        cls.objects.filter(attempted_at__lt=cutoff).delete()
