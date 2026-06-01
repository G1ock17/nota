"""Розничная цена: наценка от оптовой и округление до 100 ₽."""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# [нижняя граница включительно, верхняя исключительно, наценка]
MARKUP_TIERS: list[tuple[Decimal, Decimal | None, Decimal]] = [
    (Decimal("0"), Decimal("1000"), Decimal("500")),
    (Decimal("1000"), Decimal("3000"), Decimal("1000")),
    (Decimal("3000"), Decimal("5000"), Decimal("1500")),
    (Decimal("5000"), Decimal("10000"), Decimal("2000")),
    (Decimal("10000"), Decimal("20000"), Decimal("3000")),
    (Decimal("20000"), Decimal("30000"), Decimal("4000")),
    (Decimal("30000"), Decimal("50000"), Decimal("5000")),
    (Decimal("50000"), Decimal("80000"), Decimal("6000")),
    (Decimal("80000"), Decimal("120000"), Decimal("8000")),
    (Decimal("120000"), Decimal("200000"), Decimal("10000")),
    (Decimal("200000"), None, Decimal("12000")),
]


def _to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value).replace(" ", "").replace(",", "."))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Некорректная цена: {value!r}") from exc


def markup_amount(wholesale: Decimal) -> Decimal:
    price = _to_decimal(wholesale)
    for low, high, markup in MARKUP_TIERS:
        if high is None:
            if price >= low:
                return markup
        elif low <= price < high:
            return markup
    return MARKUP_TIERS[-1][2]


def round_to_100(amount: Decimal) -> Decimal:
    value = _to_decimal(amount)
    return (
        (value / Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        * Decimal("100")
    )


def retail_price(wholesale) -> Decimal:
    """Опт + наценка, округление до ближайших 100 ₽."""
    base = _to_decimal(wholesale)
    return round_to_100(base + markup_amount(base))
