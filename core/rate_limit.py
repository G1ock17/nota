"""IP-based rate limiting helpers (reuse LoginAttempt storage)."""

from django.utils import timezone

from .models import LoginAttempt

# username prefixes distinguish actions in LoginAttempt rows
ACTION_LOGIN = ""
ACTION_PASSWORD_RESET = "__password_reset__"
ACTION_RESEND_VERIFY = "__resend_verify__"
ACTION_REGISTER = "__register__"
ACTION_GIFT_PURCHASE = "__gift_purchase__"


def recent_attempts(ip: str, action: str, minutes: int) -> int:
    cutoff = timezone.now() - timezone.timedelta(minutes=minutes)
    username = action or ACTION_LOGIN
    return LoginAttempt.objects.filter(
        ip_address=ip,
        username=username,
        attempted_at__gte=cutoff,
    ).count()


def record_attempt(ip: str, action: str) -> None:
    username = action or ACTION_LOGIN
    LoginAttempt.objects.create(ip_address=ip, username=username)
