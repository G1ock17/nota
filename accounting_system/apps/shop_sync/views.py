from django.contrib import messages
from django.shortcuts import redirect, render
from django.views import View

from apps.accounts.models import Membership
from apps.core.mixins import OrganizationRequiredMixin, RoleRequiredMixin

from .forms import ShopOrdersImportForm
from .services import import_shop_orders_from_file


class SyncShopOrdersView(RoleRequiredMixin, OrganizationRequiredMixin, View):
    """POST: pull new paid orders from shop API or MySQL."""

    allowed_roles = {Membership.Role.OWNER, Membership.Role.ACCOUNTANT}

    def post(self, request):
        from apps.shop_sync.services import sync_mode, sync_shop_orders, test_shop_connection

        if not sync_mode():
            messages.error(
                request,
                "Синхронизация не настроена. Задайте SHOP_SYNC_URL + SHOP_SYNC_TOKEN "
                "или импортируйте файл заказов.",
            )
            return redirect("transactions:list")

        ok, msg = test_shop_connection()
        if not ok:
            messages.error(request, msg)
            return redirect("transactions:list")

        result = sync_shop_orders(request.organization, created_by=request.user)
        return _flash_sync_result(request, result)


class ImportShopOrdersFileView(RoleRequiredMixin, OrganizationRequiredMixin, View):
    """Upload CSV/Excel export from phpMyAdmin."""

    allowed_roles = {Membership.Role.OWNER, Membership.Role.ACCOUNTANT}
    template_name = "shop_sync/import_orders.html"

    def get(self, request):
        return render(request, self.template_name, {"form": ShopOrdersImportForm()})

    def post(self, request):
        form = ShopOrdersImportForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        uploaded = form.cleaned_data["file"]
        # Read bytes once — Django upload streams may not rewind like a disk file.
        from apps.shop_sync.file_import import read_file_bytes

        file_bytes = read_file_bytes(uploaded)
        result = import_shop_orders_from_file(
            request.organization,
            file_bytes,
            uploaded.name or "orders.csv",
            created_by=request.user,
        )
        return _flash_sync_result(request, result, redirect_to="shop_sync:import_file")


def _flash_sync_result(request, result, redirect_to="transactions:list"):
    if result.errors:
        for err in result.errors[:5]:
            messages.warning(request, err)
    if result.created:
        messages.success(
            request,
            f"Импортировано продаж: {result.created}. "
            f"Пропущено (уже в учёте или не подходят): {result.skipped}.",
        )
    elif not result.errors:
        messages.info(
            request,
            f"Новых заказов для импорта нет. Пропущено: {result.skipped}.",
        )
    return redirect(redirect_to)
