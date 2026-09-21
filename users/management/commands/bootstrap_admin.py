from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import transaction

from users.models import Akun, Penduduk


class Command(BaseCommand):
    help = "Create or update the initial Dekstra administrator."

    def add_arguments(self, parser):
        parser.add_argument("--nik", required=True)
        parser.add_argument("--name", required=True)
        parser.add_argument("--email", required=True)
        parser.add_argument("--password", required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        nik = options["nik"].strip()
        name = options["name"].strip()
        email = options["email"].strip().lower()
        password = options["password"]

        if len(nik) != 16 or not nik.isdigit():
            raise CommandError("NIK must contain exactly 16 digits.")

        try:
            validate_email(email)
            validate_password(password)
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        email_owner = Penduduk.objects.filter(email=email).exclude(nik=nik).first()
        if email_owner:
            raise CommandError("The email address belongs to another resident.")

        resident, _ = Penduduk.objects.get_or_create(
            nik=nik,
            defaults={
                "nama_lengkap": name,
                "email": email,
            },
        )
        resident.nama_lengkap = name
        resident.email = email
        resident.save(update_fields=["nama_lengkap", "email", "updated_at"])

        account, _ = Akun.objects.get_or_create(
            penduduk=resident,
            defaults={"peran": Akun.Peran.ADMIN},
        )
        account.peran = Akun.Peran.ADMIN
        account.is_staff = True
        account.is_superuser = True
        account.is_active = True
        account.set_password(password)
        account.save()

        self.stdout.write(
            self.style.SUCCESS(f"Administrator {nik} is ready.")
        )
