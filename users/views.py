from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, parsers
from rest_framework.throttling import ScopedRateThrottle
from django.utils import timezone
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q, F, Count, Max, OuterRef, Subquery
from django.http import FileResponse
from datetime import timedelta, datetime
from .models import Notifikasi, WilayahRT, WilayahRW, PermohonanSurat, Akun, RiwayatPersetujuan, Akun, PendaftaranAkun, Penduduk, DokumenSurat, BerkasPermohonan
from .serializers import VerifikasiPendaftaranSerializer, WilayahRTSerializer, WilayahRWSerializer, LoginSerializer, RegisterSerializer, OTPSerializer, LoginOTPRequest, OTPSerializer, OTPRequestSerializer, PengajuanSuratSerializer, PermohonanWargaSerializer, BerkasSuratSerializer, RiwayatPersetujuanSerializer, RiwayatPersetujuanListSerializer, RiwayatPengajuanSerializer, RiwayatPengajuanDetailSerializer, RiwayatPersetujuanDetailSerializer, ProfileSerializer, PendaftaranAkunListSerializer, PendaftaranAkunDetailSerializer, DashboardSerializer, NotifikasiSerializer
from django.shortcuts import get_object_or_404
import uuid
import mimetypes


class WilayahRWListView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        queryset = WilayahRW.objects.all().order_by("kode_rw")
        serializer = WilayahRWSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class WilayahRTListView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        rw = request.query_params.get("rw")

        if not rw:
            return Response(
                {"rw": "Parameter rw wajib diisi"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        queryset = WilayahRT.objects.filter(rw__kode_rw=rw).order_by("kode_rt")

        if not queryset.exists():
            return Response(
                {"rt": "RT tidak ditemukan"},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = WilayahRTSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class LoginJWTView(APIView):
    permission_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)
    
class RegisterJWTView(APIView):
    permission_classes = [permissions.AllowAny]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "register"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            obj = serializer.save()
            return Response({"id": obj.id, "nik": obj.nik}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class OTPJWTView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request):
        serializer = OTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            {"message": "Password berhasil diperbarui"},
            status=status.HTTP_200_OK,
        )
    
class OTPRequestJWTView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request):
        serializer = OTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            {"message": "OTP telah dikirim"},
            status=status.HTTP_200_OK,
        )
    
class LoginOTPRequestJWTView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "otp"

    def post(self, request):
        serializer = LoginOTPRequest(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)

