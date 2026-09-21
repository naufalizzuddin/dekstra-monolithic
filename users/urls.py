from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import VerifikasiPendaftaranAkunListView, NotifikasiTandaiDibacaView, NotifikasiListView, WilayahRTListView, WilayahRWListView, LoginJWTView, RegisterJWTView, OTPJWTView, LoginOTPRequestJWTView, OTPRequestJWTView, PengajuanSuratJWTView, BerkasSuratJWTView, RiwayatPersetujuanJWTView, RiwayatPersetujuanListJWTView, RiwayatPengajuanWargaView, RiwayatPengajuanDetailView, RiwayatPersetujuanDetailJWTView, ProfileView, PendaftaranAkunListView, PendaftaranAkunDetailView, DashboardView, DownloadBerkasView, ProtectedRegistrationFileView, ProtectedApplicationFileView

urlpatterns = [
    path("auth/login/", LoginJWTView.as_view()),#untuk login
    path("auth/otp/request/login/", LoginOTPRequestJWTView.as_view()),#untuk request otp login
    path("auth/refresh/", TokenRefreshView.as_view()),#refresh token
    path("auth/register/", RegisterJWTView.as_view()),#untuk buat akun
    path("auth/otp/verify/reset-password/", OTPJWTView.as_view()),#untuk verifikasi reset password
    path("auth/otp/request/reset-password/", OTPRequestJWTView.as_view()),#untuk request reset password

    path("wilayah/rw/", WilayahRWListView.as_view()),#untuk field RW pada form register
    path("wilayah/rt/", WilayahRTListView.as_view()),#untuk field RT pada form register

    path("pengajuan-surat/", PengajuanSuratJWTView.as_view()),#untuk request pengajuan surat
    path('upload/berkas-surat/', BerkasSuratJWTView.as_view()),#untuk upload berkas dari pengajuan surat

    path("riwayat-persetujuan/", RiwayatPersetujuanJWTView.as_view()),
    path("riwayat-persetujuan/list/", RiwayatPersetujuanListJWTView.as_view()),
    path("riwayat-persetujuan/<int:id>/", RiwayatPersetujuanDetailJWTView.as_view()),

    path("riwayat-pengajuan/", RiwayatPengajuanWargaView.as_view()),# History pengajuan milik warga
    path("riwayat-pengajuan/<path:nomor_permohonan>/",RiwayatPengajuanDetailView.as_view()),# Timeline History Pengajuan bagi Warga

    path("pendaftaran-akun/list/", PendaftaranAkunListView.as_view()),#untuk mengambil daftar akun yang perlu diverifikasi
    path("pendaftaran-akun/<int:id>/", PendaftaranAkunDetailView.as_view()),#untuk mengambil detail data tiap akun yang perlu diverifikasi
    path("verifikasi/pendaftaran-akun/<int:id>/", VerifikasiPendaftaranAkunListView.as_view()),#untuk mengubah status pendaftaran yang dilakukan oleh Admin


    path("profil/", ProfileView.as_view(), name="profil"),#untuk mengambil informasi profil

    path("dashboard/", DashboardView.as_view(), name="dashboard"),

    path("berkas/<uuid:token>", DownloadBerkasView.as_view(), name="berkas_final"),
    path(
        "media/pendaftaran/<int:id>/<str:kind>/",
        ProtectedRegistrationFileView.as_view(),
        name="protected-registration-file",
    ),
    path(
        "media/permohonan/<uuid:token>/",
        ProtectedApplicationFileView.as_view(),
        name="protected-application-file",
    ),

    path("notifikasi/", NotifikasiListView.as_view()),
    path("notifikasi/<int:id>/read/", NotifikasiTandaiDibacaView.as_view()),

]
