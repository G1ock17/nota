from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import render


def home(request):
    return render(request, 'core/home.html')


class SiteLoginView(LoginView):
    template_name = 'core/login.html'
    redirect_authenticated_user = True


@login_required
def account(request):
    return render(request, 'core/account.html')
