"""Template context: active organization, role flags, sidebar navigation."""
from .utils import role_flags


def organization(request):
    membership = getattr(request, "membership", None)
    flags = role_flags(membership)
    return {
        "current_organization": getattr(request, "organization", None),
        "current_membership": membership,
        "role_flags": flags,
        "can_create": flags["can_create"],
        "can_edit": flags["can_edit"],
        "can_delete": flags["can_delete"],
    }


def navigation(request):
    items = [
        {"label": "Дашборд", "url": "dashboard:index", "icon": "layout-dashboard", "match": "/dashboard/"},
        {"label": "Транзакции", "url": "transactions:list", "icon": "arrow-left-right", "match": "/transactions/"},
        {"label": "Счета", "url": "invoices:list", "icon": "file-text", "match": "/invoices/"},
        {"label": "Клиенты", "url": "clients:list", "icon": "users", "match": "/clients/"},
        {"label": "Категории", "url": "categories:list", "icon": "tags", "match": "/categories/"},
        {"label": "Отчёты", "url": "reports:index", "icon": "bar-chart-3", "match": "/reports/"},
    ]
    path = request.path
    for item in items:
        item["active"] = path.startswith(item["match"])
    return {"nav_items": items}
