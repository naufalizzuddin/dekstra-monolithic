from rest_framework import serializers
from django.contrib.auth import authenticate
from django.utils import timezone
from datetime import timedelta
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.hashers import make_password
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.contrib.auth.hashers import check_password, make_password
from django.urls import reverse
from django.conf import settings
from .models import Akun, Penduduk, WilayahRT, WilayahRW, PendaftaranAkun, OTPEmail, generate_otp_hash, PermohonanSurat, BerkasPermohonan, JenisSurat, RiwayatPersetujuan, Notifikasi
from .tasks import kirim_email_otp

class LoginSerializer(serializers.Serializer):
    nik = serializers.CharField(required=False)
    email = serializers.CharField(required=False)
    otp = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        nik = data.get("nik")
        password = data.get("password")
        email = data.get("email")
        otp = data.get("otp")

        if(not(email or nik)):
            raise serializers.ValidationError("Isi field NIK atau EMAIL")

        try:
            if(email):
                akun = Akun.objects.get(penduduk__email=email)
            else:
                penduduk = Penduduk.objects.get(nik=nik)
                akun = Akun.objects.get(penduduk=penduduk)
        except (Penduduk.DoesNotExist, Akun.DoesNotExist):
            raise serializers.ValidationError("Akun tidak ditemukan")

        if not akun.check_password(password):
            raise serializers.ValidationError("Password salah")

        if not akun.is_active:
            raise serializers.ValidationError("Akun nonaktif")

        otp_exist = OTPEmail.objects.filter(akun=akun, tujuan=OTPEmail.Tujuan.LOGIN)

        if not otp_exist.exists():
            raise serializers.ValidationError("OTP tidak ditemukan di akun tersebut")

        otp_valid = False
        for otps in otp_exist:
            if check_password(otp, otps.kode_hash):
                is_load_test_otp = (
                    settings.LOAD_TEST_MODE and otp == settings.LOAD_TEST_OTP
                )
                if otps.kedaluwarsa_at < timezone.now() and not is_load_test_otp:
                    otps.delete()
                    raise serializers.ValidationError("Kode OTP telah kedaluwarsa")
                if not settings.LOAD_TEST_MODE:
                    otps.delete()
                otp_valid = True
                break

        if not otp_valid:
            raise serializers.ValidationError("OTP salah atau tidak ditemukan")

        refresh = RefreshToken.for_user(akun)

        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "peran": akun.peran,
            "nik": akun.nik,
            "email": akun.email,
        }
    
class LoginOTPRequest(serializers.Serializer):
    nik = serializers.CharField(required=False)
    email = serializers.CharField(required=False)
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        nik = data.get("nik")
        password = data.get("password")
        email = data.get("email")

        if(not(email or nik)):
            raise serializers.ValidationError("Isi field NIK atau EMAIL")

        try:
            if(email):
                akun = Akun.objects.get(penduduk__email=email)
            else:
                penduduk = Penduduk.objects.get(nik=nik)
                akun = Akun.objects.get(penduduk=penduduk)
        except (Penduduk.DoesNotExist, Akun.DoesNotExist):
            raise serializers.ValidationError("Akun tidak ditemukan")

        if not akun.check_password(password):
            raise serializers.ValidationError("Password salah")

        if not akun.is_active:
            raise serializers.ValidationError("Akun nonaktif")
        
        if settings.LOAD_TEST_MODE:
            otp = settings.LOAD_TEST_OTP
            otp_hash = make_password(otp)
        else:
            otp, otp_hash = generate_otp_hash()

        OTPEmail.objects.update_or_create(
            akun=akun,
            tujuan=OTPEmail.Tujuan.LOGIN,
            defaults={
                "kode_hash": otp_hash,
                "kedaluwarsa_at": timezone.now() + timedelta(minutes=30),
                "dipakai_at": None,
            },
        )
        kirim_email_otp.delay(
            email=akun.penduduk.email,
            otp=otp,
            tujuan="login",
        )

        response = {"message": "OTP telah dikirim"}
        if settings.OTP_EXPOSE_IN_RESPONSE or settings.LOAD_TEST_MODE:
            response["otp"] = otp
        return response

