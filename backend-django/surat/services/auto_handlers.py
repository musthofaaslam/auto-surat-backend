import cloudinary.uploader
from .number_service import generate_surat_number
from .tte_service import create_tte_signature
from .pdf_service import render_and_upload_pdf
from ..models import SuratRequest, SuratAttachment, SuratAuditLog

def handle_auto_approval_surat(student, surat_type, payload_data, attachments_files=None):
    """
    Menangani pengajuan surat jalur Auto-Approval (langsung jadi & terbit).
    """
    # 1. Buat record awal SuratRequest dengan status APPROVED
    surat_req = SuratRequest.objects.create(
        student=student,
        kode_surat=surat_type,
        payload_data=payload_data,
        status='APPROVED'
    )

    # 3. Generate Nomor Resmi Surat
    nomor_resmi = generate_surat_number(surat_type, fakultas=student.fakultas)
    surat_req.nomor_surat_resmi = nomor_resmi

    # 4. Generate TTE & QR Code Verifikasi
    tte_data = create_tte_signature(surat_req, signer=None)
    surat_req.qr_verification_code = tte_data['qr_code_url']

    # 5. Render PDF & Upload ke Cloudinary
    context_data = {
        "student": student,
        "payload": payload_data,
        "nomor_surat": nomor_resmi,
        "qr_code_url": tte_data['qr_code_url']
    }
    pdf_url = render_and_upload_pdf(surat_type.template_path, context_data)
    surat_req.file_pdf_url = pdf_url
    surat_req.save()

    # 6. Catat Audit Log
    SuratAuditLog.objects.create(
        surat_request=surat_req,
        action_id="SYS_01",
        action="SYSTEM_AUTO_APPROVED"
    )

    return {
        "message": f"Surat {surat_type.nama_surat} berhasil diterbitkan secara otomatis.",
        "request_id": surat_req.id,
        "nomor_surat_resmi": nomor_resmi,
        "file_pdf_url": pdf_url
    }, 201