class BerkasSuratJWTView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = BerkasSuratSerializer(data=request.data)
        if serializer.is_valid():
            obj = serializer.save()
            return Response({"id": obj.id, "diunggah_at": obj.diunggah_at}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class PengajuanSuratJWTView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        queryset = PermohonanSurat.objects.filter(
            pemohon=request.user.penduduk
        ).order_by('-diajukan_at')
        serializer = PermohonanWargaSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
            serializer = PengajuanSuratSerializer(data=request.data)

            if serializer.is_valid():
                instance = serializer.save(
                    pemohon=request.user.penduduk,
                    status=1,
                    diajukan_at=timezone.now()
                )

                return Response(
                    PengajuanSuratSerializer(instance).data,
                    status=status.HTTP_201_CREATED
                )

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class RiwayatPersetujuanJWTView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
            serializer = RiwayatPersetujuanSerializer(data=request.data)

            if serializer.is_valid():
                instance = serializer.save(
                    oleh_akun=request.user,
                    tahap=1,
                    waktu=timezone.now()
                )

                return Response(
                    RiwayatPersetujuanSerializer(instance).data,
                    status=status.HTTP_201_CREATED
                )

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class RiwayatPersetujuanListJWTView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        latest_riwayat = RiwayatPersetujuan.objects.filter(
            permohonan=OuterRef('pk')
        ).order_by('-waktu')

        queryset = PermohonanSurat.objects.annotate(
            riwayat_aksi=Subquery(latest_riwayat.values('aksi')[:1]),
            riwayat_tahap=Subquery(latest_riwayat.values('tahap')[:1])
        )

        if request.user.peran == Akun.Peran.RT:
            queryset = queryset.filter(
                pemohon__rt=request.user.penduduk.rt,
                riwayat_tahap=RiwayatPersetujuan.Tahap.RT
            )

        elif request.user.peran == Akun.Peran.RW:
            queryset = queryset.filter(
                pemohon__rt__rw=request.user.penduduk.rt.rw,
                riwayat_tahap=RiwayatPersetujuan.Tahap.RW
            )

        elif request.user.peran == Akun.Peran.ADMIN:
            queryset = queryset.filter(
                riwayat_tahap=RiwayatPersetujuan.Tahap.ADMIN
            )

        elif request.user.peran == Akun.Peran.KEPALA_DESA:
            queryset = queryset.filter(
                riwayat_tahap=RiwayatPersetujuan.Tahap.KEPALA_DESA
            )

        else:
            return Response({"message": "Data tidak ditemukan"}, status=204)

        serializer = RiwayatPersetujuanListSerializer(queryset, many=True)
        return Response(serializer.data, status=200)

class RiwayatPersetujuanDetailJWTView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _annotate_latest_riwayat(self, queryset):
        latest_riwayat = RiwayatPersetujuan.objects.filter(
            permohonan=OuterRef('pk')
        ).order_by('-waktu')

        return queryset.annotate(
            riwayat_aksi=Subquery(latest_riwayat.values('aksi')[:1]),
            riwayat_tahap=Subquery(latest_riwayat.values('tahap')[:1])
        )
    
    def get(self, request, id):
        try:
            queryset = PermohonanSurat.objects.select_related(
                "jenis_surat",
                "pemohon"
            ).prefetch_related(
                "berkas"
            )

            queryset = self._annotate_latest_riwayat(queryset)

            if request.user.peran == Akun.Peran.RT:
                queryset = queryset.filter(
                    pemohon__rt=request.user.penduduk.rt,
                    riwayat_tahap=RiwayatPersetujuan.Tahap.RT
                )

            elif request.user.peran == Akun.Peran.RW:
                queryset = queryset.filter(
                    pemohon__rt__rw=request.user.penduduk.rt.rw,
                    riwayat_tahap=RiwayatPersetujuan.Tahap.RW
                )

            elif request.user.peran == Akun.Peran.ADMIN:
                queryset = queryset.filter(
                    riwayat_tahap=RiwayatPersetujuan.Tahap.ADMIN
                )

            elif request.user.peran == Akun.Peran.KEPALA_DESA:
                queryset = queryset.filter(
                    riwayat_tahap=RiwayatPersetujuan.Tahap.KEPALA_DESA
                )

            permohonan = queryset.get(id=id)

            serializer = RiwayatPersetujuanDetailSerializer(
                permohonan,
                context={"request": request}
            )
            return Response(serializer.data, status=200)

        except PermohonanSurat.DoesNotExist:
            return Response({"message": "Data tidak ditemukan"}, status=404)

        except Exception as e:
            return Response({"message": str(e)}, status=500)
    
class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

# List Akun yang perlu diverifikasi Admin
class PendaftaranAkunListView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    
    def get(self, request):
        queryset = PendaftaranAkun.objects.all().order_by('-created_at')
        
        status_filter = request.query_params.get('status')

        if status_filter is not None:
            try:
                status_filter = int(status_filter)
                queryset = queryset.filter(status_verifikasi=status_filter)
            except ValueError:
                pass
        else:
            queryset = queryset.filter(
                status_verifikasi=PendaftaranAkun.StatusVerifikasi.DITINJAU
            )

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)
        
        if page is not None:
            serializer = PendaftaranAkunListSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)
        
        serializer = PendaftaranAkunListSerializer(queryset, many=True)
        return Response(serializer.data)

