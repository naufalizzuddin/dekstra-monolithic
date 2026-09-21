import os
from django.db import models
from django.utils import timezone
from django.utils.formats import date_format
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator, FileExtensionValidator
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.contrib.auth.hashers import make_password
from django.conf import settings
from datetime import timedelta
from docxtpl import DocxTemplate
from .tasks import generate_surat_pdf, generate_excel_surat
import random, os, uuid

# =========================================================
# Base
# =========================================================

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

# =========================================================
# Filename Configurator
# =========================================================

# Registrasi KK dan KTP
def upload_kk_register_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    tanggal = timezone.now().strftime("%Y-%m-%d")
    waktu = timezone.now().strftime("%H%M%S")
    return f"pendaftaran_akun/kartu_keluarga/{tanggal}/{instance.nik}_{waktu}{ext}"

def upload_ktp_register_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    tanggal = timezone.now().strftime("%Y-%m-%d")
    waktu = timezone.now().strftime("%H%M%S")
    return f"pendaftaran_akun/ktp/{tanggal}/{instance.nik}_{waktu}{ext}"

# Final KK dan KTP
def upload_kk_final_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    return f"dokumen_pendukung/kartu_keluarga/{instance.nomor_kk}{ext}"

def upload_ktp_final_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    return f"dokumen_pendukung/ktp/{instance.nik}{ext}"

# Berkas permohonan dan dokumen final
def upload_berkas_permohonan_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    tanggal = timezone.now().strftime("%Y-%m-%d")
    nik = instance.permohonan.pemohon.nik 
    return f"permohonan/berkas/{tanggal}_{nik}/{filename}"

def upload_dokumen_surat_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    tanggal = timezone.now().strftime("%Y-%m-%d")
    nik = instance.permohonan.pemohon.nik
    return f"permohonan/dokumen_final/{tanggal}_{nik}/{filename}"


# =========================================================
# OTP
# =========================================================

def generate_otp():
    return str(random.randint(100000, 999999))

def generate_otp_hash():
    otp = generate_otp()
    otp_hash = make_password(otp)

    return otp, otp_hash

# =========================================================
# Validator
# =========================================================

digit_16_validator = RegexValidator(
    regex=r'^\d{16}$', 
    message='Nomor tidak valid (16 digit)'
)
image_extension_validator = FileExtensionValidator(
    allowed_extensions=['jpg', 'jpeg', 'png']
)
no_hp_validator = RegexValidator(
    regex=r'^0\d{9,14}$',
    message='Nomor HP harus diawali 0 (bukan +62 atau 62) dan terdiri dari 10-15 digit angka'
)
def tanggal_lahir_validator(value):
    today = timezone.localdate()

    if value >= today:
        raise ValidationError("Tanggal lahir tidak valid")
    
    umur = (today - value).days // 365
    if umur < 17:
        raise ValidationError("Umur minimal 17 tahun (Sudah punya KTP)")


# =========================================================
# KLUSTER 1 — KEPENDUDUKAN
# =========================================================

class WilayahRW(TimeStampedModel):
    kode_rw = models.PositiveSmallIntegerField(primary_key=True)

    class Meta:
        db_table = "wilayah_rw"

    def __str__(self):
        return f"RW {self.kode_rw:02d}"

class WilayahRT(TimeStampedModel):
    id = models.BigAutoField(primary_key=True)
    rw = models.ForeignKey(WilayahRW, on_delete=models.PROTECT, related_name="daftar_rt")
    kode_rt = models.PositiveSmallIntegerField()

    class Meta:
        db_table = "wilayah_rt"
        constraints = [
            models.UniqueConstraint(
                fields=["rw", "kode_rt"], 
                name="uniq_wilayah_rt_per_rw"),
        ]

    def __str__(self):
        return f"RT {self.kode_rt:02d} / RW {self.rw.kode_rw:02d}"

class KartuKeluarga(TimeStampedModel):
    nomor_kk = models.CharField(max_length=16, primary_key=True, validators=[digit_16_validator])
    rt = models.ForeignKey(
        WilayahRT, 
        on_delete=models.PROTECT, 
        related_name="daftar_kk"
    )
    alamat = models.CharField(max_length=255, null=True, blank=True)
    kk_file = models.FileField(
        upload_to=upload_kk_final_path,
        validators=[image_extension_validator],
        null=True,
        blank=True
    )

    class Meta:
        db_table = "kartu_keluarga"

    def __str__(self):
        return f"KK {self.nomor_kk} (RT {self.rt.kode_rt:02d}/RW {self.rt.rw.kode_rw:02d})"


