import uuid
from unittest.mock import Mock, patch

from django.test import SimpleTestCase
from django.urls import resolve, reverse
from rest_framework import permissions

from .models import JenisSurat, PermohonanSurat
from .views import DownloadBerkasView, ProtectedApplicationFileView


class PublicApplicationFileRouteTests(SimpleTestCase):
    def test_route_uses_public_uuid_token(self):
        token = uuid.uuid4()
        path = reverse("protected-application-file", kwargs={"token": token})

        self.assertEqual(path, f"/media/permohonan/{token}/")
        self.assertIs(resolve(path).func.view_class, ProtectedApplicationFileView)

    def test_route_does_not_require_authentication(self):
        self.assertEqual(ProtectedApplicationFileView.authentication_classes, [])
        self.assertEqual(
            ProtectedApplicationFileView.permission_classes,
            [permissions.AllowAny],
        )

    def test_final_document_does_not_require_authentication(self):
        self.assertEqual(DownloadBerkasView.authentication_classes, [])
        self.assertEqual(
            DownloadBerkasView.permission_classes,
            [permissions.AllowAny],
        )


class PermohonanSuratNumberGenerationTests(SimpleTestCase):
    def test_initial_insert_uses_unique_placeholder_before_final_number(self):
        letter_type = JenisSurat(kode="A01")
        citizen = Mock(rt=None)
        application = PermohonanSurat(
            jenis_surat=letter_type,
            pemohon=citizen,
            status=PermohonanSurat.Status.DIAJUKAN,
        )
        saved_numbers = []

        def fake_model_save(instance, *args, **kwargs):
            saved_numbers.append(instance.nomor_permohonan)
            if instance.id is None:
                instance.id = 321

        history_queryset = Mock()
        history_queryset.exists.return_value = True

        with patch(
            "django.db.models.base.Model.save",
            autospec=True,
            side_effect=fake_model_save,
        ) as model_save, patch(
            "users.models.RiwayatPersetujuan.objects.filter",
            return_value=history_queryset,
        ):
            application.save()

        self.assertEqual(model_save.call_count, 2)
        self.assertEqual(len(saved_numbers), 2)
        self.assertTrue(saved_numbers[0].startswith("PENDING/"))
        self.assertNotEqual(saved_numbers[0], "")
        self.assertTrue(saved_numbers[1].endswith("/A01/321"))
        self.assertEqual(application.nomor_permohonan, saved_numbers[1])
