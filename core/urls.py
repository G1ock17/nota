from django.contrib.auth.views import LogoutView, PasswordChangeDoneView, PasswordChangeView
from django.urls import path, reverse_lazy

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('brands/', views.brands, name='brands'),
    path('podbor/', views.podbor, name='podbor'),
    path('podbor/api/results/', views.podbor_results, name='podbor_results'),
    path('gift-cards/', views.gift_cards_catalog, name='gift_cards'),
    path('account/gift-cards/', views.account_gift_cards, name='account_gift_cards'),

    path('delivery/', views.info_page, {'page': 'delivery'}, name='info_delivery'),
    path('returns/', views.info_page, {'page': 'returns'}, name='info_returns'),
    path('about/', views.info_page, {'page': 'about'}, name='info_about'),
    path('contacts/', views.info_page, {'page': 'contacts'}, name='info_contacts'),
    path('privacy/', views.info_page, {'page': 'privacy'}, name='info_privacy'),
    path('offer/', views.info_page, {'page': 'offer'}, name='info_offer'),

    path('accounts/login/', views.login_view, name='login'),
    path('accounts/register/', views.register_view, name='register'),
    path('accounts/verify/<str:token>/', views.email_verify, name='email_verify'),
    path('accounts/resend-verification/', views.resend_verification, name='resend_verification'),
    path('accounts/profile-setup/', views.profile_setup, name='profile_setup'),
    path('accounts/password/reset/', views.password_reset_request, name='password_reset'),
    path('accounts/password/reset/<str:token>/', views.password_reset_confirm, name='password_reset_confirm'),
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