class OTPRequestSerializer(serializers.Serializer):
    email = serializers.CharField(write_only=True)

    def validate(self, data):
        email = data.get("email")

        # Look for OTP records matching the provided email
        try:
            akun = Akun.objects.get(penduduk__email=email)
        except Akun.DoesNotExist as exc:
            raise serializers.ValidationError(
                "Akun dengan EMAIL tersebut tidak ditemukan"
            ) from exc

        OTPEmail.objects.filter(
            akun=akun,
            tujuan=OTPEmail.Tujuan.RESET_PASSWORD,
        ).delete()
        otp, otp_hash = generate_otp_hash()
        OTPEmail.objects.create(
            akun=akun,
            tujuan=OTPEmail.Tujuan.RESET_PASSWORD,
            kode_hash=otp_hash,
            kedaluwarsa_at=timezone.now() + timedelta(minutes=5),
        )
        kirim_email_otp.delay(
            email=akun.penduduk.email,
            otp=otp,
            tujuan="reset_password",
        )

        return data

class OTPSerializer(serializers.Serializer):
    otp = serializers.CharField(write_only=True)
    email = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, required=False)

    def validate(self, data):
        otp = data.get("otp")
        email = data.get("email")
        password = data.get("new_password")

        # Look for OTP records matching the provided email
        otp_exist = OTPEmail.objects.filter(akun__penduduk__email=email)

        if otp_exist.exists():
            for otps in otp_exist:
                if check_password(otp, otps.kode_hash):
                    if otps.kedaluwarsa_at < timezone.now():
                        otps.delete()
                        raise serializers.ValidationError("Kode OTP telah kedaluwarsa")
                    if otps.tujuan == otps.Tujuan.RESET_PASSWORD:
                        otps.akun.password = make_password(password)
                        otps.akun.save()
                    otps.delete()
                    return data
            raise serializers.ValidationError("OTP tidak valid")
        else:
            raise serializers.ValidationError("Pengguna ini tidak memiliki permintaan OTP")

        return data 

class WilayahRWSerializer(serializers.ModelSerializer):
    class Meta:
        model = WilayahRW
        fields = ["kode_rw"]


class WilayahRTSerializer(serializers.ModelSerializer):
    class Meta:
        model = WilayahRT
        fields = ["id", "kode_rt"]

class RiwayatPersetujuanListSerializer(serializers.ModelSerializer):
    riwayat_aksi = serializers.IntegerField(read_only=True)
    riwayat_tahap = serializers.IntegerField(read_only=True)

    jenis_surat = serializers.SerializerMethodField()
    pemohon = serializers.SerializerMethodField()

    def get_jenis_surat(self, obj):
        return {
            "kode": obj.jenis_surat.kode,
            "nama": obj.jenis_surat.nama,
        }

    def get_pemohon(self, obj):
        return {
            "nik": obj.pemohon.nik,
            "nama": obj.pemohon.nama_lengkap,
        }

    class Meta:
        model = PermohonanSurat
        fields = [
            "id",
            "nomor_permohonan",
            "jenis_surat",
            "pemohon",
            "data",
            "status",
            "diajukan_at",
            "riwayat_aksi",
            "riwayat_tahap",
        ]

# Melihat berkas permohonan untuk verifikasi oleh Backoffice (RT,RW, Admin, dan Kades)
class BerkasPermohonanSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    def get_file_url(self, obj):
        request = self.context.get("request")
        if obj.file_berkas:
            path = reverse(
                "protected-application-file",
                kwargs={"token": obj.public_token},
            )
            return request.build_absolute_uri(path) if request else path
        return None

    class Meta:
        model = BerkasPermohonan
        fields = [
            "id",
            "file_url",
            "diunggah_at",
        ]

# Detail data pengajuan sebagai alat verifikasi oleh Backoffice (RT, RW, Admin, dan Kades)
class RiwayatPersetujuanItemSerializer(serializers.ModelSerializer):
    actor = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    timestamp = serializers.DateTimeField(source="waktu") 

    def get_actor(self, obj):
        if obj.oleh_akun:
            return obj.oleh_akun.get_peran_display()
        return "SYSTEM"

    def get_status(self, obj):
        return obj.get_aksi_display().upper()

    class Meta:
        model = RiwayatPersetujuan
        fields = ["actor", "status", "timestamp", "catatan"]

