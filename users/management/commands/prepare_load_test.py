from datetime import date, timedelta
import json
from pathlib import Path

from django.contrib.auth.hashers import make_password
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import OuterRef, Q, Subquery
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from users.management.loadtest_manifest import build_account_manifest
from users.models import (
    Akun,
    DokumenSurat,
    JenisSurat,
    KartuKeluarga,
    Notifikasi,
    OTPEmail,
    PendaftaranAkun,
    Penduduk,
    PermohonanSurat,
    RiwayatPersetujuan,
    WilayahRT,
    WilayahRW,
)


PASSWORD = "LoadTest!2026"
EMAIL_PREFIX = "loadtest-"
SCENARIO_EMAIL_PREFIX = "sblt-"
RW_CODE = 99
RT_CODE = 99
KK_NUMBER = "9700000000000001"
ROLE_PREFIXES = {
    "citizen": "91",
    "rt": "92",
    "rw": "93",
    "admin": "94",
    "kades": "95",
    "registration": "96",
}


def test_nik(role, index):
    return f"{ROLE_PREFIXES[role]}{index:014d}"


def test_email(role, index):
    return f"{EMAIL_PREFIX}{role}-{index:04d}@example.invalid"


class Command(BaseCommand):
    help = "Create deterministic data for scenario-based load testing."

    def add_arguments(self, parser):
        parser.add_argument("--citizens", type=int, default=60)
        parser.add_argument("--auth-citizens", type=int, default=500)
        parser.add_argument("--pending-per-stage", type=int, default=5000)
        parser.add_argument("--registrations", type=int, default=25000)
        parser.add_argument("--completed-documents", type=int, default=2500)
        parser.add_argument(
            "--manifest",
            default="loadtest/generated/accounts.json",
            help="Path for the prepared JWT/accounts manifest.",
        )
        parser.add_argument("--reset", action="store_true")
        parser.add_argument("--purge-only", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        citizens_count = options["citizens"]
        auth_citizens_count = options["auth_citizens"]
        pending_count = options["pending_per_stage"]
        registrations_count = options["registrations"]
        completed_documents_count = options["completed_documents"]

        if min(
            citizens_count,
            auth_citizens_count,
            pending_count,
            registrations_count,
            completed_documents_count,
        ) < 1:
            raise CommandError("All fixture counts must be greater than zero.")
        if auth_citizens_count < citizens_count:
            raise CommandError(
                "--auth-citizens must be greater than or equal to --citizens."
            )

        if options["reset"] or options["purge_only"]:
            self._reset()
        if options["purge_only"]:
            self.stdout.write(self.style.SUCCESS("Load-test fixture removed."))
            return

        letter_type = JenisSurat.objects.filter(kode="A01").first()
        if not letter_type or not letter_type.template_file:
            raise CommandError(
                "Letter templates are missing. Run load_letter_templates first."
            )

        rw, _ = WilayahRW.objects.get_or_create(kode_rw=RW_CODE)
        rt, _ = WilayahRT.objects.get_or_create(rw=rw, kode_rt=RT_CODE)
        family, _ = KartuKeluarga.objects.get_or_create(
            nomor_kk=KK_NUMBER,
            defaults={"rt": rt, "alamat": "Wilayah Load Test"},
        )

        password_hash = make_password(PASSWORD)
        citizens = [
            self._account(
                role="citizen",
                index=index,
                account_role=Akun.Peran.WARGA,
                rt=rt,
                family=family,
                password_hash=password_hash,
            )
            for index in range(1, citizens_count + 1)
        ]
        actors = {
            "rt": self._account(
                "rt", 1, Akun.Peran.RT, rt, family, password_hash
            ),
            "rw": self._account(
                "rw", 1, Akun.Peran.RW, rt, family, password_hash
            ),
            "admin": self._account(
                "admin",
                1,
                Akun.Peran.ADMIN,
                rt,
                family,
                password_hash,
                staff=True,
            ),
            "kades": self._account(
                "kades",
                1,
                Akun.Peran.KEPALA_DESA,
                rt,
                family,
                password_hash,
                nip="LOADTEST-2026",
            ),
        }
        for index in range(citizens_count + 1, auth_citizens_count + 1):
            self._account(
                role="citizen",
                index=index,
                account_role=Akun.Peran.WARGA,
                rt=rt,
                family=family,
                password_hash=password_hash,
            )

        self._create_pending_applications(
            citizens=citizens,
            actors=actors,
            letter_type=letter_type,
            per_stage=pending_count,
        )
        self._create_completed_documents(
            citizens,
            letter_type,
            completed_documents_count,
        )
        self._create_registrations(
            rt=rt,
            count=registrations_count,
            password_hash=password_hash,
        )
        self._create_login_otps()
        self._write_manifest(options["manifest"])

        self.stdout.write(
            self.style.SUCCESS(
                "Load-test fixture ready: "
                f"{citizens_count} business citizens, "
                f"{auth_citizens_count} authentication citizens, "
                f"{pending_count} applications per approval stage, "
                f"{completed_documents_count} completed documents, "
                f"{registrations_count} pending registrations."
            )
        )
        self.stdout.write(f"Shared password: {PASSWORD}")
        self.stdout.write("Load-test OTP: value from DJANGO_LOAD_TEST_OTP")
        self.stdout.write(f"Prepared JWT manifest: {options['manifest']}")

    def _write_manifest(self, path):
        accounts = (
            Akun.objects.filter(penduduk__email__startswith=EMAIL_PREFIX)
            .select_related("penduduk")
            .order_by("penduduk_id")
        )
        manifest = build_account_manifest(accounts)
        manifest["approval_candidates"] = self._approval_candidates()
        manifest["registration_candidates"] = self._registration_candidates()
        manifest["application_candidates"] = self._application_candidates()
        manifest["final_document_tokens"] = self._final_document_tokens()
        manifest["wilayah"] = self._wilayah_fixture()
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(manifest, indent=2),
            encoding="utf-8",
        )

    def _approval_candidates(self):
        stage_labels = {
            RiwayatPersetujuan.Tahap.RT: "RT",
            RiwayatPersetujuan.Tahap.RW: "RW",
            RiwayatPersetujuan.Tahap.ADMIN: "ADMIN",
            RiwayatPersetujuan.Tahap.KEPALA_DESA: "KEPALA-DESA",
        }
        latest_riwayat = RiwayatPersetujuan.objects.filter(
            permohonan=OuterRef("pk")
        ).order_by("-waktu")
        applications = (
            PermohonanSurat.objects.filter(nomor_permohonan__startswith="LT/")
            .exclude(nomor_permohonan__startswith="LT/DONE/")
            .annotate(
                riwayat_tahap=Subquery(latest_riwayat.values("tahap")[:1])
            )
            .order_by("riwayat_tahap", "id")
        )
        return [
            {
                "id": application.id,
                "nomor_permohonan": application.nomor_permohonan,
                "stage": stage_labels.get(application.riwayat_tahap),
            }
            for application in applications
            if application.riwayat_tahap in stage_labels
        ]

    def _registration_candidates(self):
        return [
            {"id": row.id, "nik": row.nik}
            for row in (
                PendaftaranAkun.objects.filter(
                    Q(email__startswith=EMAIL_PREFIX)
                    | Q(email__startswith=SCENARIO_EMAIL_PREFIX),
                    status_verifikasi=PendaftaranAkun.StatusVerifikasi.DITINJAU,
                )
                .order_by("id")
            )
        ]

    def _application_candidates(self):
        citizen_index_by_nik = {
            account.penduduk_id: int(account.penduduk_id[2:])
            for account in (
                Akun.objects.filter(
                    penduduk__email__startswith=EMAIL_PREFIX,
                    penduduk__nik__startswith=ROLE_PREFIXES["citizen"],
                )
                .select_related("penduduk")
            )
        }
        return [
            {
                "id": row.id,
                "nomor_permohonan": row.nomor_permohonan,
                "pemohon_nik": row.pemohon_id,
                "citizen_index": citizen_index_by_nik.get(row.pemohon_id),
            }
            for row in (
                PermohonanSurat.objects.filter(
                    nomor_permohonan__startswith="LT/"
                )
                .exclude(nomor_permohonan__startswith="LT/DONE/")
                .order_by("id")
            )
        ]

    def _final_document_tokens(self):
        return [
            str(row.public_token)
            for row in (
                DokumenSurat.objects.filter(
                    permohonan__nomor_permohonan__startswith="LT/DONE/",
                    file_final__gt="",
                )
                .order_by("id")
            )
        ]

    def _wilayah_fixture(self):
        rt = WilayahRT.objects.filter(
            kode_rt=RT_CODE,
            rw__kode_rw=RW_CODE,
        ).first()
        return {
            "rw": RW_CODE,
            "rt": rt.id if rt else None,
        }

    def _create_login_otps(self):
        otp_hash = make_password(
            getattr(settings, "LOAD_TEST_OTP", "") or "246810"
        )
        ttl_hours = getattr(settings, "LOAD_TEST_OTP_TTL_HOURS", 12)
        expires_at = timezone.now() + timedelta(hours=ttl_hours)
        accounts = Akun.objects.filter(
            penduduk__email__startswith=EMAIL_PREFIX,
            is_active=True,
        )
        for account in accounts:
            OTPEmail.objects.update_or_create(
                akun=account,
                tujuan=OTPEmail.Tujuan.LOGIN,
                defaults={
                    "kode_hash": otp_hash,
                    "kedaluwarsa_at": expires_at,
                    "dipakai_at": None,
                },
            )

    def _reset(self):
        test_residents = Penduduk.objects.filter(
            Q(email__startswith=EMAIL_PREFIX)
            | Q(email__startswith=SCENARIO_EMAIL_PREFIX)
        )
        family_ids = list(
            test_residents.exclude(kk_id=None).values_list(
                "kk_id",
                flat=True,
            )
        )
        self._delete_test_applications(test_residents)
        test_registrations = PendaftaranAkun.objects.filter(
            Q(email__startswith=EMAIL_PREFIX)
            | Q(email__startswith=SCENARIO_EMAIL_PREFIX)
        )
        test_registrations.filter(
            status_verifikasi=PendaftaranAkun.StatusVerifikasi.DISETUJUI
        ).update(
            status_verifikasi=PendaftaranAkun.StatusVerifikasi.DITINJAU
        )
        test_registrations.delete()
        Akun.objects.filter(
            Q(penduduk__email__startswith=EMAIL_PREFIX)
            | Q(penduduk__email__startswith=SCENARIO_EMAIL_PREFIX)
        ).delete()
        for attempt in range(1, 4):
            self._delete_test_applications(test_residents)
            try:
                test_residents.delete()
                break
            except ProtectedError as exc:
                if attempt == 3:
                    raise CommandError(
                        "Load-test reset could not delete residents because "
                        "new applications still reference them. Stop active "
                        "load-test traffic, then run the reset again."
                    ) from exc
        KartuKeluarga.objects.filter(
            Q(pk__in=family_ids) | Q(nomor_kk=KK_NUMBER)
        ).delete()
        self.stdout.write("Previous load-test fixture removed.")

    def _delete_test_applications(self, test_residents):
        PermohonanSurat.objects.filter(
            Q(pemohon__in=test_residents)
            | Q(nomor_permohonan__startswith="LT/")
                    | Q(data__tujuan="Scenario-based load testing")
                    | Q(data__tujuan="Download load-test document")
                    | Q(data__tujuan="Pengujian performa")
        ).delete()

    def _account(
        self,
        role,
        index,
        account_role,
        rt,
        family,
        password_hash,
        staff=False,
        nip=None,
    ):
        nik = test_nik(role, index)
        resident, _ = Penduduk.objects.update_or_create(
            nik=nik,
            defaults={
                "nama_lengkap": f"Load Test {role.title()} {index}",
                "tempat_lahir": "Semarang",
                "tanggal_lahir": date(1990, 1, 1),
                "jenis_kelamin": Penduduk.JenisKelamin.LAKI_LAKI,
                "agama": Penduduk.Agama.ISLAM,
                "email": test_email(role, index),
                "no_hp": f"08{index:010d}",
                "rt": rt,
                "kk": family,
            },
        )
        account, _ = Akun.objects.update_or_create(
            penduduk=resident,
            defaults={
                "peran": account_role,
                "password": password_hash,
                "is_staff": staff,
                "is_superuser": staff,
                "is_active": True,
                "nip": nip,
            },
        )
        return account

    def _create_pending_applications(
        self,
        citizens,
        actors,
        letter_type,
        per_stage,
    ):
        stage_actors = {
            RiwayatPersetujuan.Tahap.RT: actors["rt"],
            RiwayatPersetujuan.Tahap.RW: actors["rw"],
            RiwayatPersetujuan.Tahap.ADMIN: actors["admin"],
            RiwayatPersetujuan.Tahap.KEPALA_DESA: actors["kades"],
        }
        now = timezone.now()

        for stage, actor in stage_actors.items():
            label = RiwayatPersetujuan.Tahap(stage).label.upper().replace(
                " ", "-"
            )
            applications = [
                PermohonanSurat(
                    nomor_permohonan=f"LT/{label}/{index:06d}",
                    jenis_surat=letter_type,
                    pemohon=citizens[(index - 1) % len(citizens)].penduduk,
                    status=PermohonanSurat.Status.DIAJUKAN,
                    data={"tujuan": "Scenario-based load testing"},
                    diajukan_at=now,
                )
                for index in range(1, per_stage + 1)
            ]
            PermohonanSurat.objects.bulk_create(
                applications,
                ignore_conflicts=True,
            )
            stored = list(
                PermohonanSurat.objects.filter(
                    nomor_permohonan__startswith=f"LT/{label}/"
                ).order_by("id")
            )
            existing_ids = set(
                RiwayatPersetujuan.objects.filter(
                    permohonan__in=stored,
                    tahap=stage,
                ).values_list("permohonan_id", flat=True)
            )
            RiwayatPersetujuan.objects.bulk_create(
                [
                    RiwayatPersetujuan(
                        permohonan=application,
                        tahap=stage,
                        aksi=RiwayatPersetujuan.Aksi.AJUKAN,
                        oleh_akun=actor,
                        waktu=now,
                    )
                    for application in stored
                    if application.id not in existing_ids
                ]
            )

    def _create_completed_documents(self, citizens, letter_type, count):
        for index in range(1, count + 1):
            account = citizens[(index - 1) % len(citizens)]
            application, _ = PermohonanSurat.objects.get_or_create(
                nomor_permohonan=f"LT/DONE/{index:06d}",
                defaults={
                    "jenis_surat": letter_type,
                    "pemohon": account.penduduk,
                    "status": PermohonanSurat.Status.SELESAI,
                    "data": {"tujuan": "Download load-test document"},
                    "diajukan_at": timezone.now(),
                    "selesai_at": timezone.now(),
                },
            )
            document, _ = DokumenSurat.objects.get_or_create(
                permohonan=application
            )
            if not document.file_final:
                document.file_final.save(
                    f"load-test-{index:04d}.pdf",
                    ContentFile(
                        b"%PDF-1.4\n% Dekstra load-test document\n%%EOF\n"
                    ),
                    save=True,
                )
            Notifikasi.objects.get_or_create(
                penerima=account,
                permohonan=application,
                tipe=Notifikasi.Tipe.SELESAI,
            )

    def _create_registrations(self, rt, count, password_hash):
        records = []
        for index in range(1, count + 1):
            nik = test_nik("registration", index)
            records.append(
                PendaftaranAkun(
                    nomor_kk=f"98{index:014d}",
                    nik=nik,
                    nama_lengkap=f"Load Test Registration {index}",
                    tempat_lahir="Semarang",
                    tanggal_lahir=date(1990, 1, 1),
                    jenis_kelamin=PendaftaranAkun.JenisKelamin.LAKI_LAKI,
                    agama=PendaftaranAkun.Agama.ISLAM,
                    rt=rt,
                    alamat="Alamat Load Test",
                    email=test_email("registration", index),
                    no_hp=f"08{index:010d}",
                    password_hash=password_hash,
                    status_verifikasi=PendaftaranAkun.StatusVerifikasi.DITINJAU,
                )
            )
        PendaftaranAkun.objects.bulk_create(records, ignore_conflicts=True)
