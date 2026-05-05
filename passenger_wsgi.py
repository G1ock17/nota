# -*- coding: utf-8 -*-
"""
Точка входа WSGI для Phusion Passenger (REG.RU / ispmanager).

Положите проект в корень сайта (рядом с manage.py). После обновления кода:
  touch .restart-app
в каталоге сайта — Passenger подхватит изменения.

Подробнее: https://help.reg.ru/support/hosting/php-asp-net-i-skripty/kak-ustanovit-django-na-hosting
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_venv = os.environ.get("VIRTUAL_ENV")
if _venv:
    _py = f"python{sys.version_info.major}.{sys.version_info.minor}"
    _site = os.path.join(_venv, "lib", _py, "site-packages")
    if os.path.isdir(_site) and _site not in sys.path:
        sys.path.insert(1, _site)

# Если при старте сайта «No module named django», раскомментируйте и укажите
# site-packages вашего venv (как в панели REG.RU после ls):
# sys.path.insert(1, "/var/www/ВАШ_ЛОГИН/data/djangoenv/lib/python3.12/site-packages")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "perfume_store.settings")

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
