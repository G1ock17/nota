"""Shared helpers: period ranges, money math, role flags."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

TWO_PLACES = Decimal("0.01")

PERIOD_CHOICES = [
    ("week", "Эта неделя"),
    ("month", "Этот месяц"),
    ("quarter", "Этот квартал"),
    ("year", "Этот год"),
]


@dataclass(frozen=True)
class DateRange:
    start: date
    end: date

    def __iter__(self):
        return iter((self.start, self.end))


def period_bounds(period: str, today: date | None = None) -> DateRange:
    """Inclusive [start, end] date range for a named period."""
    today = today or timezone.localdate()
    if period == "week":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
    elif period == "quarter":
        q = (today.month - 1) // 3
        start = date(today.year, q * 3 + 1, 1)
        end_month = q * 3 + 3
        end = _month_end(date(today.year, end_month, 1))
    elif period == "year":
        start = date(today.year, 1, 1)
        end = date(today.year, 12, 31)
    else:  # month (default)
        start = today.replace(day=1)
        end = _month_end(start)
    return DateRange(start, end)


def _month_end(d: date) -> date:
    if d.month == 12:
        return date(d.year, 12, 31)
    return date(d.year, d.month + 1, 1) - timedelta(days=1)


def month_starts(n: int, today: date | None = None) -> list[date]:
    """First day of each of the last ``n`` months (oldest first)."""
    today = today or timezone.localdate()
    cursor = today.replace(day=1)
    out: list[date] = []
    for _ in range(n):
        out.append(cursor)
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    return list(reversed(out))


def week_buckets(rng: DateRange) -> list[DateRange]:
    """Split a range into ISO-week buckets clipped to the range."""
    buckets: list[DateRange] = []
    cursor = rng.start
    while cursor <= rng.end:
        week_end = min(cursor + timedelta(days=6 - cursor.weekday()), rng.end)
        buckets.append(DateRange(cursor, week_end))
        cursor = week_end + timedelta(days=1)
    return buckets


def money(value) -> Decimal:
    if value in (None, ""):
        return Decimal("0.00")
    return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def role_flags(membership) -> dict:
    """Boolean capabilities derived from a membership role."""
    role = getattr(membership, "role", None)
    is_owner = role == "OWNER"
    is_accountant = role == "ACCOUNTANT"
    return {
        "role": role,
        "can_view": role in {"OWNER", "ACCOUNTANT", "VIEWER"},
        "can_create": is_owner or is_accountant,
        "can_edit": is_owner or is_accountant,
        "can_delete": is_owner,
    }
