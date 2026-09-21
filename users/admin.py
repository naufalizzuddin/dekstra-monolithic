# admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import (
    WilayahRW,
    WilayahRT,
    KartuKeluarga,
    Penduduk,
    Akun,
    PendaftaranAkun,
    OTPEmail,
    JenisSurat,
    PermohonanSurat,
    BerkasPermohonan,
    DokumenSurat,
    RiwayatPersetujuan,
    Notifikasi
)


# =========================================================
# Inline
# =========================================================

class WilayahRTInline(admin.TabularInline):
    model = WilayahRT
    extra = 0


class KartuKeluargaInline(admin.TabularInline):
    model = KartuKeluarga
    extra = 0

class BerkasPermohonanInline(admin.TabularInline):
    model = BerkasPermohonan
    extra = 0
    autocomplete_fields = ("permohonan",)


class RiwayatPersetujuanInline(admin.TabularInline):
    model = RiwayatPersetujuan
    extra = 0
    autocomplete_fields = ("oleh_akun",)
    readonly_fields = ("waktu",)


# =========================================================
# Master Wilayah
# =========================================================

@admin.register(WilayahRW)
class WilayahRWAdmin(admin.ModelAdmin):
    list_display = ("kode_rw", "created_at", "updated_at")
    search_fields = ("kode_rw",)
    ordering = ("kode_rw",)


@admin.register(WilayahRT)
class WilayahRTAdmin(admin.ModelAdmin):
    list_display = ("id", "kode_rt", "rw", "created_at", "updated_at")
    search_fields = ("kode_rt", "rw__kode_rw")
    list_filter = ("rw",)


# =========================================================
# Kependudukan
# =========================================================

@admin.register(KartuKeluarga)
class KartuKeluargaAdmin(admin.ModelAdmin):
    list_display = ("nomor_kk", "rt", "alamat", "created_at", "updated_at")
    search_fields = ("nomor_kk", "alamat", "alamat_detail", "rt__kode_rt", "rt__rw__kode_rw")
    list_filter = ("rt__rw", "rt")
    autocomplete_fields = ("rt",)


@admin.register(Penduduk)
class PendudukAdmin(admin.ModelAdmin):
    list_display = ("nik", "nama_lengkap", "jenis_kelamin", "agama", "email", "no_hp", "status_kependudukan")
    search_fields = ("nik", "nama_lengkap", "email", "no_hp", "agama")
    list_filter = ("jenis_kelamin", "agama", "status_kependudukan")
    ordering = ("nik",)


# =========================================================
# Akun / Auth
# =========================================================

@admin.register(Akun)
class AkunAdmin(DjangoUserAdmin):
    """
    Custom admin untuk Akun (AUTH_USER_MODEL).
    Karena PK-nya NIK (OneToOne ke Penduduk), tampilan adminnya kita rapikan.
    """

    ordering = ("penduduk_id",)
    list_display = ("nik", "nip", "nama_lengkap", "peran", "rt_rw", "is_staff", "terakhir_login_at")
    search_fields = ("penduduk_id", "penduduk__nama_lengkap", "penduduk__email", "penduduk__no_hp")
    list_filter = ("peran", "is_staff")

    autocomplete_fields = ("penduduk",)

    fieldsets = (
        (_("Identitas"), {"fields": ("penduduk", "peran", "nip")}),
        (_("Autentikasi"), {"fields": ("password",)}),
        (_("Hak Akses"), {"fields": ("is_staff", "is_superuser", "groups", "user_permissions")}),
        (_("Aktivitas"), {"fields": ("terakhir_login_at", "last_login")}),
        (_("Waktu"), {"fields": ("created_at", "updated_at")}),
    )

    add_fieldsets = (
        (
            _("Buat Akun"),
            {
                "classes": ("wide",),
                "fields": ("penduduk", "peran", "password1", "password2", "is_staff", "is_superuser"),
            },
        ),
    )

    readonly_fields = ("created_at", "updated_at", "last_login", "terakhir_login_at")

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change=change, **kwargs)
        # custom label untuk RT / RW
        if "rt" in form.base_fields:
            form.base_fields["rt"].label = "RT/RW"
        return form
    
    def nik(self, obj):
        return obj.nik
    nik.short_description = "NIK"

    def nama_lengkap(self, obj):
        return getattr(obj.penduduk, "nama_lengkap", "")
    nama_lengkap.short_description = "Nama"

    def rt_rw(self, obj):
        rt = getattr(obj.penduduk, "rt", None)
        if rt_id := getattr(obj.penduduk, "rt_id", None):
            return f"RT {rt.kode_rt:02d} / RW {rt.rw.kode_rw:02d}"
        return "-"

    def nip(self, obj):
        return getattr(obj, "nip", "")

@admin.register(PendaftaranAkun)
class PendaftaranAkunAdmin(admin.ModelAdmin):
    list_display = (
        "nik",
        "nama_lengkap",
        "nomor_kk",
        "email",
        "rt",
        "status_verifikasi",
        "verified_by",
        "verified_at",
        "created_at",
    )
    search_fields = ("nik", "nama_lengkap", "nomor_kk", "email", "no_hp")
    list_filter = ("status_verifikasi", "rt__rw", "rt")
    autocomplete_fields = ("rt", "verified_by")
    readonly_fields = ("created_at", "updated_at", "verified_at")

