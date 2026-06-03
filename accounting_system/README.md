# Учётная система (Accounting System)

Производственный Django-монолит для учёта финансов: дашборд, транзакции,
счета (с НДС и PDF), клиенты, категории, аналитика и экспорт.

## Стек

- **Backend:** Django 4.2 (LTS), Python 3.11+
- **БД:** MySQL 8 (production), SQLite (development)
- **Шаблоны:** Django Templates (server-side)
- **Интерактивность:** HTMX (CDN) — частичные обновления без перезагрузки
- **Стили:** Tailwind CSS (CDN)
- **Графики:** Chart.js (CDN, vanilla JS)
- **Auth:** встроенная аутентификация Django + роли через `Membership`
- **Экспорт:** openpyxl (Excel), WeasyPrint (PDF счёта)
- **Конфигурация:** python-decouple (`.env`)

## Архитектура

```
config/settings/{base,development,production}.py   # окружения
apps/core         # Organization, абстрактные модели, middleware, миксины, теги
apps/accounts     # Membership (роли), вход/выход, сброс пароля
apps/clients      # клиенты/контрагенты (CRUD + история)
apps/categories   # категории доходов/расходов (дерево)
apps/invoices     # счета + позиции, нумерация INV-YYYY-NNNN, статусы, PDF
apps/transactions # доходы/расходы/переводы, CSV-импорт, бегущий баланс
apps/reports      # аналитика, JSON для Chart.js, экспорт Excel
apps/dashboard    # KPI + графики
```

### Мультиарендность и роли

Все бизнес-данные привязаны к `Organization`. Текущая организация
определяется в `CurrentOrganizationMiddleware` по `Membership` пользователя.

| Роль        | Просмотр | Создание/Редактирование | Удаление |
|-------------|:--------:|:-----------------------:|:--------:|
| OWNER       | ✅       | ✅                      | ✅       |
| ACCOUNTANT  | ✅       | ✅                      | ❌       |
| VIEWER      | ✅       | ❌                      | ❌       |

## Запуск (development)

```bash
cd accounting_system
pip install -r requirements.txt

python manage.py migrate
python manage.py seed_demo          # демо-данные + суперпользователь admin / admin12345
python manage.py runserver
```

Откройте http://127.0.0.1:8000/ и войдите как `admin / admin12345`.

`manage.py` по умолчанию использует `config.settings.development` (SQLite).

## Production

```bash
export DJANGO_SETTINGS_MODULE=config.settings.production
python manage.py collectstatic --noinput
python manage.py migrate
gunicorn config.wsgi:application      # либо WSGI вашего хостинга
```

Заполните `.env` по образцу `.env.example`. Настройки безопасности
(HSTS, secure-cookies, SSL-redirect, X-Frame-Options) включаются автоматически
при `DEBUG=False`.

## Экспорт

- Excel: транзакции, P&L, список счетов (кнопки на соответствующих страницах).
- PDF: отдельный счёт (`/invoices/<id>/pdf/`) — через WeasyPrint.
  Для PDF на сервере нужны системные библиотеки Pango/GTK.

## CSV-импорт транзакций

Колонки: `date, type, amount, category, currency, client, description`.
Тип — `INCOME` / `EXPENSE` / `TRANSFER`. Несуществующие категории создаются автоматически.
