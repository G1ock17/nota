"""Reusable CBV mixins for auth, organization scoping and HTMX."""
import inspect

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import render


class OrganizationRequiredMixin(LoginRequiredMixin):
    """Require login + an active organization."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.organization is None:
            return render(request, "accounts/no_organization.html", status=403)
        return super().dispatch(request, *args, **kwargs)


class OrganizationQuerysetMixin(OrganizationRequiredMixin):
    """Scope querysets and saved objects to ``request.organization``."""

    def get_queryset(self):
        return super().get_queryset().filter(organization=self.request.organization)

    def form_valid(self, form):
        instance = getattr(form, "instance", None)
        if instance is not None and not instance.pk:
            instance.organization = self.request.organization
        return super().form_valid(form)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # Only inject `organization` when the form actually accepts it
        # (ModelForms scoping FK choices). DeleteView's plain form does not.
        form_class = None
        if hasattr(self, "get_form_class"):
            try:
                form_class = self.get_form_class()
            except Exception:  # pragma: no cover - defensive
                form_class = None
        if form_class is not None:
            params = inspect.signature(form_class.__init__).parameters
            if "organization" in params or any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
            ):
                kwargs["organization"] = self.request.organization
        return kwargs


class RoleRequiredMixin:
    """Restrict a view to users whose membership role is allowed.

    Roles: OWNER (full), ACCOUNTANT (read + create/edit), VIEWER (read only).
    Set ``allowed_roles`` on the view; defaults to all roles (read).
    """

    allowed_roles: set | None = None

    def dispatch(self, request, *args, **kwargs):
        if self.allowed_roles is not None:
            membership = getattr(request, "membership", None)
            role = getattr(membership, "role", None)
            if role not in self.allowed_roles:
                raise PermissionDenied("Недостаточно прав для этого действия.")
        return super().dispatch(request, *args, **kwargs)


class HtmxTemplateMixin:
    """Return a partial template for HTMX requests, full page otherwise."""

    htmx_template_name: str | None = None

    def get_template_names(self):
        if getattr(self.request, "htmx", False) and self.htmx_template_name:
            return [self.htmx_template_name]
        return super().get_template_names()
