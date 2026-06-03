"""Import shop orders from CSV/Excel file (phpMyAdmin export)."""
from django.core.management.base import BaseCommand

from apps.core.models import Organization
from apps.shop_sync.services import import_shop_orders_from_file


class Command(BaseCommand):
    help = "Импорт заказов из CSV/Excel (экспорт phpMyAdmin → products_order)."

    def add_arguments(self, parser):
        parser.add_argument("file", help="Путь к .csv или .xlsx")
        parser.add_argument("--org", default="", help="Slug организации")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        org_slug = options["org"].strip()
        org = (
            Organization.objects.filter(slug=org_slug).first()
            if org_slug
            else Organization.objects.first()
        )
        if org is None:
            self.stderr.write(self.style.ERROR("Организация не найдена."))
            return

        path = options["file"]
        with open(path, "rb") as f:
            result = import_shop_orders_from_file(
                org, f, path, dry_run=options["dry_run"],
            )

        for err in result.errors or []:
            self.stderr.write(self.style.WARNING(err))

        prefix = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}«{org.name}»: импортировано {result.created}, пропущено {result.skipped}."
            )
        )
