# apps/surat/services/workflow_service.py
from logging import getLogger
from django.utils import timezone
from django.db import transaction
from .auto_handlers import handle_auto_approval_surat
from .manual_handlers import handle_manual_approval_surat
from .number_service import generate_surat_number
from .tte_service import create_tte_signature
from .pdf_service import render_and_upload_pdf
from ..models import SuratApproval, SuratAuditLog, SuratRequest
from .email_service import send_surat_via_gmail_admin
from .telegram_service import send_surat_via_telegram
import threading
from django.db import close_old_connections

logger = getLogger(__name__)

_last_issuance_worker_thread = None

def process_surat_request(student, surat_type, payload_data, attachments_files=None):
    """
    Router utama untuk mengarahkan pengajuan ke jalur Auto atau Manual.
    """
    if surat_type.is_auto_approval:
        return handle_auto_approval_surat(student, surat_type, payload_data, attachments_files)
    else:
        return handle_manual_approval_surat(student, surat_type, payload_data, attachments_files)


def process_approval_action(
    approval_id,
    lecturer,
    action,
    catatan="",
    final_approved_content=None,
    final_status="SENT",
):
    """
    Router saat Dosen melakukan APPROVE atau REJECT pada antrean surat.
    action: 'APPROVE' atau 'REJECT'
    Mendukung penyimpanan koreksi draf oleh Dosen (`final_approved_content`),
    pilihan status akhir (`final_status`), serta pemicuan pembelajaran memori gaya bahasa (Fase 3).
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

    # Evaluasi otorisasi demo: Khusus SR-MAG dan SR-BEA untuk akun Dr. Joel Evans, M.T.
    from django.conf import settings
    demo_enabled = getattr(settings, 'DEMO_ONE_STEP_APPROVAL', True)
    demo_target_surat = getattr(settings, 'DEMO_TARGET_SURAT', ['SR-MAG', 'SR-BEA'])
    demo_approver_nip = getattr(settings, 'DEMO_APPROVER_NIP', '198001012005011001')
    lecturer_nip = getattr(getattr(lecturer, 'user', None), 'nip_nim', None)
    lecturer_nama = getattr(getattr(lecturer, 'user', None), 'nama', '')
    is_demo_bypass = (
        demo_enabled
        and surat_req.kode_surat.kode_surat in demo_target_surat
        and (lecturer_nip == demo_approver_nip or "Joel Evans" in lecturer_nama)
    )

    # Validasi kepemilikan approver
    if not is_demo_bypass and approval_step.approver != lecturer:
        return {"error": "Anda tidak memiliki hak akses untuk menyetujui antrean ini."}, 403

    if not is_demo_bypass and approval_step.status != 'PENDING':
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

        # Simpan suntingan naskah dari Dosen jika dikirimkan
        if isinstance(final_approved_content, str) and final_approved_content.strip():
            surat_req.final_approved_content = final_approved_content.strip()

        # Cek apakah masih ada step approval berikutnya (dilewati pada mode demo 1-step Joel Evans)
        next_step = None
        if not is_demo_bypass:
            next_step = SuratApproval.objects.filter(
                surat_request=surat_req, 
                step_order=approval_step.step_order + 1
            ).first()

        if next_step:
            # Aktifkan step berikutnya menjadi PENDING
            next_step.status = 'PENDING'
            next_step.save(update_fields=['status'])
            surat_req.status = 'IN_REVIEW'
            update_cols = ['status']
            if isinstance(final_approved_content, str) and final_approved_content.strip():
                update_cols.append('final_approved_content')
            surat_req.save(update_fields=update_cols)

            SuratAuditLog.objects.create(
                surat_request=surat_req,
                action_id=f"APP_0{approval_step.step_order}",
                action=f"APPROVED_STEP_{approval_step.step_order}_FORWARDED"
            )
            return {"message": "Persetujuan tahap ini berhasil. Surat diteruskan ke pejabat selanjutnya."}, 200
        else:
            # Jika ini step terakhir, perbarui status menjadi APPROVED dan delegasikan penerbitan dokumen ke worker asinkron
            resolved_final_status = final_status if final_status in ("SENT", "PRINTED") else "SENT"

            # 1. Kunci naskah persetujuan dan ubah status SuratRequest menjadi APPROVED secara sinkron
            resolved_content = (
                surat_req.final_approved_content 
                or surat_req.ai_original_draft 
                or ""
            )
            if not surat_req.final_approved_content and resolved_content:
                surat_req.final_approved_content = resolved_content

            surat_req.status = 'APPROVED'
            update_req_fields = ['status']
            if isinstance(final_approved_content, str) and final_approved_content.strip():
                update_req_fields.append('final_approved_content')
            surat_req.save(update_fields=update_req_fields)

            SuratAuditLog.objects.create(
                surat_request=surat_req,
                action_id=f"APP_0{approval_step.step_order}",
                action=f"FINAL_APPROVAL_CONFIRMED_BY_{lecturer.id}"
            )

            # 2. Luncurkan worker thread asinkron untuk penerbitan dokumen resmi (Non-blocking I/O)
            global _last_issuance_worker_thread
            issuance_thread = threading.Thread(
                target=_execute_final_issuance_worker,
                kwargs={
                    "surat_request_id": surat_req.id,
                    "signer_lecturer_id": lecturer.id,
                    "final_status": resolved_final_status,
                },
                name=f"async-issuance-{surat_req.id}",
                daemon=True,
            )
            _last_issuance_worker_thread = issuance_thread
            issuance_thread.start()

            # 3. Segera kembalikan respons HTTP 200 ke klien dalam waktu kurang dari 500 ms (< 50 ms)
            return {
                "message": "Persetujuan final berhasil dikonfirmasi. Surat resmi sedang diterbitkan dan dikirim di latar belakang.",
                "status": "APPROVED",
                "nomor_surat_resmi": None,
                "file_pdf_url": None,
            }, 200

    return {"error": "Aksi tidak valid."}, 400


def route_and_distribute_document(surat_request):
    """
    Router utama agen untuk menentukan apakah kirim ke Email atau Telegram
    menggunakan kolom database yang konsisten (`chosen_destination` dan `target_destination_address`).
    """
    if not surat_request.file_pdf_url:
        raise ValueError("File PDF belum tersedia untuk didistribusikan.")

    destination_type = surat_request.chosen_destination  # 'email' atau 'telegram'
    target_address = surat_request.target_destination_address # Berisi email atau chat ID

    if destination_type == 'email':
        subject = f"Dokumen Resmi - {surat_request.kode_surat.nama_surat}"
        body = (
            "Dengan hormat,\n\n"
            "Berikut dilampirkan dokumen resmi yang telah diterbitkan dan disetujui oleh Fakultas.\n"
            "Anda juga dapat melakukan verifikasi keaslian dokumen melalui QR Code pada file terlampir.\n\n"
            "Terima kasih."
        )
        return send_surat_via_gmail_admin(
            recipient_email=target_address,
            subject=subject,
            body_message=body,
            pdf_path=surat_request.file_pdf_url  # Pastikan service menerima URL Cloudinary atau file lokal
        )
        
    elif destination_type == 'telegram':
        caption = "✅ *Surat Resmi Anda Telah Disetujui!*\nBerikut adalah dokumen PDF resmi yang diterbitkan oleh sistem kampus."
        return send_surat_via_telegram(
            chat_id=target_address,
            caption=caption,
            pdf_path=surat_request.file_pdf_url
        )
    else:
        logger.warning(f"Destinasi pengiriman tidak dikenal atau kosong untuk SuratRequest id={surat_request.id}")


def _execute_final_issuance_worker(
    surat_request_id: int,
    signer_lecturer_id: int = None,
    final_status: str = "SENT",
):
    """
    Worker asinkron untuk penerbitan dokumen akhir surat secara non-blocking:
    1. Memanggil close_old_connections() di blok awal dan finally guna mencegah kebocoran koneksi DB.
    2. Mendelegasikan eksekusi penerbitan (Nomor Surat resmi sekuensial, TTE SHA-256 & QR Code,
       render WeasyPrint PDF, dan pengunggahan Cloudinary) ke `SuratExecutionTools.execute_approval_pipeline`.
    3. Menyimpan nomor_surat_resmi, qr_verification_code, file_pdf_url, dan memperbarui status
       akhir surat menjadi SENT atau PRINTED secara atomik di dalam SuratExecutionTools.
    4. Mencatat audit log penerbitan dokumen resmi (FIN_01).
    5. Memicu pembelajaran memori gaya bahasa Fase 3 (AgenticMemoryAgent) dan
       distribusi dokumen ke Email / Telegram (_execute_distribution_worker).
    """
    close_old_connections()
    try:
        from ..models import Lecturer
        from ..agents.execution_tools import SuratExecutionTools

        surat_req = SuratRequest.objects.select_related(
            'kode_surat',
            'student',
            'student__fakultas',
            'student__prodi',
        ).get(pk=surat_request_id)

        signer = None
        if signer_lecturer_id:
            signer = Lecturer.objects.filter(pk=signer_lecturer_id).first()

        resolved_final_status = final_status if final_status in ("SENT", "PRINTED") else "SENT"

        resolved_content = (
            surat_req.final_approved_content 
            or surat_req.ai_original_draft 
            or ""
        )

        # Delegasikan seluruh pipeline penerbitan dokumen pasca-approval ke SuratExecutionTools
        tools = SuratExecutionTools()
        pipeline_result = tools.execute_approval_pipeline(
            surat_request=surat_req,
            signer=signer,
            final_approved_content=resolved_content,
            final_status=resolved_final_status,
        )

        logger.info(
            f"[ASYNC_ISSUANCE_SUCCESS] SuratRequest id={surat_req.id} berhasil diterbitkan (nomor: {pipeline_result.nomor_surat_resmi})."
        )

        # Pembelajaran Memori Gaya Bahasa Fase 3 & Distribusi Dokumen
        _execute_distribution_worker(surat_req.id)

    except Exception as exc:
        logger.exception(f"[ASYNC_ISSUANCE_ERROR] Gagal menerbitkan dokumen resmi di latar belakang id={surat_request_id}: {exc}")
        try:
            surat_req = SuratRequest.objects.get(pk=surat_request_id)
            surat_req.status = "FAILED"
            surat_req.save(update_fields=["status"])
            SuratAuditLog.objects.create(
                surat_request=surat_req,
                action_id="FIN_ERR",
                action=f"ASYNC_ISSUANCE_FAILED: {str(exc)}"[:255]
            )
        except Exception:
            pass
    finally:
        close_old_connections()


def _execute_distribution_worker(surat_request_id: int):
    """
    Worker asinkron untuk menjalankan:
    1. Pembelajaran memori gaya bahasa Fase 3 (`AgenticMemoryAgent.record_feedback_memory`)
       apabila Dosen melakukan koreksi pada `final_approved_content`.
    2. Distribusi dokumen akhir (`route_and_distribute_document`) ke Email / Telegram
       agar tidak memblokir HTTP response aksi approval dosen.
    """
    close_old_connections()
    try:
        surat_req = SuratRequest.objects.select_related('kode_surat').get(pk=surat_request_id)

        # Fase 3: Agentic Memory Learning (jika ada suntingan dosen terhadap draf asli AI)
        if surat_req.ai_original_draft and surat_req.final_approved_content:
            try:
                from ..agents.memory_agent import AgenticMemoryAgent

                mem_agent = AgenticMemoryAgent()
                mem_agent.record_feedback_memory(
                    surat_request=surat_req,
                    ai_original_draft=surat_req.ai_original_draft,
                    final_approved_content=surat_req.final_approved_content,
                    allow_heuristic_fallback=True,
                )
            except Exception as mem_exc:
                logger.warning(
                    "[ASYNC_MEMORY_WARN] Gagal menjalankan AgenticMemoryAgent untuk SuratRequest id=%s: %s",
                    surat_req.id,
                    mem_exc,
                )

        if not surat_req.chosen_destination or not surat_req.target_destination_address:
            logger.info(
                "[ASYNC_DIST_SKIP] Tidak ada destinasi pengiriman eksternal untuk SuratRequest id=%s.",
                surat_req.id,
            )
            return

        logger.info(f"[ASYNC_DIST_START] Memulai distribusi asinkron untuk SuratRequest id={surat_req.id}")
        
        dist_result = route_and_distribute_document(surat_req)
        if isinstance(dist_result, dict) and dist_result.get("status") == "ERROR":
            raise RuntimeError(dist_result.get("message", "Distribusi gagal."))
        
        surat_req.status = "SENT"
        surat_req.save(update_fields=["status"])
        
        SuratAuditLog.objects.create(
            surat_request=surat_req,
            action_id="DIST_SUCCESS",
            action=f"ASYNC_SENT_VIA_{str(surat_req.chosen_destination).upper()}"
        )
        logger.info(f"[ASYNC_DIST_SUCCESS] Dokumen berhasil dikirim untuk SuratRequest id={surat_req.id}")
    except Exception as exc:
        logger.exception(f"[ASYNC_DIST_ERROR] Gagal mengirim dokumen di latar belakang: {exc}")
        try:
            surat_req = SuratRequest.objects.get(pk=surat_request_id)
            surat_req.status = "DISTRIBUTION_FAILED"
            surat_req.save(update_fields=["status"])
            SuratAuditLog.objects.create(
                surat_request=surat_req,
                action_id="DIST_FAILED",
                action=f"ASYNC_FAILED: {str(exc)}"[:255]
            )
        except Exception:
            pass
    finally:
        close_old_connections()