class RiwayatPersetujuanDetailSerializer(serializers.ModelSerializer):
    riwayat_aksi = serializers.IntegerField(read_only=True)
    riwayat_tahap = serializers.IntegerField(read_only=True)

    jenis_surat = serializers.SerializerMethodField()
    pemohon = serializers.SerializerMethodField()

    berkas = BerkasPermohonanSerializer(many=True, read_only=True)

    riwayat = serializers.SerializerMethodField()

    def get_riwayat(self, obj):
        riwayat = RiwayatPersetujuan.objects.select_related("oleh_akun").filter(
            permohonan=obj,
            aksi=RiwayatPersetujuan.Aksi.SETUJU
        ).order_by("waktu")

        return RiwayatPersetujuanItemSerializer(riwayat, many=True).data

    def get_jenis_surat(self, obj):
        return {
            "kode": obj.jenis_surat.kode,
            "nama": obj.jenis_surat.nama,
        }

    def get_pemohon(self, obj):
        return {
            "nik": obj.pemohon.nik,
            "nama": obj.pemohon.nama_lengkap,
        }

    class Meta:
        model = PermohonanSurat
        fields = [
            "id",
            "nomor_permohonan",
            "jenis_surat",
            "pemohon",
            "data",
            "status",
            "diajukan_at",
            "riwayat_aksi",
            "riwayat_tahap",
            "berkas",
            "riwayat",
        ]

# History pengajuan milik warga   
class RiwayatPengajuanSerializer(serializers.ModelSerializer):
    riwayat_aksi = serializers.IntegerField(read_only=True)
    riwayat_tahap = serializers.IntegerField(read_only=True)

    jenis_surat = serializers.SerializerMethodField()
    public_token = serializers.SerializerMethodField() 

    def get_jenis_surat(self, obj):
        return {
            "kode": obj.jenis_surat.kode,
            "nama": obj.jenis_surat.nama,
        }

    def get_public_token(self, obj):
        if hasattr(obj, "dokumen") and obj.dokumen:
            return str(obj.dokumen.public_token)
        return None

    class Meta:
        model = PermohonanSurat
        fields = [
            "id",
            "nomor_permohonan",
            "jenis_surat",
            "data",
            "status",
            "diajukan_at",
            "riwayat_aksi",
            "riwayat_tahap",
            "public_token",
        ]

# Timeline History Pengajuan bagi Warga
class RiwayatItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = RiwayatPersetujuan
        fields = ["aksi", "created_at", "catatan"]

class RiwayatPengajuanDetailSerializer(serializers.ModelSerializer):
    jenis_surat = serializers.SerializerMethodField()
    riwayat = serializers.SerializerMethodField()
    dokumen_token = serializers.SerializerMethodField()

    def get_jenis_surat(self, obj):
        return {
            "kode": obj.jenis_surat.kode,
            "nama": obj.jenis_surat.nama,
        }

    def get_riwayat(self, obj):
        riwayat_qs = obj.riwayat.exclude(
            aksi=RiwayatPersetujuan.Aksi.AJUKAN,
            tahap__in=[
                RiwayatPersetujuan.Tahap.RW,
                RiwayatPersetujuan.Tahap.ADMIN,
                RiwayatPersetujuan.Tahap.KEPALA_DESA
            ]
        ).order_by("waktu")

        return [
            {
                "status": item.get_aksi_display(),
                "timestamp": item.waktu,
                "description": item.catatan or "-",
                "actor": item.get_tahap_display(),
            }
            for item in riwayat_qs
        ]

    def get_dokumen_token(self, obj):
        if hasattr(obj, "dokumen") and obj.dokumen:
            return str(obj.dokumen.public_token)
        return None

    class Meta:
        model = PermohonanSurat
        fields = [
            "id",
            "nomor_permohonan",
            "jenis_surat",
            "status",
            "diajukan_at",
            "riwayat",
            "dokumen_token",
        ]

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, min_length=8)
    rt = serializers.IntegerField(write_only=True)
    rw = serializers.IntegerField(write_only=True)

    class Meta:
        model = PendaftaranAkun
        fields = [
            "id",
            "nomor_kk",
            "nik",
            "nama_lengkap",
            "tempat_lahir",
            "tanggal_lahir",
            "jenis_kelamin",
            "agama",
            "rt",
            "rw",
            "alamat",
            "email",
            "no_hp",
            "password",
            "kk_file",
            "ktp_file",
            "status_verifikasi",
            "verified_by",
            "verified_at",
        ]
        read_only_fields = ["id", "status_verifikasi", "verified_by", "verified_at"]
        extra_kwargs = {
            "nik": {
                "validators": [],
            },
            "email": {
                "validators": [],  
            },
        }

    def validate_rt(self, value):
        rw = self.initial_data.get("rw")
        try:
            rt = WilayahRT.objects.get(rw=rw)
        except WilayahRT.DoesNotExist:
            raise serializers.ValidationError("RT tidak ditemukan.")
        return value

    def validate_email(self, value):    
        if Penduduk.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email sudah terdaftar")
        if PendaftaranAkun.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email sedang ditinjau pada pendaftaran.")
        return value

    def validate_nik(self, value):
        if Penduduk.objects.filter(nik=value).exists():
            raise serializers.ValidationError("NIK sudah terdaftar")
        if PendaftaranAkun.objects.filter(nik=value).exists():
            raise serializers.ValidationError("NIK sedang ditinjau pada pendaftaran.")
        return value

    def validate_nomor_kk(self, value):
        # optional: ensure format or uniqueness
        return value

    def create(self, validated_data):
        rt_id = validated_data.pop("rt")
        password_plain = validated_data.pop("password")
        validated_data.pop("rw")#tidak disimpan

        try:#ubah tipe data dari int ke wilayah rt
            rt_instance = WilayahRT.objects.get(id=rt_id)
        except WilayahRT.DoesNotExist:
            raise serializers.ValidationError({"rt": "RT tidak ditemukan."})

        # hash password (use make_password for Django hash format)
        validated_data["password_hash"] = make_password(password_plain)
        validated_data["rt"] = rt_instance
        # default status is handled by model, but enforce it anyway
        validated_data.setdefault("status_verifikasi", PendaftaranAkun.StatusVerifikasi.DITINJAU)
        instance = PendaftaranAkun.objects.create(**validated_data)
        return instance

