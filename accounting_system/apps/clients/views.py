from decimal import Decimal

from django.contrib import messages
from django.db.models import Q, Sum
from django.urls import reverse_lazy
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from apps.accounts.models import Membership
from apps.core.mixins import (
    HtmxTemplateMixin,
    OrganizationQuerysetMixin,
    RoleRequiredMixin,
)

from .forms import ClientForm
from .models import Client

EDITOR_ROLES = {Membership.Role.OWNER, Membership.Role.ACCOUNTANT}


class ClientListView(HtmxTemplateMixin, OrganizationQuerysetMixin, ListView):
    model = Client
    template_name = "clients/list.html"
    htmx_template_name = "clients/partials/client_rows.html"
    context_object_name = "clients"
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.GET.get("q", "").strip()
        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(legal_name__icontains=search)
                | Q(inn__icontains=search)
                | Q(email__icontains=search)
            )
        ctype = self.request.GET.get("type")
        if ctype in {"INDIVIDUAL", "COMPANY"}:
            qs = qs.filter(type=ctype)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["search"] = self.request.GET.get("q", "")
        ctx["current_type"] = self.request.GET.get("type", "")
        return ctx


class ClientDetailView(OrganizationQuerysetMixin, DetailView):
    model = Client
    template_name = "clients/detail.html"
    context_object_name = "client"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        client = self.object
        invoices = client.invoices.all().order_by("-issue_date")
        transactions = client.transactions.select_related("category").order_by("-date")[:50]

        paid = invoices.filter(status="PAID").aggregate(s=Sum("total"))["s"] or Decimal("0")
        owed = invoices.filter(status__in=["SENT", "OVERDUE"]).aggregate(
            s=Sum("total"))["s"] or Decimal("0")

        ctx["invoices"] = invoices
        ctx["transactions"] = transactions
        ctx["total_paid"] = paid
        ctx["total_owed"] = owed
        return ctx


class ClientCreateView(RoleRequiredMixin, OrganizationQuerysetMixin, CreateView):
    model = Client
    form_class = ClientForm
    template_name = "clients/form.html"
    success_url = reverse_lazy("clients:list")
    allowed_roles = EDITOR_ROLES

    def form_valid(self, form):
        messages.success(self.request, "Клиент создан.")
        return super().form_valid(form)


class ClientUpdateView(RoleRequiredMixin, OrganizationQuerysetMixin, UpdateView):
    model = Client
    form_class = ClientForm
    template_name = "clients/form.html"
    allowed_roles = EDITOR_ROLES

    def get_success_url(self):
        return self.object.get_absolute_url()

    def form_valid(self, form):
        messages.success(self.request, "Данные клиента обновлены.")
        return super().form_valid(form)


class ClientDeleteView(RoleRequiredMixin, OrganizationQuerysetMixin, DeleteView):
    model = Client
    template_name = "clients/confirm_delete.html"
    success_url = reverse_lazy("clients:list")
    allowed_roles = {Membership.Role.OWNER}

    def form_valid(self, form):
        messages.success(self.request, "Клиент удалён.")
        return super().form_valid(form)
