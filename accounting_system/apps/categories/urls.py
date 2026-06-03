from django.urls import path

from . import views

app_name = "categories"

urlpatterns = [
    path("", views.CategoryListView.as_view(), name="list"),
    path("new/", views.CategoryCreateView.as_view(), name="create"),
    path("<int:pk>/edit/", views.CategoryUpdateView.as_view(), name="edit"),
    path("<int:pk>/delete/", views.CategoryDeleteView.as_view(), name="delete"),
]