class BerkasSuratSerializer(serializers.ModelSerializer):
    nomor_permohonan = serializers.CharField(write_only=True)

    class Meta:
        model = BerkasPermohonan
        fields = ["id", "file_berkas", "diunggah_at", "nomor_permohonan"]
        read_only_fields = ["id", "diunggah_at"]

    def create(self, validated_data):
        permohonan_nomor = validated_data.pop('nomor_permohonan')

        try:
            permohonan = PermohonanSurat.objects.get(nomor_permohonan=permohonan_nomor)
        except:
             raise serializers.ValidationError({
                "nomor_permohonan": "nomor permohonan tidak ditemukan"
            })

        validated_data["permohonan"] = permohonan           
        return super().create(validated_data)

class RiwayatPersetujuanSerializer(serializers.ModelSerializer):
    nomor_permohonan = serializers.CharField(write_only=True)

    class Meta:
        model = RiwayatPersetujuan
        fields = ["id", "tahap", "aksi", "waktu", "catatan", "nomor_permohonan", "oleh_akun"]
        read_only_fields = ["id", "waktu", "tahap", "oleh_akun"]

    def create(self, validated_data):
        permohonan_nomor = validated_data.pop('nomor_permohonan')
        try:
            permohonan = PermohonanSurat.objects.get(nomor_permohonan=permohonan_nomor)
        except:
             raise serializers.ValidationError({
                "nomor_permohonan": "nomor permohonan tidak ditemukan"
            })

        validated_data["permohonan"] = permohonan           
        return super().create(validated_data)

class PermohonanWargaSerializer(serializers.ModelSerializer):
    """Serializer ringan untuk list permohonan milik warga (GET /pengajuan-surat/)."""
    jenis_surat = serializers.SerializerMethodField()

    def get_jenis_surat(self, obj):
        return {"kode": obj.jenis_surat.kode, "nama": obj.jenis_surat.nama}

    class Meta:
        model = PermohonanSurat
        fields = ["id", "nomor_permohonan", "jenis_surat", "status", "diajukan_at"]


class PengajuanSuratSerializer(serializers.ModelSerializer):
    jenis_surat = serializers.CharField(write_only=True)

    class Meta:
        model = PermohonanSurat
        fields = [
            "id",
            "nomor_permohonan",
            "jenis_surat",
            "pemohon",
            "data",
            "status",
            "diajukan_at"
        ]
        
        read_only_fields = ["id", "nomor_permohonan", "pemohon", "status", "diajukan_at"]

    def create(self, validated_data):
        jenis_surat_kode = validated_data.pop("jenis_surat")

        try:
            jenis_surat = JenisSurat.objects.get(kode=jenis_surat_kode)
        except:
             raise serializers.ValidationError({
                "jenis_surat": "Jenis surat tidak ditemukan"
            })

        validated_data["jenis_surat"] = jenis_surat           
        return super().create(validated_data)

