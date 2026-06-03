"""Aggregation helpers returning Chart.js-ready structures."""
from __future__ import annotations

from decimal import Decimal

from django.db.models import DecimalField, Q, Sum
from django.db.models.functions import Coalesce

from apps.core.utils import DateRange, month_starts, week_buckets, _month_end
from apps.transactions.models import Transaction

MONTH_NAMES = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн",
               "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]

_ZERO = Decimal("0.00")


def _f(value) -> float:
    return float(value or 0)


def _base_qs(org, rng: DateRange | None = None):
    qs = Transaction.objects.filter(organization=org)
    if rng is not None:
        qs = qs.filter(date__gte=rng.start, date__lte=rng.end)
    return qs


def kpis(org, rng: DateRange) -> dict:
    agg = _base_qs(org, rng).aggregate(
        income=Coalesce(Sum("amount", filter=Q(type="INCOME")), _ZERO,
                        output_field=DecimalField()),
        expense=Coalesce(Sum("amount", filter=Q(type="EXPENSE")), _ZERO,
                         output_field=DecimalField()),
    )
    from apps.invoices.models import Invoice
    outstanding = Invoice.objects.filter(
        organization=org, status__in=["SENT", "OVERDUE"]
    ).aggregate(s=Coalesce(Sum("total"), _ZERO, output_field=DecimalField()))["s"]

    revenue, expense = agg["income"], agg["expense"]
    return {
        "revenue": revenue,
        "expenses": expense,
        "profit": revenue - expense,
        "outstanding": outstanding,
    }


def revenue_vs_expense_by_week(org, rng: DateRange) -> dict:
    labels, income_data, expense_data = [], [], []
    for i, bucket in enumerate(week_buckets(rng), start=1):
        agg = _base_qs(org, bucket).aggregate(
            income=Coalesce(Sum("amount", filter=Q(type="INCOME")), _ZERO,
                            output_field=DecimalField()),
            expense=Coalesce(Sum("amount", filter=Q(type="EXPENSE")), _ZERO,
                             output_field=DecimalField()),
        )
        labels.append(f"Нед. {i}")
        income_data.append(_f(agg["income"]))
        expense_data.append(_f(agg["expense"]))
    return {"labels": labels, "income": income_data, "expense": expense_data}


def profit_trend_12m(org) -> dict:
    labels, data = [], []
    for start in month_starts(12):
        rng = DateRange(start, _month_end(start))
        agg = _base_qs(org, rng).aggregate(
            income=Coalesce(Sum("amount", filter=Q(type="INCOME")), _ZERO,
                            output_field=DecimalField()),
            expense=Coalesce(Sum("amount", filter=Q(type="EXPENSE")), _ZERO,
                             output_field=DecimalField()),
        )
        labels.append(f"{MONTH_NAMES[start.month - 1]} {start.year % 100:02d}")
        data.append(_f(agg["income"] - agg["expense"]))
    return {"labels": labels, "profit": data}


def cash_flow_12m(org) -> dict:
    labels, income_data, expense_data = [], [], []
    for start in month_starts(12):
        rng = DateRange(start, _month_end(start))
        agg = _base_qs(org, rng).aggregate(
            income=Coalesce(Sum("amount", filter=Q(type="INCOME")), _ZERO,
                            output_field=DecimalField()),
            expense=Coalesce(Sum("amount", filter=Q(type="EXPENSE")), _ZERO,
                             output_field=DecimalField()),
        )
        labels.append(f"{MONTH_NAMES[start.month - 1]} {start.year % 100:02d}")
        income_data.append(_f(agg["income"]))
        expense_data.append(_f(agg["expense"]))
    return {"labels": labels, "income": income_data, "expense": expense_data}


def category_breakdown(org, rng: DateRange, tx_type: str, limit: int | None = None) -> dict:
    qs = (
        _base_qs(org, rng).filter(type=tx_type)
        .values("category__name", "category__color")
        .annotate(total=Sum("amount"))
        .order_by("-total")
    )
    if limit:
        qs = qs[:limit]
    labels, data, colors = [], [], []
    for row in qs:
        labels.append(row["category__name"] or "—")
        data.append(_f(row["total"]))
        colors.append(row["category__color"] or "#6366f1")
    return {"labels": labels, "data": data, "colors": colors}


def pnl_table(org, n_months: int = 12) -> list[dict]:
    rows = []
    for start in month_starts(n_months):
        rng = DateRange(start, _month_end(start))
        agg = _base_qs(org, rng).aggregate(
            income=Coalesce(Sum("amount", filter=Q(type="INCOME")), _ZERO,
                            output_field=DecimalField()),
            expense=Coalesce(Sum("amount", filter=Q(type="EXPENSE")), _ZERO,
                             output_field=DecimalField()),
        )
        revenue, expense = agg["income"], agg["expense"]
        profit = revenue - expense
        margin = (profit / revenue * 100) if revenue else _ZERO
        rows.append({
            "label": f"{MONTH_NAMES[start.month - 1]} {start.year}",
            "revenue": revenue, "expense": expense, "profit": profit, "margin": margin,
        })
    return rows


def recent_transactions(org, limit: int = 10):
    return (
        Transaction.objects.filter(organization=org)
        .select_related("category", "client")
        .order_by("-date", "-id")[:limit]
    )


def dashboard_payload(org, rng: DateRange) -> dict:
    """Everything the dashboard charts need, JSON-serialisable."""
    return {
        "revenue_expense_week": revenue_vs_expense_by_week(org, rng),
        "profit_trend": profit_trend_12m(org),
        "top_expenses": category_breakdown(org, rng, "EXPENSE", limit=5),
    }


def reports_payload(org, rng: DateRange) -> dict:
    return {
        "revenue_by_category": category_breakdown(org, rng, "INCOME"),
        "expense_breakdown": category_breakdown(org, rng, "EXPENSE"),
        "cash_flow": cash_flow_12m(org),
    }
