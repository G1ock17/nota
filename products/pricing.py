"""Розничная цена: наценка от оптовой и округление до 100 ₽."""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# [нижняя граница включительно, верхняя исключительно, наценка]
MARKUP_TIERS: list[tuple[Decimal, Decimal | None, Decimal]] = [
    (Decimal("0"), Decimal("1000"), Decimal("500")),
    (Decimal("1000"), Decimal("3000"), Decimal("1000")),
    (Decimal("3000"), Decimal("5000"), Decimal("1500")),
    (Decimal("5000"), Decimal("10000"), Decimal("2500")),
    (Decimal("10000"), Decimal("20000"), Decimal("4000")),
    (Decimal("20000"), Decimal("30000"), Decimal("5000")),
    (Decimal("30000"), Decimal("50000"), Decimal("6000")),
    (Decimal("50000"), Decimal("80000"), Decimal("7000")),
    (Decimal("80000"), Decimal("120000"), Decimal("9000")),
    (Decimal("120000"), Decimal("200000"), Decimal("11000")),
    (Decimal("200000"), None, Decimal("13000")),
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


def parse_wholesale_price(value) -> Decimal | None:
    """Число из ячейки прайса без наценки."""
    if value is None:
        return None
    text = str(value).replace(" ", "").replace(",", ".")
    try:
        price = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    return price if price > 0 else None


def retail_price(wholesale) -> Decimal:
    """Опт + наценка, округление до ближайших 100 ₽."""
    base = _to_decimal(wholesale)
    return round_to_100(base + markup_amount(base))


def enforce_monotonic_volume_prices(variants) -> list:
    """
    Цена не убывает с ростом объёма.
    Если больший объём подозрительно дешёв (< 50% от меньшего) — поднимаем его цену,
    иначе снижаем цену меньшего объёма.
    """
    items = []
    for variant in variants:
        ml = variant.numeric_volume_ml()
        if ml is not None:
            items.append((variant, ml))
    items.sort(key=lambda pair: pair[1])

    changed = []
    for i in range(1, len(items)):
        smaller, larger = items[i - 1][0], items[i][0]
        if smaller.price <= larger.price:
            continue
        if larger.price < smaller.price * Decimal("0.5"):
            larger.price = smaller.price
            if larger not in changed:
                changed.append(larger)
        else:
            smaller.price = larger.price
            if smaller not in changed:
                changed.append(smaller)
    return changed


def sync_product_volume_prices(product) -> int:
    """Подправить цены одного товара; вернуть число обновлённых вариантов."""
    variants = list(product.variants.all())
    if len(variants) < 2:
        return 0
    before = {variant.id: variant.price for variant in variants}
    changed = enforce_monotonic_volume_prices(variants)
    to_save = [variant for variant in changed if variant.price != before[variant.id]]
    if to_save:
        Variant.objects.bulk_update(to_save, ["price"])
    return len(to_save)