class ProfileSerializer(serializers.ModelSerializer):
    nik = serializers.CharField(source="penduduk.nik", read_only=True)
    nomor_kk = serializers.SerializerMethodField()
    nama_lengkap = serializers.CharField(source="penduduk.nama_lengkap", read_only=True)
    jenis_kelamin = serializers.CharField(source="penduduk.get_jenis_kelamin_display", read_only=True)
    tempat_lahir = serializers.CharField(source="penduduk.tempat_lahir", read_only=True)
    tanggal_lahir = serializers.DateField(source="penduduk.tanggal_lahir", read_only=True)
    email = serializers.EmailField(source="penduduk.email", read_only=True)
    nomor_telepon = serializers.CharField(source="penduduk.no_hp", read_only=True)
    peran = serializers.CharField(source="get_peran_display", read_only=True)
    alamat = serializers.SerializerMethodField()
    rt = serializers.SerializerMethodField()
    rw = serializers.SerializerMethodField()

    class Meta:
        model = Akun
        fields = [
            "nik",
            "nomor_kk",
            "nama_lengkap",
            "jenis_kelamin",
            "tempat_lahir",
            "tanggal_lahir",
            "alamat",
            "email",
            "nomor_telepon",
            "peran",
            "rt",
            "rw",
        ]

    def get_nomor_kk(self, obj):
        if obj.penduduk and obj.penduduk.kk:
            return obj.penduduk.kk.nomor_kk
        return None

    def get_alamat(self, obj):
        if obj.penduduk and obj.penduduk.kk and obj.penduduk.kk.alamat:
            return obj.penduduk.kk.alamat
        return None

    def get_rt(self, obj):
        if obj.penduduk and obj.penduduk.rt:
            return obj.penduduk.rt.kode_rt
        return None

    def get_rw(self, obj):
        if obj.penduduk and obj.penduduk.rt and obj.penduduk.rt.rw:
            return obj.penduduk.rt.rw.kode_rw
        return None

# List akun yang perlu diverifikasi Admin
class PendaftaranAkunListSerializer(serializers.ModelSerializer):
    class Meta:
        model = PendaftaranAkun
        fields = [
            "id",
            "nik",
            "nama_lengkap",
            "email",
            "created_at",
            "status_verifikasi",
        ]
        read_only_fields = fields

# Detail data tiap Akun yang perlu Diverifikasi Admin
class PendaftaranAkunDetailSerializer(serializers.ModelSerializer):
    jenis_kelamin_display = serializers.CharField(source="get_jenis_kelamin_display", read_only=True)
    agama_display = serializers.CharField(source="get_agama_display", read_only=True)
    status_verifikasi_display = serializers.CharField(source="get_status_verifikasi_display", read_only=True)

    rt = serializers.StringRelatedField()
    rw = serializers.SerializerMethodField()
    kk_file = serializers.SerializerMethodField()
    ktp_file = serializers.SerializerMethodField()

    def get_rw(self, obj):
        return str(obj.rw) if obj.rw else None

    def _file_url(self, obj, kind):
        field = getattr(obj, f"{kind}_file")
        request = self.context.get("request")
        if not field or not request:
            return None
        path = reverse(
            "protected-registration-file",
            kwargs={"id": obj.id, "kind": kind},
        )
        return request.build_absolute_uri(path)

    def get_kk_file(self, obj):
        return self._file_url(obj, "kk")

    def get_ktp_file(self, obj):
        return self._file_url(obj, "ktp")

    class Meta:
        model = PendaftaranAkun
        fields = [
            "id",
            "nik",
            "nomor_kk",
            "nama_lengkap",
            "tempat_lahir",
            "tanggal_lahir",
            "jenis_kelamin",
            "jenis_kelamin_display",
            "agama",
            "agama_display",
            "alamat",
            "email",
            "no_hp",
            "status_verifikasi",
            "status_verifikasi_display",
            "rt",
            "rw",
            "kk_file",
            "ktp_file",
            "created_at",
        ]

class DashboardSerializer(serializers.Serializer):
    peran = serializers.CharField()
    isi_cards = serializers.DictField()
    progress = serializers.DictField()
    pengajuan_7_hari_terakhir = serializers.ListField()

class NotifikasiSerializer(serializers.ModelSerializer):
    judul = serializers.ReadOnlyField()
    pesan = serializers.ReadOnlyField()

    nomor_permohonan = serializers.CharField(
        source="permohonan.nomor_permohonan",
        read_only=True
    )

    class Meta:
        model = Notifikasi
        fields = [
            "id",
            "tipe",
            "judul",
            "pesan",
            "sudah_dibaca",
            "dibaca_at",
            "created_at",
            "permohonan",
            "nomor_permohonan",
        ]

class VerifikasiPendaftaranSerializer(serializers.Serializer):
    aksi = serializers.IntegerField()

    def validate_aksi(self, value):
        if value not in [0, 1]:
            raise serializers.ValidationError("Aksi harus 0 atau 1")
        return value
