from celery import shared_task

@shared_task
def hapus_otp_expired():
    from django.conf import settings
    from django.contrib.auth.hashers import check_password
    from django.utils import timezone
    from users.models import OTPEmail

    qs = OTPEmail.objects.filter(kedaluwarsa_at__lt=timezone.now())
    if settings.LOAD_TEST_MODE:
        expired_ids = []
        for otp in qs.iterator():
            if not check_password(settings.LOAD_TEST_OTP, otp.kode_hash):
                expired_ids.append(otp.id)
        qs = OTPEmail.objects.filter(id__in=expired_ids)

    deleted, _ = qs.delete()
    print("OTP TERHAPUS:", deleted)

    return f"{deleted} OTP dihapus"

@shared_task
def kirim_email_otp(email, otp, tujuan):
    from django.core.mail import EmailMultiAlternatives
    from django.conf import settings

    from_email = settings.EMAIL_HOST_USER
    to = [email]

    # =========================
    # KONDISI OTP
    # =========================
    if tujuan == "login":
        subject = "Kode OTP Login"
        title = "Verifikasi Login"
        message = "Gunakan kode OTP berikut untuk login ke akun Anda."
    
    elif tujuan == "reset_password":
        subject = "Reset Password OTP"
        title = "Reset Password"
        message = "Gunakan kode OTP berikut untuk mengatur ulang password Anda."
    
    else:
        subject = "Kode OTP"
        title = "Verifikasi"
        message = "Gunakan kode OTP berikut."

    text_content = f"{message} OTP: {otp}"

    # =========================
    # TEMPLATE HTML
    # =========================
    html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
        <meta charset="UTF-8">
        <title>{subject}</title>
        </head>
        <body style="margin:0; padding:0; background-color:#f4f6f8; font-family:Arial, sans-serif;">
        <table width="100%" cellspacing="0" cellpadding="0" style="background-color:#f4f6f8; padding:20px;">
            <tr>
            <td align="center">
                
                <table width="100%" max-width="500px" cellspacing="0" cellpadding="0" 
                    style="background:#ffffff; border-radius:12px; padding:30px; box-shadow:0 4px 12px rgba(0,0,0,0.1);">
                
                <!-- Header -->
                <tr>
                    <td align="center" style="padding-bottom:20px;">
                    <h2 style="margin:0; color:#333;">{title}</h2>
                    <p style="margin:5px 0 0; color:#777;">{message}</p>
                    </td>
                </tr>

                <!-- OTP -->
                <tr>
                    <td align="center" style="padding:20px 0;">
                    <div style="
                        display:inline-block;
                        background:#4CAF50;
                        color:#ffffff;
                        font-size:28px;
                        letter-spacing:6px;
                        padding:15px 25px;
                        border-radius:8px;
                        font-weight:bold;">
                        {otp}
                    </div>
                    </td>
                </tr>

                <!-- Info -->
                <tr>
                    <td align="center" style="padding:10px 0;">
                    <p style="color:#555; font-size:14px; margin:0;">
                        Kode ini berlaku selama <b>5 menit</b>.
                    </p>
                    <p style="color:#999; font-size:12px;">
                        Jangan bagikan kode ini ke siapa pun.
                    </p>
                    </td>
                </tr>

                <!-- Divider -->
                <tr>
                    <td style="padding:20px 0;">
                    <hr style="border:none; border-top:1px solid #eee;">
                    </td>
                </tr>

                <!-- Footer -->
                <tr>
                    <td align="center" style="font-size:12px; color:#aaa;">
                    <p style="margin:0;">© 2026 Dekstra App</p>
                    <p style="margin:5px 0 0;">Email ini dikirim otomatis, mohon tidak membalas.</p>
                    </td>
                </tr>

                </table>

            </td>
            </tr>
        </table>
        </body>
        </html>
    """

    email = EmailMultiAlternatives(subject, text_content, from_email, to)
    email.attach_alternative(html_content, "text/html")
    email.send()

@shared_task
def hapus_notifikasi_dibaca():
    from django.utils import timezone
    from users.models import Notifikasi
    from datetime import timedelta

    #hapus setelah 1 hari
    waktu_hapus = timezone.now() - timedelta(days=1)
    qs = Notifikasi.objects.filter(dibaca_at__lt=waktu_hapus)
    deleted, _ = qs.delete()
    print("notifikasi telah terbaca TERHAPUS:", deleted)

    return f"{deleted} notifikasi telah terbaca dihapus"

@shared_task
def hapus_pendaftaran_akun():
    from django.utils import timezone
    from users.models import PendaftaranAkun
    from datetime import timedelta

    #hapus setelah 1 hari
    waktu_hapus = timezone.now() - timedelta(days=2)
    qs = PendaftaranAkun.objects.filter(verified_at__lt=waktu_hapus)
    deleted, _ = qs.delete()
    print("PendaftaranAkun telah terbaca TERHAPUS:", deleted)

    return f"{deleted} PendaftaranAkun telah terbaca dihapus"

@shared_task
def generate_surat_pdf(permohonan_id):
    from django.utils import timezone
    from django.utils.formats import date_format
    from docxtpl import DocxTemplate, InlineImage
    from docx.shared import Mm
    from django.core.files.base import ContentFile
    import io, qrcode, tempfile, os, subprocess, shutil

    from .models import (
        PermohonanSurat,
        DokumenSurat,
        Akun,
        JenisSurat
    )

    # 🔥 cek apakah soffice tersedia di PATH
    if not shutil.which("soffice"):
        raise Exception("LibreOffice (soffice) tidak ditemukan di PATH")

    permohonan = PermohonanSurat.objects.get(id=permohonan_id)
    lokasi_template = JenisSurat.objects.get(kode=permohonan.jenis_surat.kode)

    if "docx" not in lokasi_template.template_file.name:
        return

    doc = DocxTemplate(lokasi_template.template_file.path)
    context = permohonan.data or {}

    kades = Akun.objects.filter(
        peran=Akun.Peran.KEPALA_DESA
    ).order_by("penduduk_id").first()
    if not kades:
        raise ValueError("Akun Kepala Desa belum tersedia")

    context["nama_kades"] = kades.penduduk.nama_lengkap
    context["nip"] = kades.nip
    context["nomor_surat"] = permohonan.nomor_permohonan

    now = timezone.localtime()
    context["signed_at"] = date_format(now, format="j F Y")

    # QR Code
    dokumen, _ = DokumenSurat.objects.get_or_create(permohonan=permohonan)

    qr = qrcode.make(data=dokumen.public_token)
    buffer_qr = io.BytesIO()
    qr.save(buffer_qr, format="PNG")
    buffer_qr.seek(0)

    context["ttd_img"] = InlineImage(
        doc,
        buffer_qr,
        width=Mm(30)
    )

    doc.render(context)

    with tempfile.TemporaryDirectory() as tmpdir:
        docx_path = os.path.join(tmpdir, "temp.docx")

        # simpan docx
        doc.save(docx_path)

        # 🔥 convert pakai soffice (tanpa path)
        result = subprocess.run(
            [
                "soffice",
                f"-env:UserInstallation=file://{tmpdir}/lo-profile",
                "--headless",
                "--nologo",
                "--nolockcheck",
                "--nodefault",
                "--nofirststartwizard",
                "--convert-to", "pdf",
                "--outdir", tmpdir,
                docx_path
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30
        )

        # debug kalau gagal
        if result.returncode != 0:
            raise Exception(
                f"Convert gagal:\nSTDOUT:\n{result.stdout.decode()}\nSTDERR:\n{result.stderr.decode()}"
            )

        pdf_path = os.path.join(tmpdir, "temp.pdf")

        if not os.path.exists(pdf_path):
            raise Exception("PDF tidak terbentuk")

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        file_name = f"surat_{dokumen.public_token}.pdf"

        if dokumen.file_final:
            dokumen.file_final.delete(save=False)

        dokumen.file_final.save(
            file_name,
            ContentFile(pdf_bytes),
            save=True
        )

@shared_task
def generate_excel_surat(permohonan_id):
    from .models import PermohonanSurat, DokumenSurat, Akun
    from django.core.files.base import ContentFile
    from django.utils import timezone
    from .helpers import (
        generate_b01_excel, generate_b02_excel,
        generate_b03_excel, generate_b04_excel,
        generate_b05_excel, generate_b09_excel
    )

    import subprocess
    import tempfile
    import os

    def convert_excel_to_pdf(excel_bytes):
        with tempfile.TemporaryDirectory() as tmpdir:
            xlsx_path = os.path.join(tmpdir, "file.xlsx")

            # simpan excel sementara
            with open(xlsx_path, "wb") as f:
                f.write(excel_bytes)

            # convert ke PDF
            subprocess.run([
                "soffice",
                f"-env:UserInstallation=file://{tmpdir}/lo-profile",
                "--headless",
                "--convert-to", "pdf",
                "--outdir", tmpdir,
                xlsx_path
            ], check=True)

            pdf_path = os.path.join(tmpdir, "file.pdf")

            with open(pdf_path, "rb") as f:
                return f.read()

    # =========================

    permohonan = PermohonanSurat.objects.get(id=permohonan_id)

    lokasi_template = permohonan.jenis_surat
    dokumen, _ = DokumenSurat.objects.get_or_create(permohonan=permohonan)

    kades = Akun.objects.filter(
        peran=Akun.Peran.KEPALA_DESA
    ).order_by("penduduk_id").first()
    if not kades:
        raise ValueError("Akun Kepala Desa belum tersedia")

    raw_data = dict(permohonan.data or {})
    raw_data["nama_kepala_desa"] = kades.penduduk.nama_lengkap
    raw_data["nip_kepala_desa"] = kades.nip or ""
    raw_data["tanggal_ttd"] = timezone.localtime().strftime("%Y-%m-%d")
    raw_data["qr_ttd"] = str(dokumen.public_token)
    raw_data.setdefault("tempat_ttd", "SRAGEN")

    kode_surat = permohonan.jenis_surat.kode

    # 🔥 Generate Excel
    if kode_surat == "B01":
        excel_bytes = generate_b01_excel(lokasi_template.template_file.path, raw_data)

    elif kode_surat == "B02":
        raw_data.setdefault("nama_pemohon", raw_data.get("nama_lengkap", ""))
        raw_data.setdefault("nama_petugas", "ADMIN")
        excel_bytes = generate_b02_excel(lokasi_template.template_file.path, raw_data)

    elif kode_surat == "B03":
        excel_bytes = generate_b03_excel(lokasi_template.template_file.path, raw_data)

    elif kode_surat == "B04":
        excel_bytes = generate_b04_excel(lokasi_template.template_file.path, raw_data)

    elif kode_surat == "B05":
        excel_bytes = generate_b05_excel(lokasi_template.template_file.path, raw_data)

    elif kode_surat == "B09":
        excel_bytes = generate_b09_excel(lokasi_template.template_file.path, raw_data)

    else:
        raise ValueError(f"Generator Excel untuk {kode_surat} belum tersedia")

    # 🔥 Convert ke PDF
    pdf_bytes = convert_excel_to_pdf(excel_bytes)

    file_name = f"surat_{dokumen.public_token}.pdf"

    # hapus file lama
    if dokumen.file_final:
        dokumen.file_final.delete(save=False)

    # simpan PDF
    dokumen.file_final.save(
        file_name,
        ContentFile(pdf_bytes),
        save=True
    )
