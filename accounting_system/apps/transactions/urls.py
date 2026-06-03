from django.urls import path

from . import views

app_name = "transactions"

urlpatterns = [
    path("", views.TransactionListView.as_view(), name="list"),
    path("new/", views.TransactionCreateView.as_view(), name="create"),
    path("import/", views.TransactionImportView.as_view(), name="import"),
    path("<int:pk>/edit/", views.TransactionUpdateView.as_view(), name="edit"),
    path("<int:pk>/delete/", views.TransactionDeleteView.as_view(), name="delete"),
]
