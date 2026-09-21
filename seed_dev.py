import os
import django
import random
import string
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dekstra.settings")
django.setup()

from django.core.files import File
from django.utils import timezone

from users.models import (
    JenisSurat,
    WilayahRW,
    WilayahRT,
    KartuKeluarga,
    Penduduk,
    Akun,
)

# =========================
# CONFIG PATH TEMPLATE SURAT
# =========================
BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "template_surat"

DEFAULT_PASSWORD = "admin"

# =========================
# DATA
# =========================

DATA_JENIS_SURAT = [
    ("A01", "Surat Keterangan Usaha"),
    ("A02", "Surat Keterangan Tempat Usaha"),
    ("A03", "Surat Keterangan Pengantar Barang"),
    ("A04", "Surat Keterangan Tidak Mampu (Sekolah)"),
    ("A05", "Permohonan Izin Keramaian"),
    ("A06", "Surat Pengantar SKCK"),
    ("A07", "Surat Keterangan Ahli Waris"),
    ("A08", "Surat Keterangan Lainnya"),
    ("B01", "Formulir Kartu Keluarga (Pengganti F-1.01)"),
    ("B02", "Formulir Pendaftaran Peristiwa Kependudukan (F-1.02)"),
    ("B03", "Formulir Permohonan KK Baru WNI (F-1.15)"),
    ("B04", "Formulir Permohonan Perubahan KK Baru WNI (F-1.16)"),
    ("B05", "Formulir Permohonan KTP (F-1.21)"),
    ("B06", "Surat Keterangan Domisili"),
    ("B07", "Surat Keterangan Kehilangan KK"),
    ("B08", "Surat Keterangan Pindah Penduduk"),
    ("B09", "Formulir Pendaftaran Perpindahan Penduduk (F-1.03)"),
    ("B10", "Surat Keterangan Kelahiran"),
    ("B11", "Surat Keterangan Kematian"),
]

TEMPLATE_MAPPING = {
    "A01": "A01 - Surat Keterangan Usaha.docx",
    "A02": "A02 - Surat Keterangan Tempat Usaha.docx",
    "A03": "A03 - Surat Keterangan Pengantar Barang.docx",
    "A04": "A04 - Surat Keterangan Tidak Mampu (Sekolah).docx",
    "A05": "A05 - Permohonan Izin Keramaian.docx",
    "A06": "A06 - Surat Pengantar SKCK.docx",
    "A07": "A07 - Surat Keterangan Ahli Waris.docx",
    "A08": "A08 - Surat Keterangan Lainnya.docx",
    "B01": "B01 - Formulir Kartu Keluarga (Pengganti F-1.01).xlsx",
    "B02": "B02 - Formulir Pendaftaran Peristiwa Kependudukan (F-1.02).xlsx",
    "B03": "B03 - Formulir Permohonan KK Baru WNI (F-1.15).xlsx",
    "B04": "B04 - Formulir Permohonan Perubahan KK Baru WNI (F-1.16).xlsx",
    "B05": "B05 - Formulir Permohonan KTP (F-1.21).xlsx",
    "B06": "B06 - Surat Keterangan Domisili.docx",
    "B07": "B07 - Surat Keterangan Kehilangan KK.docx",
    "B08": "B08 - Surat Keterangan Pindah Penduduk.docx",
    "B09": "B09 - Formulir Pendaftaran Perpindahan Penduduk (F-1.03).xlsx",
    "B10": "B10 - Surat Keterangan Kelahiran.docx",
    "B11": "B11 - Surat Keterangan Kematian.docx",
}

# =========================
# HELPER
# =========================

def generate_digits(n=16):
    return ''.join(random.choices(string.digits, k=n))


def unique_nik():
    while True:
        nik = generate_digits()
        if not Penduduk.objects.filter(nik=nik).exists():
            return nik


def unique_kk():
    while True:
        kk = generate_digits()
        if not KartuKeluarga.objects.filter(nomor_kk=kk).exists():
            return kk


# =========================
# SEED JENIS SURAT
# =========================

def seed_jenis_surat():
    print("\n=== JENIS SURAT ===")

    for kode, nama in DATA_JENIS_SURAT:
        obj, _ = JenisSurat.objects.get_or_create(
            kode=kode,
            defaults={"nama": nama, "aktif": True}
        )

        filename = TEMPLATE_MAPPING.get(kode)
        if filename:
            path = TEMPLATE_DIR / filename

            if path.exists():
                # hapus file lama (opsional tapi disarankan)
                if obj.template_file:
                    obj.template_file.delete(save=False)

                with open(path, "rb") as f:
                    obj.template_file.save(filename, File(f), save=True)

                print(f"{kode} template di tambahkkan / replace")
            else:
                print(f"{kode} file tidak ditemukan")


