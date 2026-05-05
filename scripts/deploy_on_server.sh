#!/bin/sh
# Запускать на сервере в SSH из корня сайта (где manage.py), с активированным venv.
set -e
cd "$(dirname "$0")/.."
pip install -r requirements.txt
python manage.py migrate --noinput
python manage.py collectstatic --noinput
touch .restart-app
echo "Готово. Passenger перезапустится после обработки .restart-app"
