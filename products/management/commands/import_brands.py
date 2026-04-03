import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

# ←←← ИЗМЕНИ ЭТУ СТРОКУ под своё приложение и модель
from products.models import Brand


class Command(BaseCommand):
    help = "Импорт брендов из JSON-файла"

    def add_arguments(self, parser):
        parser.add_argument('file', type=str, help='Путь к JSON-файлу с брендами')
        parser.add_argument('--dry-run', action='store_true',
                            help='Только проверить, ничего не сохранять в базу')
        parser.add_argument('--update', action='store_true',
                            help='Обновлять имя бренда, если оно изменилось')

    def handle(self, *args, **options):
        file_path = Path(options['file'])

        if not file_path.exists():
            raise CommandError(f"Файл не найден: {file_path}")

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        brands_data = data.get('brands', [])
        if not brands_data:
            self.stdout.write(self.style.WARNING("В JSON нет раздела 'brands'"))
            return

        dry_run = options.get('dry_run', False)
        update = options.get('update', False)

        created = 0
        updated = 0
        skipped = 0

        with transaction.atomic():
            for brand_data in brands_data:
                name = brand_data.get('name')
                if not name:
                    continue

                # Используем slug из JSON, если есть, иначе генерируем
                slug = brand_data.get('slug') or slugify(name)

                if dry_run:
                    exists = Brand.objects.filter(slug=slug).exists()
                    status = "уже существует" if exists else "будет создан"
                    self.stdout.write(f"[DRY-RUN] {name} ({slug}) — {status}")
                    continue

                # Основной импорт
                brand, is_created = Brand.objects.update_or_create(
                    slug=slug,
                    defaults={'name': name}
                )

                if is_created:
                    created += 1
                    self.stdout.write(self.style.SUCCESS(f"✓ Создан: {name}"))
                else:
                    if update and brand.name != name:
                        brand.name = name
                        brand.save()
                        updated += 1
                        self.stdout.write(self.style.SUCCESS(f"✓ Обновлён: {name}"))
                    else:
                        skipped += 1
                        self.stdout.write(f"→ Уже существует: {name}")

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDRY-RUN завершён — данные НЕ были сохранены"))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"\nИмпорт брендов успешно завершён!\n"
                f"Создано: {created} | Обновлено: {updated} | Пропущено: {skipped}"
            ))