# Detail data tiap Akun yang perlu Diverifikasi Admin
class PendaftaranAkunDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        try:
            akun = PendaftaranAkun.objects.select_related("rt__rw").get(id=id)

            serializer = PendaftaranAkunDetailSerializer(
                akun,
                context={"request": request}
            )

            return Response(serializer.data, status=200)

        except PendaftaranAkun.DoesNotExist:
            return Response(
                {"message": "Data tidak ditemukan"},
                status=404
            )

class ProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        akun = (
            Akun.objects
            .select_related("penduduk", "penduduk__rt", "penduduk__rt__rw", "penduduk__kk")
            .get(pk=request.user.pk)
        )

        serializer = ProfileSerializer(akun)
        return Response(serializer.data, status=status.HTTP_200_OK)

class DashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = (
            Akun.objects
            .select_related("penduduk", "penduduk__rt", "penduduk__rt__rw")
            .get(pk=request.user.pk)
        )

        today = timezone.localdate()
        start_today = timezone.make_aware(
            datetime.combine(today, datetime.min.time())
        )
        tujuh_hari = [today - timedelta(days=i) for i in range(6, -1, -1)]

        all_riwayat = (
            RiwayatPersetujuan.objects
            .select_related(
                "permohonan",
                "permohonan__pemohon",
                "permohonan__pemohon__rt",
                "permohonan__pemohon__rt__rw",
                "oleh_akun",
            )
        )

        latest_riwayat_ids = (
            RiwayatPersetujuan.objects
            .values("permohonan_id")
            .annotate(last_id=Max("id"))
            .values_list("last_id", flat=True)
        )

        latest_riwayat = (
            RiwayatPersetujuan.objects
            .filter(id__in=latest_riwayat_ids)
            .select_related(
                "permohonan",
                "permohonan__pemohon",
                "permohonan__pemohon__rt",
                "permohonan__pemohon__rt__rw",
                "oleh_akun",
            )
        )

        if user.peran == Akun.Peran.RT:
            data = self._dashboard_rt(
                user=user,
                all_riwayat=all_riwayat,
                latest_riwayat=latest_riwayat,
                tujuh_hari=tujuh_hari,
                start_today=start_today,
            )
        elif user.peran == Akun.Peran.RW:
            data = self._dashboard_rw(
                user=user,
                all_riwayat=all_riwayat,
                latest_riwayat=latest_riwayat,
                tujuh_hari=tujuh_hari,
                start_today=start_today,
            )
        elif user.peran == Akun.Peran.ADMIN:
            data = self._dashboard_admin(
                all_riwayat=all_riwayat,
                latest_riwayat=latest_riwayat,
                tujuh_hari=tujuh_hari,
            )
        elif user.peran == Akun.Peran.KEPALA_DESA:
            data = self._dashboard_kades(
                user=user,
                all_riwayat=all_riwayat,
                latest_riwayat=latest_riwayat,
                tujuh_hari=tujuh_hari,
                start_today=start_today,
            )
        else:
            return Response(
                {"detail": "Role tidak diizinkan."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = DashboardSerializer(data)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def _chart_7_hari(self, permohonan_qs, tanggal_list):
        counts = (
            permohonan_qs
            .filter(
                diajukan_at__date__gte=tanggal_list[0],
                diajukan_at__date__lte=tanggal_list[-1]
            )
            .values("diajukan_at__date")
            .annotate(jumlah=Count("id"))
            .order_by("diajukan_at__date")
        )

        count_map = {
            item["diajukan_at__date"]: item["jumlah"]
            for item in counts
        }

        return [
            {
                "tanggal": str(tanggal),
                "jumlah": count_map.get(tanggal, 0)
            }
            for tanggal in tanggal_list
        ]

    def _progress_dict(self, riwayat_qs, role_name):
        progress = {
            "menunggu_verifikasi_rt": riwayat_qs.filter(
                tahap=RiwayatPersetujuan.Tahap.RT,
                aksi=RiwayatPersetujuan.Aksi.AJUKAN
            ).count(),
            "menunggu_verifikasi_rw": riwayat_qs.filter(
                tahap=RiwayatPersetujuan.Tahap.RW,
                aksi=RiwayatPersetujuan.Aksi.AJUKAN
            ).count(),
            "menunggu_verifikasi_admin": riwayat_qs.filter(
                tahap=RiwayatPersetujuan.Tahap.ADMIN,
                aksi=RiwayatPersetujuan.Aksi.AJUKAN
            ).count(),
            "menunggu_verifikasi_kades": riwayat_qs.filter(
                tahap=RiwayatPersetujuan.Tahap.KEPALA_DESA,
                aksi=RiwayatPersetujuan.Aksi.AJUKAN
            ).count(),
        }

        if role_name == "rt":
            progress["disetujui_rt"] = riwayat_qs.filter(
                tahap=RiwayatPersetujuan.Tahap.RT,
                aksi=RiwayatPersetujuan.Aksi.SETUJU
            ).count()
            progress["ditolak_rt"] = riwayat_qs.filter(
                tahap=RiwayatPersetujuan.Tahap.RT,
                aksi=RiwayatPersetujuan.Aksi.TOLAK
            ).count()

        elif role_name == "rw":
            progress["disetujui_rw"] = riwayat_qs.filter(
                tahap=RiwayatPersetujuan.Tahap.RW,
                aksi=RiwayatPersetujuan.Aksi.SETUJU
            ).count()
            progress["ditolak_rw"] = riwayat_qs.filter(
                tahap=RiwayatPersetujuan.Tahap.RW,
                aksi=RiwayatPersetujuan.Aksi.TOLAK
            ).count()

        elif role_name == "admin":
            progress["disetujui_admin"] = riwayat_qs.filter(
                tahap=RiwayatPersetujuan.Tahap.ADMIN,
                aksi=RiwayatPersetujuan.Aksi.SETUJU
            ).count()
            progress["ditolak_admin"] = riwayat_qs.filter(
                tahap=RiwayatPersetujuan.Tahap.ADMIN,
                aksi=RiwayatPersetujuan.Aksi.TOLAK
            ).count()

        elif role_name == "kades":
            progress["disetujui_kades"] = riwayat_qs.filter(
                tahap=RiwayatPersetujuan.Tahap.KEPALA_DESA,
                aksi=RiwayatPersetujuan.Aksi.SETUJU
            ).count()
            progress["ditolak_kades"] = riwayat_qs.filter(
                tahap=RiwayatPersetujuan.Tahap.KEPALA_DESA,
                aksi=RiwayatPersetujuan.Aksi.TOLAK
            ).count()

        return progress

    def _dashboard_rt(self, user, all_riwayat, latest_riwayat, tujuh_hari, start_today):
        rt_user = user.penduduk.rt

        wilayah_riwayat = all_riwayat.filter(
            permohonan__pemohon__rt=rt_user
        )
        wilayah_permohonan = PermohonanSurat.objects.filter(
            pemohon__rt=rt_user
        )

        return {
            "peran": "RT",
            "isi_cards": {
                "total_warga_rt": Penduduk.objects.filter(rt=rt_user).count(),
                "menunggu_verifikasi_rt": wilayah_riwayat.filter(
                    tahap=RiwayatPersetujuan.Tahap.RT,
                    aksi=RiwayatPersetujuan.Aksi.AJUKAN
                ).count(),
                "disetujui_hari_ini_rt": RiwayatPersetujuan.objects.filter(
                    oleh_akun=user,
                    tahap=RiwayatPersetujuan.Tahap.RT,
                    aksi=RiwayatPersetujuan.Aksi.SETUJU,
                    waktu__gte=start_today
                ).count(),
            },
            "progress": self._progress_dict(wilayah_riwayat, "rt"),
            "pengajuan_7_hari_terakhir": self._chart_7_hari(
                wilayah_permohonan,
                tujuh_hari
            ),
        }

    def _dashboard_rw(self, user, all_riwayat, latest_riwayat, tujuh_hari, start_today):
        rw_user = user.penduduk.rt.rw

        wilayah_riwayat = all_riwayat.filter(
            permohonan__pemohon__rt__rw=rw_user
        )
        wilayah_permohonan = PermohonanSurat.objects.filter(
            pemohon__rt__rw=rw_user
        )

        return {
            "peran": "RW",
            "isi_cards": {
                "total_warga_rw": Penduduk.objects.filter(rt__rw=rw_user).count(),
                "menunggu_verifikasi_rw": wilayah_riwayat.filter(
                    tahap=RiwayatPersetujuan.Tahap.RW,
                    aksi=RiwayatPersetujuan.Aksi.AJUKAN
                ).count(),
                "disetujui_hari_ini_rw": RiwayatPersetujuan.objects.filter(
                    oleh_akun=user,
                    tahap=RiwayatPersetujuan.Tahap.RW,
                    aksi=RiwayatPersetujuan.Aksi.SETUJU,
                    waktu__gte=start_today
                ).count(),
            },
            "progress": self._progress_dict(wilayah_riwayat, "rw"),
            "pengajuan_7_hari_terakhir": self._chart_7_hari(
                wilayah_permohonan,
                tujuh_hari
            ),
        }

    def _dashboard_admin(self, all_riwayat, latest_riwayat, tujuh_hari):
        wilayah_riwayat = all_riwayat
        wilayah_permohonan = PermohonanSurat.objects.all()

        return {
            "peran": "Admin",
            "isi_cards": {
                "total_data_penduduk": Penduduk.objects.count(),
                "pendaftaran_perlu_verifikasi": PendaftaranAkun.objects.filter(
                    status_verifikasi=PendaftaranAkun.StatusVerifikasi.DITINJAU
                ).count(),
                "surat_perlu_verifikasi": wilayah_riwayat.filter(
                    tahap=RiwayatPersetujuan.Tahap.ADMIN,
                    aksi=RiwayatPersetujuan.Aksi.AJUKAN
                ).count(),
            },
            "progress": self._progress_dict(wilayah_riwayat, "admin"),
            "pengajuan_7_hari_terakhir": self._chart_7_hari(
                wilayah_permohonan,
                tujuh_hari
            ),
        }

    def _dashboard_kades(self, user, all_riwayat, latest_riwayat, tujuh_hari, start_today):
        wilayah_riwayat = all_riwayat
        wilayah_permohonan = PermohonanSurat.objects.all()

        return {
            "peran": "Kepala Desa",
            "isi_cards": {
                "total_warga_desa": Penduduk.objects.count(),
                "menunggu_verifikasi_kades": wilayah_riwayat.filter(
                    tahap=RiwayatPersetujuan.Tahap.KEPALA_DESA,
                    aksi=RiwayatPersetujuan.Aksi.AJUKAN
                ).count(),
                "disetujui_hari_ini_kades": RiwayatPersetujuan.objects.filter(
                    oleh_akun=user,
                    tahap=RiwayatPersetujuan.Tahap.KEPALA_DESA,
                    aksi=RiwayatPersetujuan.Aksi.SETUJU,
                    waktu__gte=start_today
                ).count(),
            },
            "progress": self._progress_dict(wilayah_riwayat, "kades"),
            "pengajuan_7_hari_terakhir": self._chart_7_hari(
                wilayah_permohonan,
                tujuh_hari
            ),
        }
    
# History pengajuan mili warga   
class RiwayatPengajuanWargaView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _annotate_latest(self, queryset):
        latest = RiwayatPersetujuan.objects.filter(
            permohonan=OuterRef('pk')
        ).order_by('-waktu')

        return queryset.annotate(
            riwayat_aksi=Subquery(latest.values('aksi')[:1]),
            riwayat_tahap=Subquery(latest.values('tahap')[:1])
        )

    def get(self, request):
        try:
            latest_riwayat = RiwayatPersetujuan.objects.filter(
                permohonan=OuterRef('pk')
            ).order_by('-waktu')

            queryset = (
                PermohonanSurat.objects
                .filter(pemohon=request.user.penduduk)
                .annotate(
                    riwayat_aksi=Subquery(latest_riwayat.values('aksi')[:1]),
                    riwayat_tahap=Subquery(latest_riwayat.values('tahap')[:1])
                )
                .order_by("-diajukan_at")
            )

            serializer = RiwayatPengajuanSerializer(queryset, many=True)

            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {"message": "Terjadi kesalahan server"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

# Timeline History Pengajuan bagi Warga
class RiwayatPengajuanDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, nomor_permohonan):
        permohonan = (
            PermohonanSurat.objects
            .filter(
                pemohon=request.user.penduduk,
                nomor_permohonan=nomor_permohonan
            )
            .select_related("jenis_surat")
            .prefetch_related("riwayat")  
            .first()
        )

        if not permohonan:
            return Response(
                {"message": "Data tidak ditemukan"},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = RiwayatPengajuanDetailSerializer(permohonan)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
class DownloadBerkasView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def get(self, request, token):
        doc = get_object_or_404(DokumenSurat, public_token=token)
        if not doc.file_final:
            return Response(
                {"detail": "Dokumen belum tersedia."},
                status=status.HTTP_404_NOT_FOUND
            )
        response = FileResponse(doc.file_final.open())
        response["Cache-Control"] = "private, no-store"
        return response


def _file_response(field):
    content_type, _ = mimetypes.guess_type(field.name)
    response = FileResponse(
        field.open("rb"),
        content_type=content_type or "application/octet-stream",
        filename=field.name.rsplit("/", 1)[-1],
    )
    response["Cache-Control"] = "private, no-store"
    return response


class ProtectedRegistrationFileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id, kind):
        if request.user.peran != Akun.Peran.ADMIN and not request.user.is_staff:
            return Response(
                {"detail": "Anda tidak memiliki akses ke berkas ini."},
                status=status.HTTP_403_FORBIDDEN,
            )

        registration = get_object_or_404(PendaftaranAkun, id=id)
        field = {
            "kk": registration.kk_file,
            "ktp": registration.ktp_file,
        }.get(kind)
        if not field:
            return Response(
                {"detail": "Berkas tidak ditemukan."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return _file_response(field)


class ProtectedApplicationFileView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def get(self, request, token):
        attachment = get_object_or_404(
            BerkasPermohonan,
            public_token=token,
        )
        if not attachment.file_berkas:
            return Response(
                {"detail": "Berkas tidak ditemukan."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if not attachment.file_berkas.storage.exists(attachment.file_berkas.name):
            return Response(
                {"detail": "Berkas tidak ditemukan."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return _file_response(attachment.file_berkas)
    
class NotifikasiListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        queryset = Notifikasi.objects.filter(
            penerima=request.user
        ).order_by("-created_at")

        serializer = NotifikasiSerializer(queryset, many=True)
        return Response(serializer.data)
    
class NotifikasiTandaiDibacaView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        notif = get_object_or_404(
            Notifikasi,
            id=id,
            penerima=request.user
        )

        notif.tandai_dibaca()

        return Response({
            "message": "Notifikasi ditandai sebagai dibaca"
        })
    
class VerifikasiPendaftaranAkunListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        notif = get_object_or_404(
            PendaftaranAkun,
            id=id,
        )

        serializer = VerifikasiPendaftaranSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        aksi = serializer.validated_data["aksi"]

        if(notif.status_verifikasi == notif.StatusVerifikasi.DITINJAU):

            if aksi == 1:
                notif.status_verifikasi = notif.StatusVerifikasi.DISETUJUI
                message = "Pendaftaran berhasil disetujui"
            else:
                notif.status_verifikasi = notif.StatusVerifikasi.DITOLAK
                message = "Pendaftaran berhasil ditolak"

            notif.verified_by = request.user
            notif.verified_at = timezone.now()
            notif.save()

        else:
            message = "Status pendaftaran yang telah ditinjau tidak dapat diubah"

        return Response({
            "message": message
        }, status=status.HTTP_200_OK)
