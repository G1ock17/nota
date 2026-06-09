#!/bin/bash
# Запуск на сервере: bash diagnose.sh
# Покажет, что не так с поддоменом accounting.accordroyally.com

set -e

DOMAIN_DIR="/var/www/u3413005/data/www/accounting.accordroyally.com"
SHOP_DIR="/var/www/u3413005/data/www/accordroyally.com"
VENV_PY="$SHOP_DIR/venv/bin/python"

echo "========== 1. Папка поддомена =========="
echo "Ожидаем: $DOMAIN_DIR"
if [ -d "$DOMAIN_DIR" ]; then
  echo "OK: папка существует"
  ls -la "$DOMAIN_DIR" | head -25
else
  echo "ОШИБКА: папки нет! Проверьте корневую директорию в ISPmanager."
  exit 1
fi

echo ""
echo "========== 2. Обязательные файлы =========="
for f in manage.py passenger_wsgi.py .env .htaccess config/wsgi.py; do
  if [ -e "$DOMAIN_DIR/$f" ]; then
    echo "OK: $f"
  else
    echo "НЕТ: $f"
  fi
done

echo ""
echo "========== 3. .htaccess =========="
if [ -f "$DOMAIN_DIR/.htaccess" ]; then
  cat "$DOMAIN_DIR/.htaccess"
else
  echo "Файл .htaccess отсутствует"
fi

echo ""
echo "========== 4. Python / venv =========="
if [ -x "$VENV_PY" ]; then
  echo "OK: $VENV_PY"
  "$VENV_PY" --version
else
  echo "НЕТ: $VENV_PY"
fi

echo ""
echo "========== 5. Django setup (как сайт) =========="
cd "$DOMAIN_DIR"
export DJANGO_SETTINGS_MODULE=config.settings.production
"$VENV_PY" -c "
import sys
sys.path.insert(0, '.')
sys.path.insert(1, '/var/www/u3413005/data/djangoenv/lib/python3.10/site-packages')
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')
import django
django.setup()
print('Django setup: OK')
" 2>&1 || echo "Django setup: ОШИБКА (см. выше)"

echo ""
echo "========== 6. WSGI application =========="
"$VENV_PY" -c "
import sys
sys.path.insert(0, '$DOMAIN_DIR')
import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.production'
# имитация passenger_wsgi
exec(open('$DOMAIN_DIR/passenger_wsgi.py').read().split('application = get_wsgi_application()')[0])
from django.core.wsgi import get_wsgi_application
app = get_wsgi_application()
print('WSGI: OK')
" 2>&1 || echo "Попробуйте: cd $DOMAIN_DIR && $VENV_PY passenger_wsgi.py 2>&1 | head -5"

echo ""
echo "========== 7. Лог ошибок =========="
if [ -f "$DOMAIN_DIR/logs/wsgi_error.log" ]; then
  tail -30 "$DOMAIN_DIR/logs/wsgi_error.log"
else
  echo "logs/wsgi_error.log пока пуст/нет — Passenger ещё не дошёл до Django"
fi

echo ""
echo "========== 8. Сравнение с рабочим магазином =========="
echo "Магазин passenger_wsgi:"
ls -la "$SHOP_DIR/passenger_wsgi.py" 2>/dev/null || ls -la "$SHOP_DIR/public_html/passenger_wsgi.py" 2>/dev/null || echo "не найден"
echo "Магазин .htaccess:"
ls -la "$SHOP_DIR/.htaccess" 2>/dev/null || ls -la "$SHOP_DIR/public_html/.htaccess" 2>/dev/null || echo "нет .htaccess (нормально для reg.ru)"

echo ""
echo "========== 9. DNS / HTTP =========="
curl -sI -o /dev/null -w "HTTP %{http_code} -> %{url_effective}\n" https://accounting.accordroyally.com/ 2>/dev/null || echo "curl недоступен или домен не отвечает"

echo ""
echo "========== ГОТОВО =========="
echo "Пришлите ВЕСЬ этот вывод в чат."
