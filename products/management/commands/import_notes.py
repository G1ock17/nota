import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from products.models import FragranceNote


class Command(BaseCommand):
    help = "Импорт нот из JSON-файла"

    def add_arguments(self, parser):
        parser.add_argument("file", type=str, help="Путь к JSON-файлу с нотами")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Только проверить, ничего не сохранять в базу",
        )
        parser.add_argument(
            "--update",
            action="store_true",
            help="Обновлять существующие записи (name/type), если отличаются",
        )

    def handle(self, *args, **options):
        file_path = Path(options["file"])
        if not file_path.exists():
            raise CommandError(f"Файл не найден: {file_path}")

        with file_path.open("r", encoding="utf-8") as f:
            raw_data = json.load(f)

        if isinstance(raw_data, list):
            notes_data = raw_data
        elif isinstance(raw_data, dict):
            notes_data = raw_data.get("notes", [])
        else:
            raise CommandError("Некорректный формат JSON: ожидается список или объект с ключом 'notes'")

        if not notes_data:
            self.stdout.write(self.style.WARNING("В JSON нет данных для импорта нот"))
            return

        valid_types = {choice for choice, _ in FragranceNote.NoteType.choices}
        dry_run = options.get("dry_run", False)
        allow_update = options.get("update", False)

        created = 0
        updated = 0
        skipped = 0

        with transaction.atomic():
            for idx, note_data in enumerate(notes_data, start=1):
                name = (note_data.get("name") or "").strip()
                slug = (note_data.get("slug") or "").strip()
                note_type = (note_data.get("type") or "").strip().lower()

                if not name:
                    self.stdout.write(self.style.WARNING(f"[{idx}] Пропуск: пустое поле 'name'"))
                    skipped += 1
                    continue

                if not slug:
                    slug = slugify(name)

                if note_type not in valid_types:
                    self.stdout.write(
                        self.style.WARNING(
                            f"[{idx}] Пропуск: неверный type='{note_type}' для '{name}'. "
                            f"Допустимо: {', '.join(sorted(valid_types))}"
                        )
                    )
                    skipped += 1
                    continue

                if dry_run:
                    exists = FragranceNote.objects.filter(slug=slug).exists()
                    status = "уже существует" if exists else "будет создана"
                    self.stdout.write(f"[DRY-RUN] {name} ({slug}, {note_type}) — {status}")
                    continue

                note, is_created = FragranceNote.objects.get_or_create(
                    slug=slug,
                    defaults={"name": name, "type": note_type},
                )

                if is_created:
                    created += 1
                    self.stdout.write(self.style.SUCCESS(f"✓ Создана: {name} ({note_type})"))
                    continue

                if allow_update:
                    changed = False
                    if note.name != name:
                        note.name = name
                        changed = True
                    if note.type != note_type:
                        note.type = note_type
                        changed = True
                    if changed:
                        note.save(update_fields=["name", "type"])
                        updated += 1
                        self.stdout.write(self.style.SUCCESS(f"✓ Обновлена: {name} ({note_type})"))
                    else:
                        skipped += 1
                        self.stdout.write(f"→ Уже актуальна: {name}")
                else:
                    skipped += 1
                    self.stdout.write(f"→ Уже существует: {name}")

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDRY-RUN завершён — данные НЕ были сохранены"))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nИмпорт нот успешно завершён!\n"
                    f"Создано: {created} | Обновлено: {updated} | Пропущено: {skipped}"
                )
            )
