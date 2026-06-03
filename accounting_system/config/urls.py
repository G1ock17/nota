from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("dashboard/", include("apps.dashboard.urls")),
    path("clients/", include("apps.clients.urls")),
    path("categories/", include("apps.categories.urls")),
    path("invoices/", include("apps.invoices.urls")),
    path("transactions/", include("apps.transactions.urls")),
    path("integrations/", include("apps.shop_sync.urls")),
    path("reports/", include("apps.reports.urls")),
    path("", RedirectView.as_view(pattern_name="dashboard:index", permanent=False)),
]
