from django.urls import path

from . import views

app_name = "clients"

urlpatterns = [
    path("", views.ClientListView.as_view(), name="list"),
    path("new/", views.ClientCreateView.as_view(), name="create"),
    path("<int:pk>/", views.ClientDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.ClientUpdateView.as_view(), name="edit"),
    path("<int:pk>/delete/", views.ClientDeleteView.as_view(), name="delete"),
]
