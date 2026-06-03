from datetime import datetime

from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.core.mixins import OrganizationRequiredMixin
from apps.core.utils import DateRange, period_bounds
from apps.invoices.models import Invoice
from apps.transactions.models import Transaction
from apps.transactions.views import _apply_filters

from . import exports, services

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _resolve_range(request) -> DateRange:
    """Custom date range (?date_from&date_to) wins over named ?period."""
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    if date_from and date_to:
        try:
            start = datetime.strptime(date_from, "%Y-%m-%d").date()
            end = datetime.strptime(date_to, "%Y-%m-%d").date()
            if start <= end:
                return DateRange(start, end)
        except ValueError:
            pass
    return period_bounds(request.GET.get("period", "month"))


class ReportsIndexView(OrganizationRequiredMixin, TemplateView):
    template_name = "reports/index.html"

    def get_template_names(self):
        if getattr(self.request, "htmx", False):
            return ["reports/partials/content.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self.request.organization
        rng = _resolve_range(self.request)
        ctx["range"] = rng
        ctx["date_from"] = rng.start
        ctx["date_to"] = rng.end
        ctx["kpis"] = services.kpis(org, rng)
        ctx["pnl_rows"] = services.pnl_table(org, 12)
        ctx["chart_data"] = services.reports_payload(org, rng)
        return ctx


class DashboardChartDataView(OrganizationRequiredMixin, View):
    """JSON endpoint for Chart.js (dashboard + reports)."""

    def get(self, request):
        org = request.organization
        rng = _resolve_range(request)
        scope = request.GET.get("scope", "dashboard")
        if scope == "reports":
            payload = services.reports_payload(org, rng)
        else:
            payload = services.dashboard_payload(org, rng)
        payload["kpis"] = {k: float(v) for k, v in services.kpis(org, rng).items()}
        return JsonResponse(payload)


class ExportTransactionsXlsx(OrganizationRequiredMixin, View):
    def get(self, request):
        qs = _apply_filters(
            Transaction.objects.filter(organization=request.organization)
            .select_related("category", "client"),
            request.GET,
        )
        data = exports.transactions_xlsx(qs)
        resp = HttpResponse(data, content_type=XLSX)
        resp["Content-Disposition"] = 'attachment; filename="transactions.xlsx"'
        return resp


class ExportPnlXlsx(OrganizationRequiredMixin, View):
    def get(self, request):
        rows = services.pnl_table(request.organization, 12)
        data = exports.pnl_xlsx(rows)
        resp = HttpResponse(data, content_type=XLSX)
        resp["Content-Disposition"] = 'attachment; filename="pnl_report.xlsx"'
        return resp


class ExportInvoicesXlsx(OrganizationRequiredMixin, View):
    def get(self, request):
        qs = Invoice.objects.filter(organization=request.organization).select_related("client")
        status = request.GET.get("status")
        if status in dict(Invoice.Status.choices):
            qs = qs.filter(status=status)
        data = exports.invoices_xlsx(qs)
        resp = HttpResponse(data, content_type=XLSX)
        resp["Content-Disposition"] = 'attachment; filename="invoices.xlsx"'
        return resp
