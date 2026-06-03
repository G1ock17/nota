from django.contrib import messages
from django.db.models import Count, Q
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.accounts.models import Membership
from apps.core.mixins import (
    HtmxTemplateMixin,
    OrganizationQuerysetMixin,
    RoleRequiredMixin,
)

from .forms import CategoryForm
from .models import Category

EDITOR_ROLES = {Membership.Role.OWNER, Membership.Role.ACCOUNTANT}


class CategoryListView(HtmxTemplateMixin, OrganizationQuerysetMixin, ListView):
    model = Category
    template_name = "categories/list.html"
    htmx_template_name = "categories/partials/category_table.html"
    context_object_name = "categories"

    def get_queryset(self):
        qs = super().get_queryset().annotate(tx_count=Count("transactions"))
        type_filter = self.request.GET.get("type")
        if type_filter in {"INCOME", "EXPENSE"}:
            qs = qs.filter(type=type_filter)
        search = self.request.GET.get("q", "").strip()
        if search:
            qs = qs.filter(Q(name__icontains=search))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["current_type"] = self.request.GET.get("type", "")
        ctx["search"] = self.request.GET.get("q", "")
        return ctx


class CategoryCreateView(RoleRequiredMixin, OrganizationQuerysetMixin, CreateView):
    model = Category
    form_class = CategoryForm
    template_name = "categories/form.html"
    success_url = reverse_lazy("categories:list")
    allowed_roles = EDITOR_ROLES

    def form_valid(self, form):
        messages.success(self.request, "Категория создана.")
        return super().form_valid(form)


class CategoryUpdateView(RoleRequiredMixin, OrganizationQuerysetMixin, UpdateView):
    model = Category
    form_class = CategoryForm
    template_name = "categories/form.html"
    success_url = reverse_lazy("categories:list")
    allowed_roles = EDITOR_ROLES

    def form_valid(self, form):
        messages.success(self.request, "Категория обновлена.")
        return super().form_valid(form)


class CategoryDeleteView(RoleRequiredMixin, OrganizationQuerysetMixin, DeleteView):
    model = Category
    template_name = "categories/confirm_delete.html"
    success_url = reverse_lazy("categories:list")
    allowed_roles = {Membership.Role.OWNER}

    def form_valid(self, form):
        messages.success(self.request, "Категория удалена.")
        return super().form_valid(form)
