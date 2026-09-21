from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from users.models import JenisSurat


class Command(BaseCommand):
    help = "Load the bundled DOCX and XLSX letter templates."

    @transaction.atomic
    def handle(self, *args, **options):
        template_dir = Path(settings.BASE_DIR) / "template_surat"
        files = sorted(
            path
            for path in template_dir.iterdir()
            if path.suffix.lower() in {".docx", ".xlsx"}
        )
        if not files:
            raise CommandError(f"No templates found in {template_dir}.")

        loaded = 0
        for path in files:
            code, separator, name = path.stem.partition(" - ")
            if not separator:
                self.stderr.write(f"Skipped unexpected filename: {path.name}")
                continue

            letter_type, _ = JenisSurat.objects.update_or_create(
                kode=code,
                defaults={
                    "nama": name,
                    "aktif": True,
                },
            )
            if letter_type.template_file:
                letter_type.template_file.delete(save=False)

            with path.open("rb") as template_file:
                letter_type.template_file.save(
                    path.name,
                    File(template_file),
                    save=True,
                )
            loaded += 1
            self.stdout.write(f"Loaded {code}: {path.name}")

        self.stdout.write(
            self.style.SUCCESS(f"{loaded} letter templates loaded.")
        )
