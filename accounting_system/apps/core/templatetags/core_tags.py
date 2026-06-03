from decimal import Decimal

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

CURRENCY_SYMBOLS = {"RUB": "₽", "USD": "$", "EUR": "€"}

STATUS_BADGES = {
    "DRAFT": "bg-slate-100 text-slate-600",
    "SENT": "bg-blue-100 text-blue-700",
    "PAID": "bg-emerald-100 text-emerald-700",
    "OVERDUE": "bg-red-100 text-red-700",
    "CANCELLED": "bg-gray-100 text-gray-500 line-through",
}

TYPE_BADGES = {
    "INCOME": "bg-emerald-100 text-emerald-700",
    "EXPENSE": "bg-red-100 text-red-700",
    "TRANSFER": "bg-indigo-100 text-indigo-700",
}


@register.filter
def money(value, currency="RUB"):
    """Format a decimal as `1 234 567.89 ₽` (thin-space thousands)."""
    try:
        amount = Decimal(str(value or 0)).quantize(Decimal("0.01"))
    except Exception:
        return value
    sign = "-" if amount < 0 else ""
    whole, frac = f"{abs(amount):.2f}".split(".")
    grouped = "\u202f".join(
        [whole[max(i - 3, 0):i] for i in range(len(whole), 0, -3)][::-1]
    )
    symbol = CURRENCY_SYMBOLS.get(currency, currency)
    return f"{sign}{grouped}.{frac}\u202f{symbol}"


@register.filter
def status_badge(status):
    return STATUS_BADGES.get(status, "bg-slate-100 text-slate-600")


@register.filter
def type_badge(t):
    return TYPE_BADGES.get(t, "bg-slate-100 text-slate-600")


@register.filter
def get_item(d, key):
    try:
        return d.get(key)
    except AttributeError:
        return None


@register.filter
def pct(value, digits=1):
    try:
        return f"{Decimal(str(value)):.{int(digits)}f}%"
    except Exception:
        return value


@register.simple_tag(takes_context=True)
def query_replace(context, **kwargs):
    """Rebuild the current querystring overriding/removing given keys."""
    request = context["request"]
    params = request.GET.copy()
    for key, value in kwargs.items():
        if value is None or value == "":
            params.pop(key, None)
        else:
            params[key] = value
    encoded = params.urlencode()
    return mark_safe(f"?{encoded}" if encoded else "")
