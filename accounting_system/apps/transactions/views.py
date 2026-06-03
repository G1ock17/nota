import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db.models import Q, Sum
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView, View

from apps.accounts.models import Membership
from apps.categories.models import Category
from apps.clients.models import Client
from apps.core.mixins import (
    HtmxTemplateMixin,
    OrganizationQuerysetMixin,
    OrganizationRequiredMixin,
    RoleRequiredMixin,
)

from .forms import CsvImportForm, TransactionForm
from .models import Transaction

EDITOR_ROLES = {Membership.Role.OWNER, Membership.Role.ACCOUNTANT}


def _apply_filters(qs, params):
    ttype = params.get("type")
    if ttype in dict(Transaction.Type.choices):
        qs = qs.filter(type=ttype)
    category = params.get("category")
    if category:
        qs = qs.filter(category_id=category)
    client = params.get("client")
    if client:
        qs = qs.filter(client_id=client)
    date_from = params.get("date_from")
    if date_from:
        qs = qs.filter(date__gte=date_from)
    date_to = params.get("date_to")
    if date_to:
        qs = qs.filter(date__lte=date_to)
    amount_min = params.get("amount_min")
    if amount_min:
        try:
            qs = qs.filter(amount__gte=Decimal(amount_min))
        except InvalidOperation:
            pass
    amount_max = params.get("amount_max")
    if amount_max:
        try:
            qs = qs.filter(amount__lte=Decimal(amount_max))
        except InvalidOperation:
            pass
    search = params.get("q", "").strip()
    if search:
        qs = qs.filter(Q(description__icontains=search) | Q(notes__icontains=search))
    return qs


class TransactionListView(HtmxTemplateMixin, OrganizationQuerysetMixin, ListView):
    model = Transaction
    template_name = "transactions/list.html"
    htmx_template_name = "transactions/partials/transaction_rows.html"
    context_object_name = "transactions"
    paginate_by = 30

    def get_queryset(self):
        qs = super().get_queryset().select_related("category", "client")
        return _apply_filters(qs, self.request.GET)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self.request.organization
        base = _apply_filters(
            Transaction.objects.filter(organization=org).select_related("category", "client"),
            self.request.GET,
        )
        totals = base.aggregate(
            income=Sum("amount", filter=Q(type="INCOME")),
            expense=Sum("amount", filter=Q(type="EXPENSE")),
        )
        income = totals["income"] or Decimal("0")
        expense = totals["expense"] or Decimal("0")

        # Running balance computed over the *current page*, newest first.
        page_txs = list(ctx["transactions"])
        running = Decimal("0")
        for tx in reversed(page_txs):
            running += tx.signed_amount
            tx.running_balance = running

        ctx.update({
            "total_income": income,
            "total_expense": expense,
            "net": income - expense,
            "categories": Category.objects.filter(organization=org),
            "clients": Client.objects.filter(organization=org),
            "types": Transaction.Type.choices,
            "filters": self.request.GET,
        })
        return ctx


class TransactionCreateView(RoleRequiredMixin, OrganizationQuerysetMixin, CreateView):
    model = Transaction
    form_class = TransactionForm
    template_name = "transactions/form.html"
    success_url = reverse_lazy("transactions:list")
    allowed_roles = EDITOR_ROLES

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, "Транзакция добавлена.")
        return super().form_valid(form)


class TransactionUpdateView(RoleRequiredMixin, OrganizationQuerysetMixin, UpdateView):
    model = Transaction
    form_class = TransactionForm
    template_name = "transactions/form.html"
    success_url = reverse_lazy("transactions:list")
    allowed_roles = EDITOR_ROLES

    def form_valid(self, form):
        messages.success(self.request, "Транзакция обновлена.")
        return super().form_valid(form)


class TransactionDeleteView(RoleRequiredMixin, OrganizationQuerysetMixin, DeleteView):
    model = Transaction
    template_name = "transactions/confirm_delete.html"
    success_url = reverse_lazy("transactions:list")
    allowed_roles = {Membership.Role.OWNER}

    def form_valid(self, form):
        messages.success(self.request, "Транзакция удалена.")
        return super().form_valid(form)


class TransactionImportView(RoleRequiredMixin, OrganizationRequiredMixin, View):
    allowed_roles = EDITOR_ROLES
    template_name = "transactions/import.html"

    def get(self, request):
        return render(request, self.template_name, {"form": CsvImportForm()})

    def post(self, request):
        form = CsvImportForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        raw = form.cleaned_data["file"].read()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp1251", errors="replace")

        reader = csv.DictReader(io.StringIO(text))
        org = request.organization
        created, errors = 0, []
        cat_cache = {}

        for line_no, row in enumerate(reader, start=2):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            try:
                ttype = (row.get("type") or "EXPENSE").upper()
                if ttype not in dict(Transaction.Type.choices):
                    raise ValueError(f"неизвестный тип '{ttype}'")
                amount = Decimal(row.get("amount", "").replace(",", ".").replace(" ", ""))
                if amount <= 0:
                    raise ValueError("сумма должна быть > 0")
                date_str = row.get("date", "")
                tx_date = _parse_date(date_str)
                if tx_date is None:
                    raise ValueError(f"некорректная дата '{date_str}'")

                cat_name = row.get("category") or "Без категории"
                cat_key = (cat_name, ttype if ttype != "TRANSFER" else "EXPENSE")
                category = cat_cache.get(cat_key)
                if category is None:
                    category, _ = Category.objects.get_or_create(
                        organization=org, name=cat_name, type=cat_key[1],
                        defaults={"color": "#6366f1", "icon": "tag"},
                    )
                    cat_cache[cat_key] = category

                client = None
                client_name = row.get("client")
                if client_name:
                    client = Client.objects.filter(
                        organization=org, name__iexact=client_name).first()

                Transaction.objects.create(
                    organization=org, type=ttype, amount=amount,
                    currency=(row.get("currency") or "RUB").upper()[:3],
                    category=category, client=client, date=tx_date,
                    description=row.get("description", "")[:255], created_by=request.user,
                )
                created += 1
            except (InvalidOperation, ValueError, KeyError) as exc:
                errors.append(f"Строка {line_no}: {exc}")

        if created:
            messages.success(request, f"Импортировано транзакций: {created}.")
        if errors:
            messages.warning(request, "Пропущено строк: %d. %s" % (
                len(errors), "; ".join(errors[:5])))
        if not created and not errors:
            messages.info(request, "В файле не найдено данных.")
        return redirect("transactions:list")


def _parse_date(value):
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None