# =========================
# SEED WILAYAH
# =========================

def seed_wilayah():
    print("\n=== WILAYAH ===")

    rw1, _ = WilayahRW.objects.get_or_create(kode_rw=1)
    rw2, _ = WilayahRW.objects.get_or_create(kode_rw=2)

    rt1, _ = WilayahRT.objects.get_or_create(rw=rw1, kode_rt=1)
    rt2, _ = WilayahRT.objects.get_or_create(rw=rw2, kode_rt=2)

    return rt1, rt2


# =========================
# SEED KK
# =========================

def seed_kk(rt1, rt2):
    print("\n=== KARTU KELUARGA ===")

    kk1 = KartuKeluarga.objects.get_or_create(
        nomor_kk=unique_kk(),
        defaults={"rt": rt1, "alamat": "Jl Mawar"}
    )[0]

    kk2 = KartuKeluarga.objects.get_or_create(
        nomor_kk=unique_kk(),
        defaults={"rt": rt2, "alamat": "Jl Melati"}
    )[0]

    return kk1, kk2

# =========================
# SEED AKUN
# =========================

def create_dummy_akun(nama, email, peran, rt, kk,
                      staff=False, superuser=False, nik=None, nip=None):

    resolved_nik = nik or unique_nik()
    penduduk, _ = Penduduk.objects.update_or_create(
        nik=resolved_nik,
        defaults={
            "nama_lengkap": nama,
            "email": email,
            "rt": rt,
            "kk": kk,
            "tanggal_lahir": timezone.datetime(1990, 1, 1).date(),
            "jenis_kelamin": Penduduk.JenisKelamin.LAKI_LAKI,
            "agama": Penduduk.Agama.ISLAM,
            "no_hp": f"08{resolved_nik[-10:]}"
        }
    )

    akun, _ = Akun.objects.get_or_create(
        penduduk=penduduk,
        defaults={
            "peran": peran,
            "nip": nip,
            "is_staff": staff,
            "is_superuser": superuser,
            "is_active": True
        }
    )

    akun.set_password(DEFAULT_PASSWORD)
    akun.peran = peran
    akun.is_staff = staff
    akun.nip = nip
    akun.is_superuser = superuser
    akun.is_active = True
    akun.save()

    print(
        f"Akun {nama} ({akun.get_peran_display()}) siap: "
        f"NIK={resolved_nik}, email={email}"
    )


# =========================
# MAIN
# =========================

def main():
    seed_jenis_surat()
    rt1, rt2 = seed_wilayah()
    kk1, kk2 = seed_kk(rt1, rt2)

    print("\n=== AKUN ===")

    # =========================
    # ADMIN (FIXED)
    # =========================
    create_dummy_akun(
        nama="Budi Santoso",
        email="budi@example.com",
        peran=Akun.Peran.ADMIN,
        rt=rt1,
        kk=kk1,
        staff=True,
        superuser=True,
        nik="1234567890123456"
    )

    # RT
    for nama, email, nik in (
        ("Ketua RT 1", "rt1@example.com", "2234567890123456"),
        ("Ketua RT 2", "rt2@example.com", "2234567890123457"),
    ):
        create_dummy_akun(
            nama=nama,
            email=email,
            peran=Akun.Peran.RT,
            rt=rt1,
            kk=kk1,
            staff=False,
            superuser=False,
            nik=nik,
        )

    # RW
    for nama, email, nik in (
        ("Ketua RW 1", "rw1@example.com", "3234567890123456"),
        ("Ketua RW 2", "rw2@example.com", "3234567890123457"),
    ):
        create_dummy_akun(
            nama=nama,
            email=email,
            peran=Akun.Peran.RW,
            rt=rt1,
            kk=kk1,
            staff=False,
            superuser=False,
            nik=nik,
        )

    # KADES
    create_dummy_akun(
        nama="Kepala Desa",
        email="kades@example.com",
        peran=Akun.Peran.KEPALA_DESA,
        rt=rt2,
        kk=kk2,
        staff=False,
        superuser=False,
        nik="4234567890123456",
        nip="198709102010011001"
    )

    # WARGA
    for nomor, email, nik in (
        (1, "warga1@example.com", "5234567890123456"),
        (2, "warga2@example.com", "5234567890123457"),
        (3, "warga3@example.com", "5234567890123458"),
        (4, "warga4@example.com", "5234567890123459"),
        (5, "warga5@example.com", "5234567890123460"),
    ):
        create_dummy_akun(
            nama=f"Warga {nomor}",
            email=email,
            peran=Akun.Peran.WARGA,
            rt=rt1,
            kk=kk1,
            staff=False,
            superuser=False,
            nik=nik,
        )

    print("\nSEED SELESAI")


if __name__ == "__main__":
    main()
