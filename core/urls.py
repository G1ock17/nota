from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('accounts/login/', views.SiteLoginView.as_view(), name='login'),
    path(
        'accounts/logout/',
        LogoutView.as_view(next_page='/'),
        name='logout',
    ),
    path('accounts/', views.account, name='account'),
]
