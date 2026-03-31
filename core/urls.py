from django.contrib.auth.views import LogoutView, PasswordChangeDoneView, PasswordChangeView
from django.urls import path, reverse_lazy

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('accounts/login/', views.SiteLoginView.as_view(), name='login'),
    path('accounts/register/', views.RegisterView.as_view(), name='register'),
    path(
        'accounts/logout/',
        LogoutView.as_view(next_page='/'),
        name='logout',
    ),
    path('accounts/', views.account, name='account'),
    path('accounts/orders/<int:order_id>/', views.order_detail, name='order_detail'),
    path(
        'accounts/password/change/',
        PasswordChangeView.as_view(
            template_name='core/password_change.html',
            success_url=reverse_lazy('password_change_done'),
        ),
        name='password_change',
    ),
    path(
        'accounts/password/change/done/',
        PasswordChangeDoneView.as_view(template_name='core/password_change_done.html'),
        name='password_change_done',
    ),
]
