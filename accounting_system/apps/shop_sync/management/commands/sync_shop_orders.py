"""Import paid orders from the Accord shop database."""
from datetime import datetime

from django.core.management.base import BaseCommand

from apps.core.models import Organization
from apps.shop_sync.services import sync_shop_orders, test_shop_connection


class Command(BaseCommand):
    help = "Синхронизировать оплаченные заказы магазина Accord → транзакции дохода."

    def add_arguments(self, parser):
        parser.add_argument(
            "--org",
            default="",
            help="Slug организации (по умолчанию — первая в базе).",
        )
        parser.add_argument(
            "--since",
            default="",
            help="Импортировать заказы с даты, YYYY-MM-DD.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Только показать, сколько записей будет создано.",
        )

    def handle(self, *args, **options):
        ok, msg = test_shop_connection()
        if not ok:
            self.stderr.write(self.style.ERROR(msg))
            return

        org_slug = options["org"].strip()
        if org_slug:
            org = Organization.objects.filter(slug=org_slug).first()
        else:
            org = Organization.objects.first()
        if org is None:
            self.stderr.write(self.style.ERROR("Организация не найдена."))
            return

        since = None
        if options["since"]:
            since = datetime.strptime(options["since"], "%Y-%m-%d").date()

        result = sync_shop_orders(org, since=since, dry_run=options["dry_run"])
        if result.errors:
            for err in result.errors:
                self.stderr.write(self.style.ERROR(err))
            return

        prefix = "[dry-run] " if options["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Организация «{org.name}»: создано {result.created}, "
                f"пропущено (уже есть) {result.skipped}."
            )
        )