class Penduduk(TimeStampedModel):

    class JenisKelamin(models.IntegerChoices):
        LAKI_LAKI = 1, "Laki-laki"
        PEREMPUAN = 2, "Perempuan"

    class StatusKependudukan(models.IntegerChoices):
        AKTIF = 1, "Aktif"
        PINDAH = 2, "Pindah"
        MENINGGAL = 3, "Meninggal"
        NONAKTIF = 4, "Nonaktif"

    class Agama(models.IntegerChoices):
        ISLAM = 1, "Islam"
        KRISTEN = 2, "Kristen"
        KATOLIK = 3, "Katolik"
        HINDU = 4, "Hindu"
        BUDDHA = 5, "Buddha"
        KONGHUCU = 6, "Konghucu"
        KEPERCAYAAN = 7, "Kepercayaan terhadap Tuhan Yang Maha Esa"

    nik = models.CharField(max_length=16, primary_key=True, validators=[digit_16_validator])
    nama_lengkap = models.CharField(max_length=150)
    tempat_lahir = models.CharField(max_length=80, null=True, blank=True)
    tanggal_lahir = models.DateField(
        null=True, 
        blank=True,
        validators=[tanggal_lahir_validator]
    )
    jenis_kelamin = models.PositiveSmallIntegerField(
        choices=JenisKelamin.choices,
        null=True, 
        blank=True
    )
    agama = models.PositiveSmallIntegerField(
        choices=Agama.choices,
        null=True,
        blank=True,
    )
    email = models.EmailField(max_length=160, unique=True)
    no_hp = models.CharField(
        max_length=32, 
        null=True, 
        blank=True,
        validators=[no_hp_validator]    
    )
    rt = models.ForeignKey(
        WilayahRT,
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name="penduduk"
    )
    kk = models.ForeignKey(
        KartuKeluarga,
        on_delete=models.PROTECT,
        related_name="daftar_penduduk",
        null=True,
        blank=True,
    )
    status_kependudukan = models.PositiveSmallIntegerField(
        choices=StatusKependudukan.choices,
        default=StatusKependudukan.AKTIF
    )
    ktp_file = models.FileField(
        upload_to=upload_ktp_final_path,
        validators=[image_extension_validator],
        null=True,
        blank=True
    )
    class Meta:
        db_table = "penduduk"

    def __str__(self):
        return f"{self.nik} - {self.nama_lengkap}"

# =========================================================
# KLUSTER 2 — LOGIN (PK Akun = NIK) + OTP EMAIL
# =========================================================

