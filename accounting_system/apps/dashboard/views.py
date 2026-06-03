from django.views.generic import TemplateView

from apps.core.mixins import OrganizationRequiredMixin
from apps.core.utils import PERIOD_CHOICES, period_bounds
from apps.reports import services


class DashboardView(OrganizationRequiredMixin, TemplateView):
    template_name = "dashboard/index.html"

    def get_template_names(self):
        # HTMX period switch swaps just the inner content.
        if getattr(self.request, "htmx", False):
            return ["dashboard/partials/content.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self.request.organization
        period = self.request.GET.get("period", "month")
        if period not in dict(PERIOD_CHOICES):
            period = "month"
        rng = period_bounds(period)

        ctx["period"] = period
        ctx["period_choices"] = PERIOD_CHOICES
        ctx["range"] = rng
        ctx["kpis"] = services.kpis(org, rng)
        ctx["recent_transactions"] = services.recent_transactions(org, 10)
        ctx["chart_data"] = services.dashboard_payload(org, rng)
        return ctx
