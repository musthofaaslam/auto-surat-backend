# apps/surat/services/workflow_service.py
from django.utils import timezone
from django.db import transaction
from .auto_handlers import handle_auto_approval_surat
from .manual_handlers import handle_manual_approval_surat
from .number_service import generate_surat_number
from .tte_service import create_tte_signature
from .pdf_service import render_and_upload_pdf
from ..models import SuratApproval, SuratAuditLog

def process_surat_request(student, surat_type, payload_data, attachments_files=None):
    """
    Router utama untuk mengarahkan pengajuan ke jalur Auto atau Manual.
    """
    if surat_type.is_auto_approval:
        return handle_auto_approval_surat(student, surat_type, payload_data, attachments_files)
    else:
        return handle_manual_approval_surat(student, surat_type, payload_data, attachments_files)


def process_approval_action(approval_id, lecturer, action, catatan=""):
    """
    Router saat Dosen melakukan APPROVE atau REJECT pada antrean surat.
    action: 'APPROVE' atau 'REJECT'
    """
    try:
        approval_step = SuratApproval.objects.select_related(
            'surat_request', 
            'surat_request__kode_surat', 
            'surat_request__student', 
            'surat_request__student__fakultas',
            'surat_request__student__prodi'
        ).get(id=approval_id)
    except SuratApproval.DoesNotExist:
        return {"error": "Antrean approval tidak ditemukan."}, 404

    surat_req = approval_step.surat_request

    # Validasi kepemilikan approver
    if approval_step.approver != lecturer:
        return {"error": "Anda tidak memiliki hak akses untuk menyetujui antrean ini."}, 403

    if approval_step.status != 'PENDING':
        return {"error": "Langkah persetujuan ini belum aktif atau sudah diproses sebelumnya."}, 400

    # Handle REJECT
    if action == 'REJECT':
        approval_step.status = 'REJECTED'
        approval_step.catatan = catatan
        approval_step.save(update_fields=['status', 'catatan'])

        surat_req.status = 'REJECTED'
        surat_req.save(update_fields=['status'])

        SuratAuditLog.objects.create(
            surat_request=surat_req,
            action_id="REJ_01",
            action=f"REJECTED_BY_{lecturer.id}"
        )
        return {"message": "Pengajuan surat telah ditolak."}, 200

    # Handle APPROVE
    if action == 'APPROVE':
        approval_step.status = 'APPROVED'
        approval_step.catatan = catatan
        approval_step.save(update_fields=['status', 'catatan'])

        # Cek apakah masih ada step approval berikutnya
        next_step = SuratApproval.objects.filter(
            surat_request=surat_req, 
            step_order=approval_step.step_order + 1
        ).first()

        if next_step:
            # Aktifkan step berikutnya menjadi PENDING
            next_step.status = 'PENDING'
            next_step.save(update_fields=['status'])
            surat_req.status = 'IN_REVIEW'
            surat_req.save(update_fields=['status'])

            SuratAuditLog.objects.create(
                surat_request=surat_req,
                action_id=f"APP_0{approval_step.step_order}",
                action=f"APPROVED_STEP_{approval_step.step_order}_FORWARDED"
            )
            return {"message": "Persetujuan tahap ini berhasil. Surat diteruskan ke pejabat selanjutnya."}, 200
        else:
            # Jika ini step terakhir, terbitkan surat resmi secara penuh!
            surat_req.status = 'APPROVED'
            
            try:
                # Bungkus proses akhir dengan transaksi agar aman
                with transaction.atomic():
                    # 1. Generate Nomor Surat Resmi
                    nomor_resmi = generate_surat_number(surat_req.kode_surat, fakultas=surat_req.student.fakultas)
                    surat_req.nomor_surat_resmi = nomor_resmi
                    surat_req.kode_surat.template_path = "../../templates/kerangka-surat/base_surat_template.html"

                    # 2. Generate TTE & QR Code
                    tte_data = create_tte_signature(surat_req, signer=lecturer)
                    surat_req.qr_verification_code = tte_data['qr_code_url']

                    # Tentukan teks konten final yang akan dicetak
                    resolved_content = (
                        surat_req.final_approved_content 
                        or surat_req.ai_original_draft 
                        or ""
                    )

                    # 3. Render PDF & Upload ke Cloudinary
                    context_data = {
                        "student": surat_req.student,
                        "payload": surat_req.payload_data,
                        "nomor_surat": nomor_resmi,
                        "qr_code_url": tte_data['qr_code_url'],
                        "final_content": resolved_content  # <-- DIPERBAIKI: Naskah dikirim ke template PDF
                    }
                    pdf_url = render_and_upload_pdf(surat_req.kode_surat.template_path, context_data)
                    surat_req.file_pdf_url = pdf_url
                    surat_req.save()

                # 4. Catat Audit Log Final di luar blok transaksi kritis atau di dalam
                SuratAuditLog.objects.create(
                    surat_request=surat_req,
                    action_id="FIN_01",
                    action="FINAL_APPROVED_AND_ISSUED"
                )

            except Exception as e:
                return {"error": f"Gagal menerbitkan dokumen resmi: {str(e)}"}, 500

            return {
                "message": "Persetujuan final selesai. Surat resmi berhasil diterbitkan!",
                "nomor_surat_resmi": nomor_resmi,
                "file_pdf_url": surat_req.file_pdf_url
            }, 200

    return {"error": "Aksi tidak valid."}, 400