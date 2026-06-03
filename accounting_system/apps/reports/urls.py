from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.ReportsIndexView.as_view(), name="index"),
    path("api/chart-data/", views.DashboardChartDataView.as_view(), name="chart_data"),
    path("export/transactions.xlsx", views.ExportTransactionsXlsx.as_view(), name="export_transactions"),
    path("export/pnl.xlsx", views.ExportPnlXlsx.as_view(), name="export_pnl"),
    path("export/invoices.xlsx", views.ExportInvoicesXlsx.as_view(), name="export_invoices"),
]
