import cloudinary.uploader
from django.conf import settings
from accounts.models import Lecturer
from ..models import SuratRequest, SuratApproval, SuratAttachment, SuratAuditLog, ApprovalRule

def create_approval_workflow_for_request(surat_req, student):
    """
    Fungsi Helper (DRY) untuk membuat antrean SuratApproval berjenjang
    berdasarkan ApprovalRule untuk sebuah SuratRequest yang sudah ada.
    Mendukung Non-Destructive Interceptor untuk 1-step approval saat mode demo aktif.
    """
    surat_type = surat_req.kode_surat
    kode_surat_str = getattr(surat_type, 'kode_surat', str(surat_type))

    # INTERCEPTOR DEMO ONE-STEP APPROVAL:
    # Memangkas birokrasi menjadi 1 langkah langsung ke akun Dr. Joel Evans, M.T.
    # khusus target surat demo (SR-MAG dan SR-BEA) tanpa merusak tabel approval_rules.
    demo_enabled = getattr(settings, 'DEMO_ONE_STEP_APPROVAL', True)
    demo_target_surat = getattr(settings, 'DEMO_TARGET_SURAT', ['SR-MAG', 'SR-BEA'])
    demo_approver_nip = getattr(settings, 'DEMO_APPROVER_NIP', '198001012005011001')

    if demo_enabled and kode_surat_str in demo_target_surat:
        joel_evans = (
            Lecturer.objects.filter(user__nip_nim=demo_approver_nip).first()
            or Lecturer.objects.filter(user__nama__icontains="Joel Evans").first()
        )
        if joel_evans:
            SuratApproval.objects.create(
                surat_request=surat_req,
                step_order=1,
                approver=joel_evans,
                status='PENDING'
            )
            return

    rules = ApprovalRule.objects.filter(kode_surat=surat_type).order_by('step_order')

    if not rules.exists():
        # Fallback default jika rule belum diatur: arahkan ke Dosen Pembimbing Akademik (DPA)
        default_approver = student.dosen_pembimbing_akademik
        if default_approver:
            SuratApproval.objects.create(
                surat_request=surat_req,
                step_order=1,
                approver=default_approver,
                status='PENDING' # Gunakan string langsung jika enum belum siap di file ini
            )
    else:
        # Daftarkan antrean approval sesuai step rule
        for rule in rules:
            approver_obj = None
            if rule.approval_role == 'DPA':
                approver_obj = student.dosen_pembimbing_akademik
            elif rule.approval_role == 'KAPRODI':
                approver_obj = student.prodi.kaprodi
            elif rule.approval_role == 'DEKAN':
                approver_obj = student.fakultas.dekan

            if approver_obj:
                SuratApproval.objects.create(
                    surat_request=surat_req,
                    step_order=rule.step_order,
                    approver=approver_obj,
                    # Step 1 langsung PENDING (aktif), sisanya WAITING
                    status='PENDING' if rule.step_order == 1 else 'WAITING'
                )

def handle_manual_approval_surat(student, surat_type, payload_data, attachments_files=None):
    """
    Menangani pengajuan surat jalur Manual Approval Berjenjang.
    """
    # 1. Buat record SuratRequest dengan status SUBMITTED
    surat_req = SuratRequest.objects.create(
        student=student,
        kode_surat=surat_type,
        payload_data=payload_data,
        status='SUBMITTED'
    )

    # 2. Simpan lampiran dokumen ke Cloudinary jika ada
    if attachments_files:
        for file_obj in attachments_files:
            upload_res = cloudinary.uploader.upload(
                file_obj, 
                resource_type="auto", 
                folder="autosurat_attachments"
            )
            SuratAttachment.objects.create(
                surat_request=surat_req,
                nama_dokumen=file_obj.name,
                file_url=upload_res.get("secure_url"),
                mime_type=getattr(file_obj, 'content_type', 'application/octet-stream')
            )

    # 3. Ambil aturan approval berjenjang berdasarkan ApprovalRule
    create_approval_workflow_for_request(surat_req, student)
    
    # 4. Catat Audit Log
    SuratAuditLog.objects.create(
        surat_request=surat_req,
        action_id="SUB_01",
        action="SURAT_SUBMITTED_FOR_APPROVAL"
    )

    return {
        "message": f"Pengajuan surat {surat_type.nama_surat} berhasil dikirim dan masuk antrean approval.",
        "request_id": surat_req.id,
        "status": "SUBMITTED"
    }, 201
