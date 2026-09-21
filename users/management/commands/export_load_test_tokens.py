import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from users.management.loadtest_manifest import build_account_manifest
from users.models import Akun


class Command(BaseCommand):
    help = "Export JWT manifest for load-test fixture accounts."

    def handle(self, *args, **options):
        if not settings.LOAD_TEST_MODE:
            raise CommandError(
                "Manifest export is only available when "
                "DJANGO_LOAD_TEST_MODE=true."
            )

        accounts = (
            Akun.objects.filter(penduduk__email__startswith="loadtest-")
            .select_related("penduduk")
            .order_by("penduduk_id")
        )
        manifest = build_account_manifest(accounts)
        if not manifest["accounts"]:
            raise CommandError(
                "No load-test accounts found. Run prepare_load_test first."
            )

        self.stdout.write(
            json.dumps(
                manifest,
                separators=(",", ":"),
            )
        )
