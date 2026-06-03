from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import DeleteView, DetailView, ListView, View

from apps.accounts.models import Membership
from apps.core.mixins import (
    HtmxTemplateMixin,
    OrganizationQuerysetMixin,
    OrganizationRequiredMixin,
    RoleRequiredMixin,
)

from .forms import InvoiceForm, InvoiceItemFormSet
from .models import Invoice
from .services import next_invoice_number, recalc_invoice, set_invoice_status

EDITOR_ROLES = {Membership.Role.OWNER, Membership.Role.ACCOUNTANT}


class InvoiceListView(HtmxTemplateMixin, OrganizationQuerysetMixin, ListView):
    model = Invoice
    template_name = "invoices/list.html"
    htmx_template_name = "invoices/partials/invoice_rows.html"
    context_object_name = "invoices"
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset().select_related("client")
        status = self.request.GET.get("status")
        if status in dict(Invoice.Status.choices):
            qs = qs.filter(status=status)
        search = self.request.GET.get("q", "").strip()
        if search:
            qs = qs.filter(Q(number__icontains=search) | Q(client__name__icontains=search))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["statuses"] = Invoice.Status.choices
        ctx["current_status"] = self.request.GET.get("status", "")
        ctx["search"] = self.request.GET.get("q", "")
        ctx["today"] = timezone.localdate()
        return ctx


class InvoiceDetailView(OrganizationQuerysetMixin, DetailView):
    model = Invoice
    template_name = "invoices/detail.html"
    context_object_name = "invoice"

    def get_queryset(self):
        return super().get_queryset().select_related("client", "organization").prefetch_related("items")


class InvoicePrintView(OrganizationQuerysetMixin, DetailView):
    model = Invoice
    template_name = "invoices/print.html"
    context_object_name = "invoice"

    def get_queryset(self):
        return super().get_queryset().select_related("client", "organization").prefetch_related("items")


class _InvoiceFormMixin(RoleRequiredMixin, OrganizationRequiredMixin):
    allowed_roles = EDITOR_ROLES

    def get_object_or_none(self):
        return None

    def render_form(self, form, formset):
        return render(self.request, "invoices/form.html", {
            "form": form, "formset": formset, "invoice": self.get_object_or_none(),
        })


class InvoiceCreateView(_InvoiceFormMixin, View):
    def get(self, request):
        form = InvoiceForm(organization=request.organization)
        formset = InvoiceItemFormSet(prefix="items")
        return self.render_form(form, formset)

    def post(self, request):
        form = InvoiceForm(request.POST, organization=request.organization)
        formset = InvoiceItemFormSet(request.POST, prefix="items")
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                invoice = form.save(commit=False)
                invoice.organization = request.organization
                invoice.created_by = request.user
                invoice.number = next_invoice_number(request.organization)
                invoice.save()
                formset.instance = invoice
                formset.save()
                recalc_invoice(invoice)
            messages.success(request, f"Счёт {invoice.number} создан.")
            return redirect(invoice.get_absolute_url())
        return self.render_form(form, formset)


class InvoiceUpdateView(_InvoiceFormMixin, View):
    def get_object_or_none(self):
        return get_object_or_404(
            Invoice, pk=self.kwargs["pk"], organization=self.request.organization
        )

    def get(self, request, pk):
        invoice = self.get_object_or_none()
        form = InvoiceForm(instance=invoice, organization=request.organization)
        formset = InvoiceItemFormSet(instance=invoice, prefix="items")
        return self.render_form(form, formset)

    def post(self, request, pk):
        invoice = self.get_object_or_none()
        form = InvoiceForm(request.POST, instance=invoice, organization=request.organization)
        formset = InvoiceItemFormSet(request.POST, instance=invoice, prefix="items")
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                invoice = form.save()
                formset.save()
                recalc_invoice(invoice)
            messages.success(request, f"Счёт {invoice.number} обновлён.")
            return redirect(invoice.get_absolute_url())
        return self.render_form(form, formset)


class InvoiceDeleteView(RoleRequiredMixin, OrganizationQuerysetMixin, DeleteView):
    model = Invoice
    template_name = "invoices/confirm_delete.html"
    success_url = reverse_lazy("invoices:list")
    allowed_roles = {Membership.Role.OWNER}

    def form_valid(self, form):
        messages.success(self.request, "Счёт удалён.")
        return super().form_valid(form)


class InvoiceStatusView(RoleRequiredMixin, OrganizationRequiredMixin, View):
    """HTMX POST endpoint to change invoice status (returns status badge partial)."""

    allowed_roles = EDITOR_ROLES

    def post(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk, organization=request.organization)
        new_status = request.POST.get("status")
        valid = dict(Invoice.Status.choices)
        if new_status not in valid:
            return HttpResponse("Некорректный статус", status=400)
        set_invoice_status(invoice, new_status, user=request.user)
        if request.htmx:
            return render(request, "invoices/partials/status_control.html", {"invoice": invoice})
        messages.success(request, "Статус счёта обновлён.")
        return redirect(invoice.get_absolute_url())


class InvoiceAddRowView(RoleRequiredMixin, OrganizationRequiredMixin, View):
    """Return one empty formset row for HTMX 'add line item'."""

    allowed_roles = EDITOR_ROLES

    def get(self, request):
        try:
            index = int(request.GET.get("index", "0"))
        except (TypeError, ValueError):
            index = 0
        formset = InvoiceItemFormSet(prefix="items")
        form = formset.empty_form
        form.prefix = f"items-{index}"
        return render(request, "invoices/partials/item_row.html", {"form": form})


class InvoicePdfView(OrganizationRequiredMixin, View):
    def get(self, request, pk):
        invoice = get_object_or_404(
            Invoice.objects.select_related("client", "organization").prefetch_related("items"),
            pk=pk, organization=request.organization,
        )
        html = render(request, "invoices/pdf.html", {"invoice": invoice}).content.decode("utf-8")
        try:
            from weasyprint import HTML
        except Exception:
            messages.error(request, "PDF-движок недоступен на сервере (WeasyPrint).")
            return redirect(invoice.get_absolute_url())
        pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
        resp = HttpResponse(pdf, content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="{invoice.number}.pdf"'
        return resp
