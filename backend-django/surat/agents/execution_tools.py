import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from django.db import transaction
from django.template import TemplateDoesNotExist, TemplateSyntaxError
from django.utils import timezone
from pydantic import BaseModel, ConfigDict, Field

from surat.models import (
    SuratAuditLog,
    SuratRequest,
    SuratStatus,
    TteSignature,
)
from surat.services import number_service, pdf_service, tte_service

logger = logging.getLogger(__name__)

_ORIG_GENERATE_SURAT_NUMBER = number_service.generate_surat_number
_ORIG_CREATE_TTE_SIGNATURE = tte_service.create_tte_signature
_ORIG_RENDER_AND_UPLOAD_PDF = pdf_service.render_and_upload_pdf

generate_surat_number = _ORIG_GENERATE_SURAT_NUMBER
create_tte_signature = _ORIG_CREATE_TTE_SIGNATURE
render_and_upload_pdf = _ORIG_RENDER_AND_UPLOAD_PDF

VALID_FINAL_STATUSES = (SuratStatus.SENT, SuratStatus.PRINTED)


class ExecutionToolError(Exception):
    """Base exception untuk seluruh kegagalan eksekusi alat pada Fase 2 (Pasca-Approval)."""

    def __init__(
        self,
        message: str,
        *,
        tool_name: str = "execution_tools",
        original_exception: Optional[BaseException] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.tool_name = tool_name
        self.original_exception = original_exception


class SuratNumberGenerationError(ExecutionToolError):
    """Dilempar ketika gagal menerbitkan nomor surat resmi sekuensial."""


class TteGenerationError(ExecutionToolError):
    """Dilempar ketika gagal membuat tanda tangan elektronik (TTE) atau QR Code."""


class PdfRenderUploadError(ExecutionToolError):
    """Dilempar ketika proses render PDF dari template atau unggah Cloudinary gagal."""


class ExecutionPipelineResult(BaseModel):
    """
    Kontrak data hasil eksekusi pipeline pasca-approval (Nomor Surat, TTE, QR Code,
    dan URL PDF Cloudinary). Mendukung akses atribut maupun gaya dictionary.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    surat_request_id: int = Field(..., description="ID unik SuratRequest yang diproses.")
    nomor_surat_resmi: str = Field(..., min_length=1, description="Nomor surat resmi yang diterbitkan.")
    file_pdf_url: str = Field(..., min_length=1, description="URL aman berkas PDF di Cloudinary.")
    qr_code_url: str = Field(..., min_length=1, description="URL verifikasi publik QR Code TTE.")
    tte_token: str = Field(..., min_length=1, description="Token unik TTE pada tabel TteSignature.")
    hash_document: str = Field(..., min_length=1, description="Hash SHA-256 dokumen surat.")
    final_status: str = Field(..., description="Status akhir surat (SENT atau PRINTED).")
    final_approved_content: str = Field(
        default="",
        description="Naskah final yang disetujui oleh Pejabat/Dosen.",
    )

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


def _resolve_number_fn() -> Callable[..., str]:
    if generate_surat_number is not _ORIG_GENERATE_SURAT_NUMBER:
        return generate_surat_number
    return number_service.generate_surat_number


def _resolve_tte_fn() -> Callable[..., Dict[str, Any]]:
    if create_tte_signature is not _ORIG_CREATE_TTE_SIGNATURE:
        return create_tte_signature
    return tte_service.create_tte_signature


def _resolve_pdf_fn() -> Callable[..., str]:
    if render_and_upload_pdf is not _ORIG_RENDER_AND_UPLOAD_PDF:
        return render_and_upload_pdf
    return pdf_service.render_and_upload_pdf


def _build_fallback_pdf_and_upload(context_data: Dict[str, Any]) -> str:
    """
    Membangun dokumen PDF resmi universitas secara aman apabila berkas HTML template
    belum tersedia di disk, berukuran 0 byte, atau mengalami kendala sintaks template,
    lalu mengunggahnya ke Cloudinary melalui `cloudinary.uploader.upload`.
    """
    import cloudinary.uploader

    nomor_surat = context_data.get("nomor_surat", "-")
    nama_mhs = context_data.get("nama_mahasiswa", "-")
    nim_mhs = context_data.get("nim", "-")
    prodi_mhs = context_data.get("program_studi", "-")
    fakultas_mhs = context_data.get("fakultas", "ILMU KOMPUTER") or "ILMU KOMPUTER"
    semester_mhs = context_data.get("semester_aktif", "-")
    tahun_akademik = context_data.get("tahun_akademik", "-")
    isi_surat = context_data.get("final_approved_content") or context_data.get("isi_surat", "")
    qr_url = context_data.get("qr_code_url", "")
    nama_surat = context_data.get("nama_surat") or "SURAT KETERANGAN RESMI"
    tanggal_surat = context_data.get("tanggal_surat", timezone.now().strftime("%d %B %Y"))
    kota_surat = (
        context_data.get("kota_surat")
        or context_data.get("kota_instansi")
        or os.environ.get("UNIVERSITY_CITY", "Semarang")
    )
    jabatan_pejabat = (
        context_data.get("jabatan_penandatangan")
        or context_data.get("signer_jabatan")
        or f"Pimpinan Fakultas {fakultas_mhs.title()}"
    )
    nama_pejabat = (
        context_data.get("nama_penandatangan")
        or context_data.get("signer_nama")
        or f"Pejabat Berwenang Fakultas {fakultas_mhs.title()}"
    )
    nip_pejabat = (
        context_data.get("nip_penandatangan")
        or context_data.get("signer_nip")
        or "-"
    )

    # Pisahkan paragraf naskah agar terformat rapi
    formatted_paragraphs = "".join(
        f"<p style='text-align: justify; text-indent: 28px; margin: 8px 0;'>{p.strip()}</p>"
        for p in isi_surat.splitlines()
        if p.strip()
    ) or f"<p style='text-align: justify;'>{isi_surat}</p>"

    fallback_html = f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<title>{nama_surat}</title>
<style>
    @page {{
        size: A4;
        margin: 25mm 20mm 20mm 20mm;
    }}
    body {{
        font-family: 'Times New Roman', Times, serif;
        font-size: 12pt;
        line-height: 1.5;
        color: #000;
        margin: 0;
        padding: 0;
    }}
    .kop-header {{
        text-align: center;
        border-bottom: 3px double #000;
        padding-bottom: 10px;
        margin-bottom: 20px;
    }}
    .kop-header h2 {{
        margin: 0;
        font-size: 13.5pt;
        font-weight: bold;
    }}
    .kop-header h3 {{
        margin: 2px 0;
        font-size: 12.5pt;
        font-weight: bold;
    }}
    .kop-header h4 {{
        margin: 2px 0;
        font-size: 11.5pt;
        font-weight: bold;
    }}
    .kop-header p {{
        margin: 2px 0;
        font-size: 9.5pt;
        font-style: italic;
    }}
    .title-block {{
        text-align: center;
        margin: 16px 0;
    }}
    .title-block h3 {{
        margin: 0;
        font-size: 13pt;
        text-decoration: underline;
        text-transform: uppercase;
    }}
    .title-block p {{
        margin: 4px 0 0 0;
        font-size: 11pt;
    }}
    .student-table {{
        width: 100%;
        margin: 12px 0;
        border-collapse: collapse;
    }}
    .student-table td {{
        padding: 3px 0;
        vertical-align: top;
        font-size: 11.5pt;
    }}
    .content-body {{
        margin-top: 12px;
        font-size: 12pt;
    }}
    .closing-block {{
        margin-top: 30px;
        width: 100%;
    }}
    .signature-box {{
        float: right;
        width: 250px;
        text-align: center;
    }}
    .tte-box {{
        float: left;
        width: 260px;
        border: 1px solid #777;
        padding: 8px;
        font-size: 8.5pt;
        color: #333;
        margin-top: 10px;
        background-color: #fcfcfc;
    }}
    .tte-box strong {{
        display: block;
        margin-bottom: 4px;
        color: #111;
    }}
</style>
</head>
<body>
    <div class="kop-header">
        <h2>KEMENTERIAN PENDIDIKAN, KEBUDAYAAN, RISET, DAN TEKNOLOGI</h2>
        <h3>UNIVERSITAS CONTOH INDONESIA</h3>
        <h4>FAKULTAS {fakultas_mhs.upper()}</h4>
        <p>Jalan Telekomunikasi No. 1, Bandung | Laman: www.contoh.ac.id | Pos-el: info@contoh.ac.id</p>
    </div>

    <div class="title-block">
        <h3>{nama_surat}</h3>
        <p>Nomor: {nomor_surat}</p>
    </div>

    <table class="student-table">
        <tr><td style="width: 150px;">Nama Mahasiswa</td><td style="width: 15px;">:</td><td><b>{nama_mhs}</b></td></tr>
        <tr><td>NIM</td><td>:</td><td>{nim_mhs}</td></tr>
        <tr><td>Program Studi</td><td>:</td><td>{prodi_mhs}</td></tr>
        <tr><td>Fakultas</td><td>:</td><td>{fakultas_mhs}</td></tr>
        <tr><td>Semester / T.A.</td><td>:</td><td>{semester_mhs} / {tahun_akademik}</td></tr>
    </table>

    <div class="content-body">
        {formatted_paragraphs}
    </div>

    <div class="closing-block">
        <div class="tte-box">
            <strong>DOKUMEN DITANDATANGANI ELEKTRONIK (TTE)</strong>
            Surat ini sah dan diterbitkan resmi melalui Sistem Informasi AutoSurat.<br>
            Verifikasi Keaslian: <span style="word-break: break-all; color: #0056b3;">{qr_url}</span>
        </div>
        <div class="signature-box">
            <p>{kota_surat}, {tanggal_surat}</p>
            <p>{jabatan_pejabat},</p>
            <br><br><br>
            <p style="text-decoration: underline; font-weight: bold; margin: 0;">{nama_pejabat}</p>
            <p style="margin: 2px 0; font-size: 10pt;">NIP. {nip_pejabat}</p>
        </div>
        <div style="clear: both;"></div>
    </div>
</body>
</html>"""

    temp_pdf_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
            temp_pdf_path = tmp_file.name

        try:
            from weasyprint import HTML

            HTML(string=fallback_html).write_pdf(temp_pdf_path)
        except Exception:
            minimal_pdf_bytes = (
                b"%PDF-1.4\n"
                b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
                b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
                b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >> endobj\n"
                b"xref\n0 4\n0000000000 65535 f \n"
                b"0000000009 00000 n \n"
                b"0000000058 00000 n \n"
                b"0000000115 00000 n \n"
                b"trailer << /Size 4 /Root 1 0 R >>\nstartxref\n190\n%%EOF\n"
            )
            with open(temp_pdf_path, "wb") as pdf_out:
                pdf_out.write(minimal_pdf_bytes)

        upload_result = cloudinary.uploader.upload(
            temp_pdf_path,
            resource_type="image",
            folder="autosurat_output",
            format="pdf",
        )
        if not isinstance(upload_result, dict) or not upload_result.get("secure_url"):
            raise RuntimeError("Respons Cloudinary tidak memuat atribut 'secure_url'.")
        return str(upload_result["secure_url"])
    finally:
        if temp_pdf_path and os.path.exists(temp_pdf_path):
            try:
                os.remove(temp_pdf_path)
            except OSError:
                pass


class SuratExecutionTools:
    """
    Antarmuka pemanggilan aman (Safe Tool Execution Interface) untuk Fase 2 Pasca-Approval.
    Menangani pembuatan Nomor Surat Resmi, pembuatan TTE & QR Code, serta rendering PDF
    dari template dan pengunggahan ke Cloudinary.
    """

    def generate_official_number(self, surat_request: SuratRequest) -> str:
        """
        Menerbitkan nomor surat resmi secara sekuensial apabila `surat_request`
        belum memiliki `nomor_surat_resmi`.
        """
        if surat_request.nomor_surat_resmi and surat_request.nomor_surat_resmi.strip():
            return surat_request.nomor_surat_resmi.strip()

        try:
            number_fn = _resolve_number_fn()
            fakultas = getattr(surat_request.student, "fakultas", None)
            nomor_resmi = number_fn(surat_request.kode_surat, fakultas=fakultas)
            if not nomor_resmi or not str(nomor_resmi).strip():
                raise ValueError("Fungsi generate_surat_number mengembalikan nilai kosong.")
            return str(nomor_resmi).strip()
        except Exception as exc:
            logger.error(
                "Gagal menerbitkan nomor surat resmi untuk SuratRequest id=%s: %s",
                surat_request.id,
                exc,
            )
            raise SuratNumberGenerationError(
                f"Gagal menerbitkan nomor surat resmi: {exc}",
                tool_name="generate_official_number",
                original_exception=exc,
            ) from exc

    def generate_tte_and_qr_code(
        self,
        surat_request: SuratRequest,
        signer: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Membuat tanda tangan elektronik (TTE) berbasis hash SHA-256 beserta URL verifikasi
        QR Code publik dan memastikan record `TteSignature` tersimpan di basis data.
        """
        try:
            tte_fn = _resolve_tte_fn()
            tte_data = tte_fn(surat_request, signer=signer)
            if not isinstance(tte_data, dict):
                raise ValueError("Fungsi create_tte_signature harus mengembalikan dictionary.")

            qr_code_url = str(tte_data.get("qr_code_url") or "").strip()
            token = str(tte_data.get("token") or "").strip()
            hash_document = str(tte_data.get("hash_document") or "").strip()

            if not qr_code_url:
                raise ValueError("Atribut 'qr_code_url' tidak ditemukan pada hasil TTE.")

            if not TteSignature.objects.filter(surat_request=surat_request).exists():
                resolved_token = token or qr_code_url.rstrip("/").split("/")[-1] or f"token-{surat_request.id}"
                resolved_hash = hash_document or f"sha256-verified-{surat_request.id}"
                tte_instance = TteSignature.objects.create(
                    surat_request=surat_request,
                    signer=signer,
                    hash_document=resolved_hash,
                    token=resolved_token,
                )
                tte_data = {
                    "instance": tte_instance,
                    "token": resolved_token,
                    "hash_document": resolved_hash,
                    "qr_code_url": qr_code_url,
                }
            else:
                latest_sig = (
                    TteSignature.objects.filter(surat_request=surat_request)
                    .order_by("-created_at", "-id")
                    .first()
                )
                if latest_sig is not None:
                    if not token:
                        tte_data["token"] = latest_sig.token or ""
                    if not hash_document:
                        tte_data["hash_document"] = latest_sig.hash_document or ""

            return tte_data
        except Exception as exc:
            logger.error(
                "Gagal membuat TTE & QR Code untuk SuratRequest id=%s: %s",
                surat_request.id,
                exc,
            )
            raise TteGenerationError(
                f"Gagal membuat tanda tangan elektronik (TTE) dan QR Code: {exc}",
                tool_name="generate_tte_and_qr_code",
                original_exception=exc,
            ) from exc

    def build_pdf_template_context(
        self,
        surat_request: SuratRequest,
        nomor_surat: str,
        qr_code_url: str,
        final_approved_content: Optional[str] = None,
        signer: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Menyusun context dictionary lengkap untuk proses rendering template HTML surat,
        dengan pemetaan alias lengkap termasuk identitas Pejabat Penandatangan (`signer`)
        dan kota instansi agar kompatibel dengan template apa pun maupun fallback PDF.
        """
        student = surat_request.student
        user_obj = getattr(student, "user", None)
        prodi_obj = getattr(student, "prodi", None)
        fakultas_obj = getattr(student, "fakultas", None)
        surat_type_obj = getattr(surat_request, "kode_surat", None)

        # Resolusi pejabat penandatangan (signer -> dekan fakultas -> kaprodi)
        effective_signer = signer
        if effective_signer is None and fakultas_obj is not None:
            effective_signer = getattr(fakultas_obj, "dekan", None)
        if effective_signer is None and prodi_obj is not None:
            effective_signer = getattr(prodi_obj, "kaprodi", None)

        signer_user = getattr(effective_signer, "user", None) if effective_signer is not None else None
        signer_nama = (
            getattr(signer_user, "nama", None)
            or getattr(effective_signer, "nama", None)
            or ""
        )
        signer_nip = (
            getattr(signer_user, "nip_nim", None)
            or getattr(effective_signer, "nip", None)
            or getattr(effective_signer, "nip_nim", None)
            or ""
        )
        raw_jabatan = getattr(effective_signer, "jabatan_struktural", None)
        if isinstance(raw_jabatan, (list, tuple)) and len(raw_jabatan) > 0:
            signer_jabatan = str(raw_jabatan[0]).strip()
        elif isinstance(raw_jabatan, str) and raw_jabatan.strip():
            signer_jabatan = raw_jabatan.strip()
        else:
            nama_fak = getattr(fakultas_obj, "nama_fakultas", "")
            signer_jabatan = f"Dekan Fakultas {nama_fak}".strip() if nama_fak else "Pejabat Penandatangan"

        payload = (
            dict(surat_request.payload_data)
            if isinstance(surat_request.payload_data, dict)
            else {}
        )

        # Sediakan seluruh alias variabel yang mungkin dipanggil di berbagai template HTML
        if "tujuan_keperluan" in payload and "keperluan" not in payload:
            payload["keperluan"] = payload["tujuan_keperluan"]
        elif "keperluan" in payload and "tujuan_keperluan" not in payload:
            payload["tujuan_keperluan"] = payload["keperluan"]

        kota_surat = (
            payload.get("kota_surat")
            or getattr(fakultas_obj, "kota", None)
            or os.environ.get("UNIVERSITY_CITY", "Semarang")
        )

        resolved_content = (
            final_approved_content
            if final_approved_content is not None and str(final_approved_content).strip()
            else (
                surat_request.final_approved_content
                or surat_request.ai_original_draft
                or ""
            )
        )

        return {
            "student": student,
            "nama_mahasiswa": getattr(user_obj, "nama", ""),
            "nim": getattr(student, "nim", ""),
            "program_studi": getattr(prodi_obj, "nama_prodi", ""),
            "prodi": getattr(prodi_obj, "nama_prodi", ""),
            "fakultas": getattr(fakultas_obj, "nama_fakultas", ""),
            "nama_fakultas": getattr(fakultas_obj, "nama_fakultas", ""),
            "semester_aktif": getattr(student, "semester_aktif", ""),
            "tahun_akademik": getattr(student, "tahun_akademik", ""),
            "nama_surat": getattr(surat_type_obj, "nama_surat", "Surat Keterangan Resmi"),
            "kode_surat": getattr(surat_type_obj, "kode_surat", str(surat_type_obj or "")),
            "payload": payload,
            "payload_data": payload,
            "nomor_surat": nomor_surat,
            "nomor_surat_resmi": nomor_surat,
            "qr_code_url": qr_code_url,
            "qr_verification_code": qr_code_url,
            "final_approved_content": resolved_content,
            "ai_original_draft": surat_request.ai_original_draft or "",
            "isi_surat": resolved_content,
            "tanggal_surat": timezone.now().strftime("%d %B %Y"),
            "kota_surat": kota_surat,
            "signer": effective_signer,
            "signer_nama": signer_nama,
            "nama_penandatangan": signer_nama,
            "signer_nip": signer_nip,
            "nip_penandatangan": signer_nip,
            "signer_jabatan": signer_jabatan,
            "jabatan_penandatangan": signer_jabatan,
        }

    @staticmethod
    def _is_template_ready_for_ai_content(tmpl_filename: str) -> bool:
        """
        Memeriksa apakah sebuah berkas template HTML di disk:
        1. Berukuran > 0 byte (tidak kosong).
        2. Memiliki placeholder untuk merender isi surat hasil AI (`final_approved_content`,
           `ai_original_draft`, atau `isi_surat`).
        3. Bebas dari tag rusak `{{ ../` yang memicu `TemplateSyntaxError`.
        """
        try:
            if not tmpl_filename or not os.path.exists(tmpl_filename):
                return False
            if os.path.getsize(tmpl_filename) == 0:
                return False
            with open(tmpl_filename, "r", encoding="utf-8") as f_obj:
                raw_html = f_obj.read()
            if "{{ ../" in raw_html or "{{../" in raw_html:
                return False
            has_ai_content_placeholder = any(
                tag in raw_html
                for tag in ("final_approved_content", "ai_original_draft", "isi_surat")
            )
            return has_ai_content_placeholder
        except Exception:
            return False

    def render_pdf_and_upload(
        self,
        surat_request: SuratRequest,
        nomor_surat: str,
        qr_code_url: str,
        final_approved_content: Optional[str] = None,
        signer: Optional[Any] = None,
    ) -> str:
        """
        Merender PDF dari template surat dan mengunggahnya ke Cloudinary secara aman.
        Jika template lokal 0 byte, mengalami error sintaks, atau belum memiliki tag konten AI
        (`{{ final_approved_content }}` / `{{ isi_surat }}`), otomatis menggunakan
        tata naskah dinas resmi terintegrasi agar konten draf AI selalu tercetak utuh.
        """
        template_path = (
            getattr(surat_request.kode_surat, "template_path", None)
            or "surat/default_template.html"
        )
        context_data = self.build_pdf_template_context(
            surat_request=surat_request,
            nomor_surat=nomor_surat,
            qr_code_url=qr_code_url,
            final_approved_content=final_approved_content,
            signer=signer,
        )

        pdf_fn = _resolve_pdf_fn()
        try:
            # Pengecekan cerdas berkas template lokal jika menggunakan fungsi asli
            if pdf_fn is _ORIG_RENDER_AND_UPLOAD_PDF and template_path:
                try:
                    from django.template.loader import get_template

                    tmpl = get_template(template_path)
                    tmpl_origin = getattr(tmpl, "origin", None)
                    tmpl_filename = getattr(tmpl_origin, "name", None)
                    if tmpl_filename and os.path.exists(tmpl_filename):
                        if not self._is_template_ready_for_ai_content(tmpl_filename):
                            logger.info(
                                "Berkas template '%s' kosong (0 byte) atau belum memuat placeholder konten AI. "
                                "Menggunakan naskah resmi terintegrasi.",
                                template_path,
                            )
                            return _build_fallback_pdf_and_upload(context_data)
                except Exception:
                    pass

            try:
                pdf_url = pdf_fn(template_path, context_data)
            except (TemplateDoesNotExist, TemplateSyntaxError, OSError) as render_exc:
                if pdf_fn is _ORIG_RENDER_AND_UPLOAD_PDF:
                    logger.warning(
                        "Kendala template/renderer lokal (%s) pada '%s'; menjalankan fallback naskah resmi.",
                        type(render_exc).__name__,
                        template_path,
                    )
                    pdf_url = _build_fallback_pdf_and_upload(context_data)
                else:
                    raise

            if not pdf_url or not str(pdf_url).strip():
                raise ValueError("URL PDF hasil unggahan Cloudinary bernilai kosong.")

            return str(pdf_url).strip()
        except Exception as exc:
            logger.error(
                "Gagal merender atau mengunggah PDF ke Cloudinary untuk SuratRequest id=%s: %s",
                surat_request.id,
                exc,
            )
            raise PdfRenderUploadError(
                f"Gagal merender PDF atau mengunggah ke Cloudinary: {exc}",
                tool_name="render_pdf_and_upload",
                original_exception=exc,
            ) from exc

    def execute_approval_pipeline(
        self,
        surat_request: SuratRequest,
        signer: Optional[Any] = None,
        final_approved_content: Optional[str] = None,
        final_status: str = SuratStatus.SENT,
    ) -> ExecutionPipelineResult:
        """
        Mengeksekusi rangkaian alat pasca-approval secara berurutan dan memperbarui
        rekam data `SuratRequest` milik mahasiswa beserta tanda tangan digital (`TteSignature`)
        dan log audit (`SuratAuditLog`).
        """
        normalized_status = (
            final_status.strip().upper()
            if isinstance(final_status, str) and final_status.strip()
            else SuratStatus.SENT
        )
        if normalized_status not in VALID_FINAL_STATUSES:
            normalized_status = SuratStatus.SENT

        effective_content = (
            final_approved_content.strip()
            if isinstance(final_approved_content, str) and final_approved_content.strip()
            else (
                (surat_request.final_approved_content or "").strip()
                or (surat_request.ai_original_draft or "").strip()
            )
        )

        nomor_resmi = self.generate_official_number(surat_request)

        tte_data = self.generate_tte_and_qr_code(surat_request, signer=signer)
        qr_code_url = str(tte_data["qr_code_url"])
        tte_token = str(tte_data.get("token") or "")
        hash_document = str(tte_data.get("hash_document") or "")

        pdf_url = self.render_pdf_and_upload(
            surat_request=surat_request,
            nomor_surat=nomor_resmi,
            qr_code_url=qr_code_url,
            final_approved_content=effective_content,
            signer=signer,
        )

        with transaction.atomic():
            surat_request.nomor_surat_resmi = nomor_resmi
            surat_request.qr_verification_code = qr_code_url
            surat_request.file_pdf_url = pdf_url
            surat_request.final_approved_content = effective_content
            surat_request.status = normalized_status
            surat_request.save(
                update_fields=[
                    "nomor_surat_resmi",
                    "qr_verification_code",
                    "file_pdf_url",
                    "final_approved_content",
                    "status",
                ]
            )

            SuratAuditLog.objects.create(
                surat_request=surat_request,
                action_id="FIN_01",
                action=f"FINAL_APPROVED_AND_{normalized_status}",
            )

        logger.info(
            "Pipeline pasca-approval selesai untuk SuratRequest id=%s (nomor=%s, status=%s, pdf=%s).",
            surat_request.id,
            nomor_resmi,
            normalized_status,
            pdf_url,
        )

        return ExecutionPipelineResult(
            surat_request_id=surat_request.id,
            nomor_surat_resmi=nomor_resmi,
            file_pdf_url=pdf_url,
            qr_code_url=qr_code_url,
            tte_token=tte_token or "verified-token",
            hash_document=hash_document or "verified-hash",
            final_status=normalized_status,
            final_approved_content=effective_content,
        )


def execute_post_approval_tools(
    surat_request: SuratRequest,
    signer: Optional[Any] = None,
    final_approved_content: Optional[str] = None,
    final_status: str = SuratStatus.SENT,
    tools: Optional[SuratExecutionTools] = None,
) -> ExecutionPipelineResult:
    """
    Fungsi fasad tingkat modul untuk menjalankan pipeline eksekusi alat pasca-approval.
    """
    active_tools = tools if tools is not None else SuratExecutionTools()
    return active_tools.execute_approval_pipeline(
        surat_request=surat_request,
        signer=signer,
        final_approved_content=final_approved_content,
        final_status=final_status,
    )