@admin.register(OTPEmail)
class OTPEmailAdmin(admin.ModelAdmin):
    list_display = ("akun", "email", "tujuan", "kedaluwarsa_at", "dipakai_at", "created_at")
    search_fields = ("akun__penduduk_id", "akun__penduduk__email")
    list_filter = ("tujuan",)
    autocomplete_fields = ("akun",)
    readonly_fields = ("created_at",)


# =========================================================
# Surat Menyurat
# =========================================================

@admin.register(JenisSurat)
class JenisSuratAdmin(admin.ModelAdmin):
    list_display = ("kode", "nama", "aktif", "created_at", "updated_at")
    search_fields = ("kode", "nama")


@admin.register(PermohonanSurat)
class PermohonanSuratAdmin(admin.ModelAdmin):
    list_display = ("nomor_permohonan", "jenis_surat", "pemohon", "status", "diajukan_at", "selesai_at")
    search_fields = (
        "nomor_permohonan",
        "pemohon__nik",
        "pemohon__nama_lengkap",
        "jenis_surat__kode",
        "jenis_surat__nama",
        "pemohon__rt__kode_rt",
        "pemohon__rt__rw__kode_rw",
    )
    list_filter = ("status", "jenis_surat",)
    autocomplete_fields = ("jenis_surat", "pemohon",)
    inlines = (BerkasPermohonanInline, RiwayatPersetujuanInline,)

    # optional: biar aman log-nya urut
    def get_queryset(self, request):
        return super().get_queryset(request).select_related("jenis_surat", "pemohon", "pemohon__rt", "pemohon__rt__rw")


@admin.register(BerkasPermohonan)
class BerkasPermohonanAdmin(admin.ModelAdmin):
    list_display = ("id", "permohonan", "file_berkas", "diunggah_at")
    search_fields = ("permohonan__nomor_permohonan",)
    autocomplete_fields = ("permohonan",)

    def nama_file(self, obj):
        return obj.file.name
    nama_file.short_description = "File"


@admin.register(DokumenSurat)
class DokumenSuratAdmin(admin.ModelAdmin):
    list_display = ("permohonan", "file_final", "dibuat_at")
    list_select_related = ("permohonan",)
    search_fields = ("permohonan__nomor_permohonan",)
    autocomplete_fields = ("permohonan",)


@admin.register(RiwayatPersetujuan)
class RiwayatPersetujuanAdmin(admin.ModelAdmin):
    list_display = ("permohonan", "tahap", "aksi", "oleh_akun", "waktu")
    search_fields = ("permohonan__nomor_permohonan", "oleh_akun__penduduk_id", "oleh_akun__penduduk__nama_lengkap", "catatan")
    list_filter = ("tahap", "aksi")
    autocomplete_fields = ("permohonan", "oleh_akun")
    readonly_fields = ("waktu",)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "permohonan",
            "oleh_akun",
            "oleh_akun__penduduk",
            "permohonan__pemohon",
            "permohonan__pemohon__rt",
            "permohonan__pemohon__rt__rw",
        )
    
@admin.register(Notifikasi)
class NotifikasiAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "penerima",
        "permohonan",
        "nomor_permohonan",
        "jenis_surat",
        "tipe",
        "judul_preview",
        "sudah_dibaca",
        "dibaca_at",
        "created_at",
    )
    list_filter = (
        "tipe",
        "sudah_dibaca",
        "created_at",
        "dibaca_at",
        "permohonan__jenis_surat",
        "penerima__peran",
    )
    search_fields = (
        "penerima__penduduk__nik",
        "penerima__penduduk__nama_lengkap",
        "permohonan__nomor_permohonan",
        "permohonan__jenis_surat__nama",
        "permohonan__pemohon__nama_lengkap",
    )
    autocomplete_fields = ("penerima", "permohonan")
    readonly_fields = (
        "judul_preview",
        "pesan_preview",
        "created_at",
        "updated_at",
        "dibaca_at",
    )
    fieldsets = (
        ("Data Utama", {
            "fields": (
                "penerima",
                "permohonan",
                "tipe",
                "sudah_dibaca",
                "dibaca_at",
            )
        }),
        ("Preview Template", {
            "fields": (
                "judul_preview",
                "pesan_preview",
            )
        }),
        ("Waktu", {
            "fields": (
                "created_at",
                "updated_at",
            )
        }),
    )
    ordering = ("-created_at",)
    list_select_related = (
        "penerima",
        "penerima__penduduk",
        "permohonan",
        "permohonan__jenis_surat",
        "permohonan__pemohon",
    )

    def nomor_permohonan(self, obj):
        return obj.permohonan.nomor_permohonan
    nomor_permohonan.short_description = "Nomor Permohonan"
    nomor_permohonan.admin_order_field = "permohonan__nomor_permohonan"

    def jenis_surat(self, obj):
        return obj.permohonan.jenis_surat.nama
    jenis_surat.short_description = "Jenis Surat"
    jenis_surat.admin_order_field = "permohonan__jenis_surat__nama"

    def judul_preview(self, obj):
        return obj.judul
    judul_preview.short_description = "Judul"

    def pesan_preview(self, obj):
        return obj.pesan
    pesan_preview.short_description = "Pesan"

    @admin.action(description="Tandai notifikasi terpilih sebagai sudah dibaca")
    def tandai_sudah_dibaca(self, request, queryset):
        from django.utils import timezone
        now = timezone.now()
        queryset.filter(sudah_dibaca=False).update(
            sudah_dibaca=True,
            dibaca_at=now,
            updated_at=now,
        )

    actions = ["tandai_sudah_dibaca"]