class AkunManager(BaseUserManager):
    def create_user(self, penduduk: Penduduk, password=None, **extra_fields):
        if penduduk is None:
            raise ValueError("penduduk wajib diisi (Akun PK mengikuti NIK penduduk).")

        akun = self.model(penduduk=penduduk, **extra_fields)
        if password:
            akun.set_password(password)
        else:
            akun.set_unusable_password()

        akun.save(using=self._db)
        return akun

    def create_superuser(self, penduduk: Penduduk, password=None, **extra_fields):
        extra_fields.setdefault("peran", Akun.Peran.ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(penduduk=penduduk, password=password, **extra_fields)


class Akun(AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    """
    Akun login:
    - PK = NIK (mengikuti penduduk.nik)
    - Set AUTH_USER_MODEL = "<app>.Akun" jika dipakai untuk autentikasi Django
    """

    class Peran(models.IntegerChoices):
        WARGA = 1, "Warga"
        RT = 2, "RT"
        RW = 3, "RW"
        KEPALA_DESA = 4, "Kepala Desa"
        ADMIN = 5, "Admin"

    penduduk = models.OneToOneField(
        Penduduk, 
        on_delete=models.CASCADE, 
        primary_key=True, 
        related_name="akun"
    )

    peran = models.PositiveSmallIntegerField(choices=Peran.choices)

    terakhir_login_at = models.DateTimeField(null=True, blank=True)

    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    nip = models.CharField(max_length=30, null=True, blank=True)

    objects = AkunManager()

    # Catatan: default Django mengharuskan USERNAME_FIELD berupa field pada model.
    # Karena PK kita adalah penduduk (nik), kita gunakan 'penduduk' sebagai identifier.
    # Login pakai input NIK umumnya ditangani di form/backend (mengambil Akun berdasarkan penduduk__nik).
    USERNAME_FIELD = "penduduk"

    class Meta:
        db_table = "akun"
    
    @property
    def nik(self) -> str:
        return self.penduduk_id

    @property
    def nama(self):
        return self.penduduk.nama_lengkap

    @property
    def email(self):
        return self.penduduk.email

    @property
    def rt(self):
        return self.penduduk.rt
    
    @property
    def rw(self):
        return self.penduduk.rt.rw if self.penduduk.rt_id else None

    def __str__(self):
        return f"{self.nik} - {self.nama} - {self.email} - {self.get_peran_display()}"

    def save(self, *args, **kwargs):
        if self.peran != self.Peran.KEPALA_DESA:
            self.nip = None  # paksa kosong kalau bukan kepdes
        super().save(*args, **kwargs)

class PendaftaranAkun(TimeStampedModel):

    class StatusVerifikasi(models.IntegerChoices):
        DITINJAU = 1, "Ditinjau"
        DITOLAK = 2, "Ditolak"
        DISETUJUI = 3, "Disetujui"

    class JenisKelamin(models.IntegerChoices):
        LAKI_LAKI = 1, "Laki-laki"
        PEREMPUAN = 2, "Perempuan"

    class Agama(models.IntegerChoices):
        ISLAM = 1, "Islam"
        KRISTEN = 2, "Kristen"
        KATOLIK = 3, "Katolik"
        HINDU = 4, "Hindu"
        BUDDHA = 5, "Buddha"
        KONGHUCU = 6, "Konghucu"
        KEPERCAYAAN = 7, "Kepercayaan terhadap Tuhan Yang Maha Esa"

    id = models.BigAutoField(primary_key=True)

    nomor_kk = models.CharField(max_length=16, validators=[digit_16_validator])
    nik = models.CharField(max_length=16, unique=True, validators=[digit_16_validator])
    nama_lengkap = models.CharField(max_length=150)
    tempat_lahir = models.CharField(max_length=100)
    tanggal_lahir = models.DateField(
        validators=[tanggal_lahir_validator]
    )
    jenis_kelamin = models.PositiveSmallIntegerField(choices=JenisKelamin.choices)
    agama = models.PositiveSmallIntegerField(
        choices=Agama.choices,
        null=True,
        blank=True,
    )
    rt = models.ForeignKey(
        WilayahRT,
        on_delete=models.PROTECT,
        related_name="pendaftaran_akun"
    )

    alamat = models.CharField(max_length=255)
    email = models.EmailField(max_length=160, unique=True)
    no_hp = models.CharField(max_length=32, validators=[no_hp_validator])

    password_hash = models.CharField(max_length=255)

    kk_file = models.FileField(
        validators=[image_extension_validator],
        upload_to=upload_kk_register_path,
        null=True,
        blank=True
    )
    ktp_file = models.FileField(
        validators=[image_extension_validator],
        upload_to=upload_ktp_register_path,
        null=True,
        blank=True
    )
    status_verifikasi = models.PositiveSmallIntegerField(
        choices=StatusVerifikasi.choices,
        default=StatusVerifikasi.DITINJAU
    )
    verified_by = models.ForeignKey(
        "Akun",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pendaftaran_diverifikasi"
    )
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "pendaftaran_akun"
        indexes = [
            models.Index(fields=["status_verifikasi"], name="idx_pendaftaran_status"),
            models.Index(fields=["nik"], name="idx_pendaftaran_nik"),
            models.Index(fields=["nomor_kk"], name="idx_pendaftaran_kk"),
        ]

    @property
    def rw(self):
        return self.rt.rw if self.rt_id else None        

    def __str__(self):
        return f"{self.nik} - {self.nama_lengkap} ({self.get_status_verifikasi_display()})"

@receiver(post_save, sender=PendaftaranAkun)
def process_instance_on_disetujui(sender, instance, created, **kwargs):
    if instance.status_verifikasi == PendaftaranAkun.StatusVerifikasi.DISETUJUI:
        #simpan kk
        if KartuKeluarga.objects.filter(nomor_kk=instance.nomor_kk).exists():
            kk_user = KartuKeluarga.objects.get(nomor_kk=instance.nomor_kk)
        else:
            kk_user = KartuKeluarga.objects.create(
                nomor_kk = instance.nomor_kk,
                rt = instance.rt,
                alamat = instance.alamat,
                kk_file = instance.kk_file
            )
        #simpan ke penduduk
        penduduk_user = Penduduk.objects.create(
            nik = instance.nik,
            nama_lengkap = instance.nama_lengkap,
            tanggal_lahir = instance.tanggal_lahir,
            tempat_lahir = instance.tempat_lahir,
            jenis_kelamin = instance.jenis_kelamin,
            agama = instance.agama,
            rt = instance.rt,
            email = instance.email,
            no_hp = instance.no_hp,
            ktp_file = instance.ktp_file,
            kk = kk_user
        )
        Akun.objects.create(
            penduduk = penduduk_user,
            peran = Akun.Peran.WARGA,#default peran adalah warga
            password = instance.password_hash
        )
        #simpan ke akun sambungkan dengan penduduk
        #simpan kk dan sambungkan dengan akun
        # instance.delete()

    # if instance.status_verifikasi == PendaftaranAkun.StatusVerifikasi.DITOLAK:
    #     instance.delete()

@receiver(pre_delete, sender=PendaftaranAkun)
def send_email_before_delete(sender, instance, **kwargs):
    if instance.status_verifikasi == PendaftaranAkun.StatusVerifikasi.DISETUJUI:
        #tambahkan notifikasi email untuk akun disetujui dan OTP
        otp, otp_hash = generate_otp_hash()#kirim otp
        print("otp : " + otp)#hapus
        akun_user = Akun.objects.get(penduduk=instance.nik)
        OTPEmail.objects.update_or_create(
            akun=akun_user,
            tujuan=OTPEmail.Tujuan.VERIF_EMAIL,
            kode_hash=otp_hash,
            kedaluwarsa_at=timezone.now() + timedelta(minutes=5)
        )
        print("pengajuan pendaftaran akun disetujui")

    if instance.status_verifikasi == PendaftaranAkun.StatusVerifikasi.DITOLAK:
        #tambahkan email untuk notifikasi ditolak
        print("pengajuan pendaftaran akun ditolak")       

class OTPEmail(models.Model):
    id = models.BigAutoField(primary_key=True)

    class Tujuan(models.IntegerChoices):
        LOGIN = 1, "Login"
        RESET_PASSWORD = 2, "Reset Password"

    akun = models.ForeignKey(Akun, on_delete=models.CASCADE, related_name="otp_email")
    tujuan = models.PositiveSmallIntegerField(choices=Tujuan.choices)
    kode_hash = models.CharField(max_length=255)
    kedaluwarsa_at = models.DateTimeField()
    dipakai_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        db_table = "otp_email"
    
    @property
    def email(self):
        return self.akun.email
    
    @property
    def nik(self):
        return self.akun.nik

    def __str__(self):
        return f"OTP {self.tujuan} untuk {self.email} (akun {self.nik})"


# =========================================================
# KLUSTER 3 — PERMOHONAN SURAT + PDF + RIWAYAT PERSETUJUAN + NOTIFIKASI
# =========================================================

class JenisSurat(TimeStampedModel):

    def validate_template(value):
        ext = os.path.splitext(value.name)[1].lower()
        allowed_extensions = [".docx", ".xlsx"]
        if ext not in allowed_extensions:
            raise ValidationError("Template yang anda masukkan tidak sesuai kriteria")
        
    id = models.BigAutoField(primary_key=True)
    kode = models.CharField(max_length=20, unique=True)
    nama = models.CharField(max_length=120)
    deskripsi = models.TextField(null=True, blank=True)
    aktif = models.BooleanField(default=True)
    template_file = models.FileField(
        upload_to="template_surat/",
        validators=[validate_template],
        null=True,
        blank=True
    )

    class Meta:
        db_table = "jenis_surat"

    def __str__(self):
        return f"{self.kode} - {self.nama}"


class PermohonanSurat(TimeStampedModel):
    id = models.BigAutoField(primary_key=True)

    class Status(models.IntegerChoices):
        DIAJUKAN = 1, "Diajukan"
        DITOLAK = 2, "Ditolak"
        SELESAI = 3, "Selesai"

    nomor_permohonan = models.CharField(max_length=50, unique=True, blank=True)
    jenis_surat = models.ForeignKey(JenisSurat, on_delete=models.PROTECT, related_name="permohonan")
    pemohon = models.ForeignKey(Penduduk, on_delete=models.PROTECT, related_name="permohonan_surat")
    status = models.PositiveSmallIntegerField(choices=Status.choices)
    data = models.JSONField(default=dict)

    diajukan_at = models.DateTimeField(null=True, blank=True)
    selesai_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "permohonan_surat"

    def save(self, *args, **kwargs):
        should_generate_nomor = not self.nomor_permohonan
        if should_generate_nomor:
            self.nomor_permohonan = f"PENDING/{uuid.uuid4().hex}"

        super().save(*args, **kwargs)  # save first to get ID
        is_new = not RiwayatPersetujuan.objects.filter(
            permohonan=self
        ).exists()#cek apakah sudah pernah dibuat

        if should_generate_nomor:
            now = timezone.localtime()
            self.nomor_permohonan = f"{now:%Y}/{now:%m}/{self.jenis_surat.kode}/{self.id}"
            super().save(update_fields=["nomor_permohonan"])

        # ✅ hanya saat pertama kali dibuat
        if is_new:
            # cari akun RT sesuai wilayah pemohon
            akun_rt = Akun.objects.filter(
                peran=Akun.Peran.RT,
                penduduk__rt=self.pemohon.rt
            ).first()
            
            penerima = Akun.objects.get(penduduk=self.pemohon)
            Notifikasi.objects.create(penerima=penerima, 
                                      permohonan=self, 
                                      tipe=Notifikasi.Tipe.PENGAJUAN_BARU,
                                      )

            if akun_rt:
                RiwayatPersetujuan.objects.create(
                    permohonan=self,
                    tahap=RiwayatPersetujuan.Tahap.RT,
                    aksi=RiwayatPersetujuan.Aksi.AJUKAN,
                    oleh_akun=akun_rt
                )

        if self.status == self.Status.SELESAI:
            ext = os.path.splitext(self.jenis_surat.template_file.name)[1].lower()

            if ext == ".xlsx":
                generate_excel_surat.delay(self.id)

            elif ext == ".docx":
                generate_surat_pdf.delay(self.id)


    @property
    def rt(self):
        return self.pemohon.rt
    
    @property
    def rw(self):
        return self.pemohon.rt.rw if self.pemohon.rt_id else None

    def __str__(self):
        return f"{self.nomor_permohonan} ({self.jenis_surat.kode})"


class BerkasPermohonan(models.Model):
    id = models.BigAutoField(primary_key=True)
    public_token = models.UUIDField(default=uuid.uuid4, unique=True)
    permohonan = models.ForeignKey(PermohonanSurat, on_delete=models.CASCADE, related_name="berkas")
    file_berkas = models.FileField(upload_to=upload_berkas_permohonan_path)
    diunggah_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "berkas_permohonan"

    def __str__(self):
        return f"Berkas untuk {self.permohonan.nomor_permohonan}"


class DokumenSurat(models.Model):
    id = models.BigAutoField(primary_key=True)
    public_token = models.UUIDField(default=uuid.uuid4, unique=True)
    permohonan = models.OneToOneField(PermohonanSurat, on_delete=models.CASCADE, related_name="dokumen")
    file_final = models.FileField(upload_to=upload_dokumen_surat_path)
    dibuat_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "dokumen_surat"

    def __str__(self):
        return f"Dokumen {self.permohonan.nomor_permohonan}"


class RiwayatPersetujuan(models.Model):

    id = models.BigAutoField(primary_key=True)

    class Tahap(models.IntegerChoices):
        RT = 1, "RT"
        RW = 2, "RW"
        ADMIN = 3, "ADMIN"
        KEPALA_DESA = 4, "Kepala Desa"

    class Aksi(models.IntegerChoices):
        AJUKAN = 1, "Ajukan"
        SETUJU = 2, "Setuju"
        TOLAK = 3, "Tolak"

    permohonan = models.ForeignKey(PermohonanSurat, on_delete=models.CASCADE, related_name="riwayat")
    tahap = models.PositiveSmallIntegerField(choices=Tahap.choices)
    aksi = models.PositiveSmallIntegerField(choices=Aksi.choices)
    catatan = models.TextField(null=True, blank=True)
    oleh_akun = models.ForeignKey(Akun, on_delete=models.SET_NULL, null=True, blank=True, related_name="aksi_riwayat")
    waktu = models.DateTimeField(default=timezone.now)
    akun = None

    class Meta:
        db_table = "riwayat_persetujuan"
        indexes = [
            models.Index(fields=["permohonan", "-waktu"], name="idx_riwayat_perm_waktu"),
            models.Index(fields=["tahap", "aksi"], name="idx_riwayat_tahap_aksi"),
        ]
    
    def _tahap_dari_akun(self) -> int:
        if not self.oleh_akun:
            raise ValidationError({"oleh_akun": "Akun pelaku harus diisi."})

        peran = self.oleh_akun.peran
        #tambahkan buat objek baru dengan status diajukan untuk setiap
        if peran == Akun.Peran.RT:
            return self.Tahap.RT
        if peran == Akun.Peran.RW:
            return self.Tahap.RW
        if peran == Akun.Peran.ADMIN:
            return self.Tahap.ADMIN
        if peran == Akun.Peran.KEPALA_DESA:
            return self.Tahap.KEPALA_DESA

        raise ValidationError({"oleh_akun": "Peran akun tidak valid."})

    def _next_tahap(self):
        mapping = {
            self.Tahap.RT: self.Tahap.RW,
            self.Tahap.RW: self.Tahap.ADMIN,
            self.Tahap.ADMIN: self.Tahap.KEPALA_DESA,
        }
        return mapping.get(self.tahap, None)

    def clean(self):
        super().clean()
        self.tahap = self._tahap_dari_akun()

    def save(self, *args, **kwargs):
        self.full_clean()
        is_new = self.pk is None

        super().save(*args, **kwargs)

        # hanya trigger jika:
        # 1. aksi SETUJU
        # 2. bukan create awal AJUKAN
        if self.aksi == self.Aksi.SETUJU:
            penerima = Akun.objects.get(penduduk=self.permohonan.pemohon)
            if self.tahap == self.Tahap.KEPALA_DESA:
                #ubah permohonan menjadi selesai ketika disetujui kepdes
                self.permohonan.status = self.permohonan.Status.SELESAI
                self.permohonan.save()
                Notifikasi.objects.create(penerima=penerima, 
                                        permohonan=self.permohonan, 
                                        tipe=Notifikasi.Tipe.SELESAI,
                                        )

            next_tahap = self._next_tahap()

            if next_tahap:
                # cek apakah sudah ada tahap berikutnya
                exists = RiwayatPersetujuan.objects.filter(
                    permohonan=self.permohonan,
                    tahap=next_tahap
                ).exists()

                if(next_tahap == self.Tahap.RW):
                    self.akun = Akun.objects.filter(
                        peran=Akun.Peran.RW,
                        penduduk__rt__rw=self.oleh_akun.rt.rw,
                    ).order_by("penduduk_id").first()
                    Notifikasi.objects.create(penerima=penerima, 
                                            permohonan=self.permohonan, 
                                            tipe=Notifikasi.Tipe.VERIFIKASI_RW,
                                            )  
                elif(next_tahap == self.Tahap.ADMIN):
                    self.akun = Akun.objects.filter(
                        peran=Akun.Peran.ADMIN
                    ).order_by("penduduk_id").first()
                    Notifikasi.objects.create(penerima=penerima, 
                                            permohonan=self.permohonan, 
                                            tipe=Notifikasi.Tipe.VERIFIKASI_ADMIN,
                                            )  
                elif(next_tahap == self.Tahap.KEPALA_DESA):
                    self.akun = Akun.objects.filter(
                        peran=Akun.Peran.KEPALA_DESA
                    ).order_by("penduduk_id").first()
                    Notifikasi.objects.create(penerima=penerima, 
                                            permohonan=self.permohonan, 
                                            tipe=Notifikasi.Tipe.VERIFIKASI_KEPALA_DESA,
                                            )

                if not exists and self.akun != None:
                    RiwayatPersetujuan.objects.create(
                        permohonan=self.permohonan,
                        tahap=next_tahap,
                        aksi=self.Aksi.AJUKAN,
                        oleh_akun=self.akun
                    )


        if self.aksi == self.Aksi.TOLAK:
            #ditolak oleh siapapun akan mengubah status ditolak
            self.permohonan.status = self.permohonan.Status.DITOLAK
            self.permohonan.save()


    def __str__(self):
        return f"{self.permohonan.nomor_permohonan} - {self.get_tahap_display()} - {self.get_aksi_display()} @ {self.waktu}"

class Notifikasi(TimeStampedModel):

    class Tipe(models.IntegerChoices):
        PENGAJUAN_BARU = 1, "Pengajuan Baru"
        VERIFIKASI_RT = 2, "Verifikasi RT"
        VERIFIKASI_RW = 3, "Verifikasi RW"
        VERIFIKASI_ADMIN = 4, "Verifikasi Admin"
        VERIFIKASI_KEPALA_DESA = 5, "Verifikasi Kepala Desa"
        DITOLAK = 6, "Ditolak"
        SELESAI = 7, "Selesai"

    TEMPLATE = {
        Tipe.PENGAJUAN_BARU: {
            "judul": "Pengajuan Surat Baru",
            "pesan": "Permohonan {jenis_surat} telah diajukan."
        },
        Tipe.VERIFIKASI_RT: {
            "judul": "Permohonan Sedang Diverifikasi RT",
            "pesan": "Permohonan {jenis_surat} sedang diverifikasi RT"
        },
        Tipe.VERIFIKASI_RW: {
            "judul": "Permohonan Sedang Diverifikasi RW",
            "pesan": "Permohonan {jenis_surat} sedang diverifikasi RW."
        },
        Tipe.VERIFIKASI_ADMIN: {
            "judul": "Permohonan Sedang Diverifikasi Admin",
            "pesan": "Permohonan {jenis_surat} sedang diverifikasi Admin."
        },
        Tipe.VERIFIKASI_KEPALA_DESA: {
            "judul": "Permohonan Sedang Diverifikasi Kepala Desa",
            "pesan": "Permohonan {jenis_surat} sedang diverifikasi Kepala Desa."
        },
        Tipe.DITOLAK: {
            "judul": "Permohonan Ditolak",
            "pesan": "Permohonan {jenis_surat} ditolak."
        },
        Tipe.SELESAI: {
            "judul": "Permohonan Selesai",
            "pesan": "Permohonan {jenis_surat} telah selesai diproses, dan dokumen bisa diunduh."
        },
    }

    penerima = models.ForeignKey(
        Akun,
        on_delete=models.CASCADE,
        related_name="notifikasi"
    )

    permohonan = models.ForeignKey(
        PermohonanSurat,
        on_delete=models.CASCADE,
        related_name="notifikasi"
    )

    tipe = models.PositiveSmallIntegerField(choices=Tipe.choices)

    sudah_dibaca = models.BooleanField(default=False)
    dibaca_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "notifikasi"
        indexes = [
            models.Index(fields=["penerima", "sudah_dibaca", "-created_at"], name="idx_notif_user_baca_waktu"),
            models.Index(fields=["permohonan", "-created_at"], name="idx_notif_perm_waktu"),
            models.Index(fields=["tipe"], name="idx_notif_tipe"),
        ]

    def __str__(self):
        return f"Notifikasi {self.id} - {self.penerima.nik} - {self.get_tipe_display()}"

    def get_context(self):
        return {
            "nomor_permohonan": self.permohonan.nomor_permohonan,
            "jenis_surat": self.permohonan.jenis_surat.nama,
            "kode_surat": self.permohonan.jenis_surat.kode,
            "pemohon": self.permohonan.pemohon.nama_lengkap,
            "status": self.permohonan.get_status_display(),
        }

    @property
    def judul(self):
        template = self.TEMPLATE.get(self.tipe, {})
        return template.get("judul", "Notifikasi")

    @property
    def pesan(self):
        template = self.TEMPLATE.get(self.tipe, {})
        raw = template.get("pesan", "Tidak ada pesan.")
        return raw.format(**self.get_context())

    def tandai_dibaca(self):
        if not self.sudah_dibaca:
            self.sudah_dibaca = True
            self.dibaca_at = timezone.now()
            self.save(update_fields=["sudah_dibaca", "dibaca_at", "updated_at"])

    def save(self, *args, **kwargs):
        # jika sudah dibaca tapi belum ada waktu dibaca
        if self.sudah_dibaca and not self.dibaca_at:
            self.dibaca_at = timezone.now()

        super().save(*args, **kwargs)
