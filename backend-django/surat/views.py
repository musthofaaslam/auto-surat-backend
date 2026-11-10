import logging
import os
import threading
from typing import Any, Dict, Optional

from django.conf import settings
from django.db import close_old_connections, models
from django.http import FileResponse, Http404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.authentication import CustomJWTAuthentication
from accounts.models import Lecturer, Student
from accounts.serializers import StandardErrorResponseSerializer

from .agents.backend_bridge import persist_attachments_for_request
from .agents.execution_tools import (
    ExecutionToolError,
    SuratExecutionTools,
)
from .agents.letter_agent import (
    SuratAgentError,
    SuratAgentRateLimitError,
    SuratAgentTimeoutError,
    SuratDraftingAgent,
)
from .agents.memory_agent import (
    AgenticMemoryAgent,
    MemoryAgentError,
)
from .models import (
    ApprovalStatus,
    SuratApproval,
    SuratAuditLog,
    SuratRequest,
    SuratStatus,
    SuratType,
    TteSignature,
    ChatThread,
    ChatMessage,
)
from .serializers import (
    ApprovalActionErrorResponseSerializer,
    LecturerApprovalActionRequestSerializer,
    LecturerApprovalActionResponseSerializer,
    SuratApprovalActionSerializer,
    SuratApprovalSerializer,
    SuratRejectActionSerializer,
    SuratRequestCreateSerializer,
    SuratRequestDetailSerializer,
    SuratRequestListSerializer,
    SuratRequestSuccessResponseSerializer,
    SuratTypeSerializer,
    SuratVerifyInvalidResponseSerializer,
    SuratVerifyValidResponseSerializer,
    ReDraftSuratRequestSerializer,
)
from .services.workflow_service import process_approval_action
from .services.manual_handlers import create_approval_workflow_for_request
from .services.session_manager import AutoSuratSessionManager

# SARAN PERBAIKAN ARSITEKTURAL:
# 1. Eksekusi `SuratDraftingAgent.draft_letter()` didelegasikan ke background worker thread
#    (`_execute_drafting_agent_worker`) agar siklus inferensi LLM dan Self-Reflection Loop
#    (5-15 detik) tidak memblokir koneksi HTTP utama pengguna (mencegah HTTP timeout).
# 2. Setiap siklus hidup background thread memanggil `close_old_connections()` pada blok
#    awal dan `finally` untuk mencegah kebocoran koneksi PostgreSQL (connection leak).
# 3. Prinsip State Pausing (Agentic AI Level 2) ditegakkan secara ketat pada Fase 1:
#    aliran eksekusi berhenti tepat setelah status mencapai `PENDING_APPROVAL` tanpa
#    memicu pembuatan Nomor Surat Resmi, TTE, QR Code, maupun unggahan PDF ke Cloudinary.
# 4. Kegagalan inferensi LLM (`SuratAgentTimeoutError`, `SuratAgentRateLimitError`, atau
#    `SuratAgentError` lainnya) ditangkap secara deterministik di dalam thread untuk
#    mengubah status `SuratRequest` menjadi `FAILED` beserta rekam jejak di `SuratAuditLog`.
# 5. Pada Fase 2 & 3 (`LecturerApprovalActionAPIView`), saat keputusan `APPROVE` final
#    diterima, naskah `final_approved_content` langsung dikunci di database, sementara
#    proses pembuatan Nomor Surat, TTE QR Code, render PDF & unggah Cloudinary
#    (`SuratExecutionTools`), serta komparasi diff gaya bahasa (`AgenticMemoryAgent`)
#    didelegasikan ke background thread (`_execute_approval_pipeline_worker`) hingga
#    status akhir diperbarui menjadi `SENT` atau `PRINTED`.

logger = logging.getLogger(__name__)


def _mark_surat_request_failed(
    surat_request_id: int,
    error_code: str,
    error_reason: str,
) -> None:
    """
    Memperbarui status SuratRequest menjadi FAILED dan mencatat alasan kegagalan
    apabila eksekusi agen atau pipeline di latar belakang mengalami kendala.
    """
    try:
        surat_req = SuratRequest.objects.filter(pk=surat_request_id).first()
        if surat_req is not None:
            existing_notes = (
                list(surat_req.revision_notes)
                if isinstance(surat_req.revision_notes, list)
                else []
            )
            existing_notes.append(error_reason)
            surat_req.status = SuratStatus.FAILED
            surat_req.revision_notes = existing_notes
            surat_req.save(update_fields=["status", "revision_notes"])

            SuratAuditLog.objects.create(
                surat_request=surat_req,
                action_id=error_code[:100],
                action=f"AI_DRAFT_FAILED: {error_reason}"[:255],
            )
    except Exception as db_exc:
        logger.error(
            "Gagal memperbarui status FAILED untuk SuratRequest id=%s: %s",
            surat_request_id,
            db_exc,
        )

def _execute_drafting_agent_worker(
    surat_request_id: int,
    user_prompt_context: str,
    kode_surat: str,
    student_metadata: Optional[Dict[str, Any]] = None,
    agent: Optional[SuratDraftingAgent] = None,
    dynamic_fields_dict: Optional[Dict[str, Any]] = None
) -> None:
    """
    Worker asinkron untuk menjalankan SuratDraftingAgent.draft_letter() di latar belakang.
    Menyimpan hasil ekstraksi Pydantic ke kolom payload_data, menyimpan draf asli AI serta
    skor evaluasi diri, lalu mengunci status pada PENDING_APPROVAL (State Pausing).
    """
    close_old_connections()
    try:
        surat_req_init = SuratRequest.objects.filter(pk=surat_request_id).first()
        initial_payload = (
            dict(surat_req_init.payload_data)
            if surat_req_init is not None and isinstance(surat_req_init.payload_data, dict) and surat_req_init.payload_data
            else None
        )

        active_agent = agent if agent is not None else SuratDraftingAgent()
        draft_output = active_agent.draft_letter(
            user_prompt_context=user_prompt_context,
            kode_surat=kode_surat,
            student_metadata=student_metadata,
            previous_payload=initial_payload,
            dynamic_fields_dict=dynamic_fields_dict,
        )

        # CARA AMAN MENGEKSTRAK PAYLOAD DARI AGEN
        if hasattr(draft_output, "to_payload_dict") and callable(draft_output.to_payload_dict):
            structured_payload: Dict[str, Any] = draft_output.to_payload_dict()
        elif hasattr(draft_output, "extracted_payload"):
            payload_obj = draft_output.extracted_payload
            if hasattr(payload_obj, "model_dump") and callable(payload_obj.model_dump):
                structured_payload = payload_obj.model_dump(mode="json")
            else:
                structured_payload = dict(payload_obj)
        elif hasattr(draft_output, "model_dump") and callable(draft_output.model_dump):
            structured_payload = draft_output.model_dump(mode="json")
        else:
            structured_payload = dict(draft_output)

        surat_req = SuratRequest.objects.get(pk=surat_request_id)
        surat_req.payload_data = structured_payload
        surat_req.ai_original_draft = draft_output.ai_original_draft
        surat_req.self_critique_score = draft_output.evaluation.self_critique_score
        surat_req.revision_notes = list(draft_output.evaluation.revision_notes)
        
        critique_score = draft_output.evaluation.self_critique_score
        has_missing_info = getattr(draft_output.evaluation, "has_missing_info", False)
        
        if critique_score < 7 or has_missing_info:
            surat_req.status = SuratStatus.REVISION_REQUIRED
            surat_req.save(
                update_fields=[
                    "payload_data",
                    "ai_original_draft",
                    "self_critique_score",
                    "revision_notes",
                    "status",
                ]
            )
            
            SuratAuditLog.objects.create(
                surat_request=surat_req,
                action_id="AI_REV_REQ",
                action="AI_DRAFTING_LOW_QUALITY_SCORE",
            )
            logger.warning(
                "SuratRequest id=%s dikembalikan karena skor evaluasi diri AI terlalu rendah atau data belum lengkap (Skor: %s).",
                surat_request_id,
                critique_score,
            )
            return

        # STATE PAUSING: Ubah status ke PENDING_APPROVAL dan hentikan alur eksekusi.
        # DILARANG memanggil fungsi pembuatan Nomor Surat, TTE, QR Code, atau Cloudinary.
        surat_req.status = SuratStatus.PENDING_APPROVAL
        surat_req.save(
            update_fields=[
                "payload_data",
                "ai_original_draft",
                "self_critique_score",
                "revision_notes",
                "status",
            ]
        )

        create_approval_workflow_for_request(surat_req, surat_req.student)
        
        SuratAuditLog.objects.create(
            surat_request=surat_req,
            action_id="AI_02",
            action="AI_DRAFT_COMPLETED_PENDING_APPROVAL",
        )
        logger.info(
            "Penyusunan draf surat selesai untuk SuratRequest id=%s (status=%s, skor=%s).",
            surat_request_id,
            surat_req.status,
            surat_req.self_critique_score,
        )
    except (SuratAgentTimeoutError, SuratAgentRateLimitError) as exc:
        logger.error(
            "Kegagalan Timeout/RateLimit LLM pada SuratRequest id=%s (%s): %s",
            surat_request_id,
            type(exc).__name__,
            exc,
        )
        _mark_surat_request_failed(
            surat_request_id=surat_request_id,
            error_code="AI_ERR_LIMIT",
            error_reason=f"{type(exc).__name__}: {exc}",
        )
    except SuratAgentError as exc:
        logger.error(
            "Kesalahan operasional SuratDraftingAgent pada SuratRequest id=%s (%s): %s",
            surat_request_id,
            type(exc).__name__,
            exc,
        )
        _mark_surat_request_failed(
            surat_request_id=surat_request_id,
            error_code="AI_ERR_AGENT",
            error_reason=f"{type(exc).__name__}: {exc}",
        )
    except Exception as exc:
        logger.exception(
            "Kesalahan tak terduga saat menyusun draf surat pada SuratRequest id=%s: %s",
            surat_request_id,
            exc,
        )
        _mark_surat_request_failed(
            surat_request_id=surat_request_id,
            error_code="AI_ERR_UNEXPECTED",
            error_reason=f"{type(exc).__name__}: {exc}",
        )
    finally:
        close_old_connections()


def _execute_redraft_agent_worker(
    surat_request_id: int,
    user_prompt_context: str,
    kode_surat: str,
    previous_draft: str,
    previous_payload: dict,
    previous_score: int,
    revision_notes: list,
    student_metadata: dict,
    agent: Optional[SuratDraftingAgent] = None,
) -> None:
    """
    Worker asinkron untuk memproses ulang penyusunan draf surat (Self-Reflection Re-draft)
    ketika pengguna memberikan informasi tambahan berdasarkan revision_notes.
    """
    close_old_connections()
    try:
        surat_req = SuratRequest.objects.get(pk=surat_request_id)
        
        active_agent = agent if agent is not None else SuratDraftingAgent()
        # Memanggil fungsi revisi iteratif agen
        draft_output = active_agent.draft_letter_with_reflection(
            user_prompt_context=user_prompt_context,
            kode_surat=kode_surat,
            previous_draft=previous_draft,
            previous_payload=previous_payload,
            previous_score=previous_score,
            revision_notes=revision_notes,
            student_metadata=student_metadata,
        )

        from .agents import evaluate_draft_readiness, ensure_approval_queue_for_request

        # Evaluasi kelengkapan draf dinamis untuk ke-10 jenis surat menggunakan evaluator resmi modul agen
        readiness = evaluate_draft_readiness(
            draft_output=draft_output,
            kode_surat=kode_surat,
            agent=active_agent,
        )

        surat_req.payload_data = readiness["structured_payload"]
        surat_req.ai_original_draft = getattr(draft_output, "ai_original_draft", "")
        surat_req.self_critique_score = readiness["critique_score"]
        surat_req.revision_notes = readiness["revision_notes"]

        if readiness["is_ready_for_approval"]:
            surat_req.status = SuratStatus.PENDING_APPROVAL
            action_code = "AI_REDRAFT_SUCCESS_PENDING_APPROVAL"
        else:
            surat_req.status = SuratStatus.REVISION_REQUIRED
            action_code = "AI_REDRAFT_STILL_INCOMPLETE"

        surat_req.save(
            update_fields=[
                "payload_data",
                "ai_original_draft",
                "self_critique_score",
                "revision_notes",
                "status",
            ]
        )

        if surat_req.status == SuratStatus.PENDING_APPROVAL:
            create_approval_workflow_for_request(surat_req, surat_req.student)
            ensure_approval_queue_for_request(surat_req)

        SuratAuditLog.objects.create(
            surat_request=surat_req,
            action_id="AI_02",
            action=action_code,
        )
        logger.info(
            "Re-draft surat selesai untuk SuratRequest id=%s (status=%s, skor=%s).",
            surat_request_id,
            surat_req.status,
            surat_req.self_critique_score,
        )
    except Exception as exc:
        logger.exception(
            "Kesalahan saat re-draft surat pada SuratRequest id=%s: %s",
            surat_request_id,
            exc,
        )
        _mark_surat_request_failed(
            surat_request_id=surat_request_id,
            error_code="AI_REDRAFT_ERR",
            error_reason=f"{type(exc).__name__}: {exc}",
        )
    finally:
        close_old_connections()

class ChatThreadCreateAPIView(APIView):
    """
    Endpoint untuk menginisialisasi atau membuat sesi thread chat baru bagi mahasiswa.
    POST /api/surat/chat/init/
    """
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [CustomJWTAuthentication]

    def post(self, request):
        title = request.data.get("title", "Permohonan Surat Baru")
        document_type = request.data.get("document_type", None)

        # Buat thread baru yang terikat otomatis ke user yang sedang login via JWT
        thread = ChatThread.objects.create(
            user=request.user,
            title=title,
            document_type=document_type,
            status=ChatThread.ThreadStatus.ACTIVE
        )

        AutoSuratSessionManager.save_session(
            thread_id=str(thread.id),
            state="COLLECTING_SLOTS",  # State awal penampungan slot/intent
            intent=document_type,       # Jika document_type dikirim dari frontend, jadikan intent awal
            slots={},
            missing_slots=[]
        )
        
        return Response({
            "status": "success",
            "message": "Sesi chat (thread) berhasil diinisialisasi.",
            "initial_message": "Halo, saya adalah Asisten AI yang akan membantu Anda menyusun dokumen dan surat resmi. Silakan deskripsikan jenis surat yang ingin Anda buat beserta detail keperluannya.",
            "thread_id": str(thread.id),
            "title": thread.title,
            "document_type": thread.document_type,
            "created_at": thread.created_at
        }, status=status.HTTP_201_CREATED)
class ChatSessionMessageAPIView(APIView):
    """
    Endpoint untuk memproses pesan obrolan mahasiswa secara interaktif.
    Menggunakan AutoSuratSessionManager (Redis) + Chat Workflow Service 
    untuk Intent Detection (Lapis 1 & 2), State Locking, dan Accumulative Slot Filling.
    Mendukung input pesan teks maupun berkas lampiran multimodal.
    POST /api/surat/chat/<str:thread_id>/
    """
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [CustomJWTAuthentication]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, thread_id):
        user_msg = request.data.get("message", "").strip()
        attachment_files = request.FILES.getlist('attachments')

        if not user_msg and not attachment_files:
            return Response(
                {"status": "error", "message": "Pesan atau berkas lampiran tidak boleh kosong."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 1. Pastikan thread milik user yang sedang login
        thread = ChatThread.objects.filter(id=thread_id, user=request.user).first()
        if not thread:
            return Response(
                {"status": "error", "message": "Sesi chat atau thread tidak ditemukan."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Ekstrak berkas multimodal jika terdapat berkas lampiran
        multimodal_parts = []
        if attachment_files:
            try:
                multimodal_parts = persist_attachments_for_request(None, attachment_files)
            except Exception as exc:
                logger.warning("Gagal mengekstrak berkas lampiran multimodal: %s", exc)

        if not user_msg and attachment_files:
            file_names = ", ".join(getattr(f, "name", "berkas") for f in attachment_files)
            user_msg = f"Berikut dokumen lampiran pendukung yang saya unggah: {file_names}"

        # 2. Jalankan AutoSuratSessionManager untuk menangani pesan masuk, 
        # pembatalan global (pilar 5), TTL Redis, dan pencatatan riwayat ke PostgreSQL (ChatMessage).
        reply_message = AutoSuratSessionManager.handle_incoming_message(
            thread_id=str(thread.id),
            user_message=user_msg,
            user_obj=request.user,
            attachments=multimodal_parts or attachment_files,
        )

        # 3. Ambil kembali state terbaru dari Redis setelah diproses
        session_data = AutoSuratSessionManager.get_session(str(thread.id))
        
        if session_data.get("state") in ["CANCELLED", "EXPIRED"]:
            return Response({
                "status": "success",
                "state": session_data["state"],
                "reply": reply_message
            }, status=status.HTTP_200_OK)

        intent = session_data.get("intent") # Kode surat aktif (misal: "SI-MAG")
        slots = session_data.get("slots", {})
        waiting_confirmation = session_data.get("is_waiting_for_switch_confirmation", False)

        # Ambil daftar required_fields dari database Supabase (SuratType) atau fallback required_field_surat.json
        from .services.chat_workflow import get_effective_required_fields

        required_fields = []
        if intent:
            try:
                surat_type_obj = SuratType.objects.get(kode_surat=intent)
                required_fields = get_effective_required_fields(surat_type_obj)
            except SuratType.DoesNotExist:
                pass

        # 4. Jika semua required fields sudah lengkap, berikan sinyal ke frontend 
        # bahwa sesi siap diconvert menjadi SuratRequest (Fase Drafting Agent).
        main_slots_complete = bool(intent and required_fields) and all(
            item.get("field") in slots and bool(slots[item.get("field")])
            for item in required_fields
        )

        surat_is_complete = (
            not waiting_confirmation
            and main_slots_complete
            and bool(slots.get("chosen_destination"))
            and bool(slots.get("target_destination_address"))
        )

        waiting_clarification = session_data.get("is_waiting_for_intent_clarification", False)
        candidate_intents = session_data.get("candidate_intents", [])

        action_required = None
        action_options = []
        if waiting_confirmation:
            action_required = "switch_confirmation"
            action_options = [
                {"label": "Ya, Beralih Surat", "value": "Ya"},
                {"label": "Tidak, Lanjutkan Sebelumnya", "value": "Tidak"}
            ]
        elif waiting_clarification and candidate_intents:
            action_required = "intent_clarification"
            for c in candidate_intents:
                try:
                    surat_type_obj = SuratType.objects.get(kode_surat=c)
                    lbl = f"{surat_type_obj.nama_surat} ({c})"
                except Exception:
                    lbl = c
                action_options.append({"label": lbl, "value": c})
        elif main_slots_complete and not slots.get("chosen_destination"):
            action_required = "delivery_method"
            action_options = [
                {"label": "Email", "value": "Email"},
                {"label": "Telegram", "value": "Telegram"}
            ]

        missing_fields = [
            item.get("field") for item in required_fields
            if not (item.get("field") in slots and bool(slots[item.get("field")]))
        ] if required_fields else []

        if surat_is_complete:
            return Response({
                "status": "ready_to_draft",
                "state": "READY_TO_DRAFT",
                "is_ready_to_draft": True,
                "action_required": None,
                "action_options": [],
                "intent": intent,
                "detected_intent": intent,
                "kode_surat": intent,
                "is_waiting_for_switch_confirmation": False,
                "collected_slots": slots,
                "missing_fields": [],
                "required_fields": required_fields,
                "reply": reply_message
            }, status=status.HTTP_200_OK)

        # 5. Kembalikan balasan interaktif normal ke frontend (menampilkan checklist / tagihan field berikutnya)
        return Response({
            "status": "success",
            "state": "COLLECTING_SLOTS",
            "is_ready_to_draft": False,
            "action_required": action_required,
            "action_options": action_options,
            "intent": intent,
            "detected_intent": intent,
            "kode_surat": intent,
            "is_waiting_for_switch_confirmation": waiting_confirmation,
            "is_waiting_for_intent_clarification": waiting_clarification,
            "reply": reply_message,
            "collected_slots": slots,
            "missing_fields": missing_fields,
            "required_fields": required_fields
        }, status=status.HTTP_200_OK)

    def get(self, request, thread_id):
        """
        Mengambil detail status, riwayat pesan, dan snapshot slot dari sesi chat tertentu.
        GET /api/surat/chat/<str:thread_id>/
        """
        thread = ChatThread.objects.filter(id=thread_id, user=request.user).first()
        if not thread:
            return Response(
                {"status": "error", "message": "Sesi chat atau thread tidak ditemukan."},
                status=status.HTTP_404_NOT_FOUND
            )

        session_data = AutoSuratSessionManager.get_session(str(thread.id))
        intent = session_data.get("intent") or thread.document_type
        slots = session_data.get("slots", {})
        waiting_confirmation = session_data.get("is_waiting_for_switch_confirmation", False)

        from .services.chat_workflow import get_effective_required_fields
        required_fields = []
        if intent:
            try:
                surat_type_obj = SuratType.objects.get(kode_surat=intent)
                required_fields = get_effective_required_fields(surat_type_obj)
            except SuratType.DoesNotExist:
                pass

        main_slots_complete = bool(intent and required_fields) and all(
            item.get("field") in slots and bool(slots[item.get("field")])
            for item in required_fields
        )

        surat_is_complete = (
            not waiting_confirmation
            and main_slots_complete
            and bool(slots.get("chosen_destination"))
            and bool(slots.get("target_destination_address"))
        )

        waiting_clarification = session_data.get("is_waiting_for_intent_clarification", False)
        candidate_intents = session_data.get("candidate_intents", [])

        action_required = None
        action_options = []
        if waiting_confirmation:
            action_required = "switch_confirmation"
            action_options = [
                {"label": "Ya, Beralih Surat", "value": "Ya"},
                {"label": "Tidak, Lanjutkan Sebelumnya", "value": "Tidak"}
            ]
        elif waiting_clarification and candidate_intents:
            action_required = "intent_clarification"
            for c in candidate_intents:
                try:
                    surat_type_obj = SuratType.objects.get(kode_surat=c)
                    lbl = f"{surat_type_obj.nama_surat} ({c})"
                except Exception:
                    lbl = c
                action_options.append({"label": lbl, "value": c})
        elif main_slots_complete and not slots.get("chosen_destination"):
            action_required = "delivery_method"
            action_options = [
                {"label": "Email", "value": "Email"},
                {"label": "Telegram", "value": "Telegram"}
            ]

        missing_fields = [
            item.get("field") for item in required_fields
            if not (item.get("field") in slots and bool(slots[item.get("field")]))
        ] if required_fields else []

        messages = ChatMessage.objects.filter(thread=thread).order_by('created_at')
        formatted_messages = [
            {
                "id": str(msg.id),
                "sender": msg.sender,
                "text": msg.message,
                "timestamp": msg.created_at.strftime("%H:%M") if msg.created_at else "",
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
            }
            for msg in messages
        ]

        state = "READY_TO_DRAFT" if surat_is_complete else session_data.get("state", "COLLECTING_SLOTS")
        status_str = "ready_to_draft" if surat_is_complete else "success"

        return Response({
            "status": status_str,
            "state": state,
            "is_ready_to_draft": surat_is_complete,
            "action_required": action_required,
            "action_options": action_options,
            "is_waiting_for_switch_confirmation": waiting_confirmation,
            "is_waiting_for_intent_clarification": waiting_clarification,
            "thread_id": str(thread.id),
            "title": thread.title,
            "intent": intent,
            "detected_intent": intent,
            "kode_surat": intent,
            "collected_slots": slots,
            "missing_fields": missing_fields,
            "required_fields": required_fields,
            "messages": formatted_messages,
        }, status=status.HTTP_200_OK)
                        
class SuratRequestRedraftAPIView(APIView):
    """
    Endpoint bagi mahasiswa untuk memberikan informasi tambahan / revisi 
    pada surat yang berstatus REVISION_REQUIRED atau FAILED.
    POST / PATCH /api/surat/requests/<int:pk>/re-draft/
    """
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [CustomJWTAuthentication]
    parser_classes = [JSONParser, FormParser, MultiPartParser]
    agent_instance: Optional[SuratDraftingAgent] = None
    _last_worker_thread: Optional[threading.Thread] = None

    def get_drafting_agent(self) -> Optional[SuratDraftingAgent]:
        return self.agent_instance

    @extend_schema(
        summary="Perbarui Draf Surat Berdasarkan Catatan Revisi (Mahasiswa)",
        description=(
            "Digunakan mahasiswa untuk mengirimkan informasi tambahan guna melengkapi "
            "draf surat yang sebelumnya berstatus REVISION_REQUIRED. "
            "Agen AI akan memproses ulang draf dengan menggabungkan konteks lama dan koreksi baru."
        ),
        request=ReDraftSuratRequestSerializer,
        responses={
            202: SuratRequestSuccessResponseSerializer,
            400: StandardErrorResponseSerializer,
            403: StandardErrorResponseSerializer,
            404: StandardErrorResponseSerializer,
        },
    )
    def post(self, request, pk=None):
        try:
            student_obj = request.user.student_profile
        except (Student.DoesNotExist, AttributeError):
            return Response(
                {
                    "status": "error",
                    "message": "Validasi gagal",
                    "errors": "Bukan akun mahasiswa. Hanya mahasiswa yang dapat merevisi surat.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            surat_req = SuratRequest.objects.select_related("kode_surat", "student").get(pk=pk)
        except SuratRequest.DoesNotExist:
            return Response(
                {
                    "status": "error",
                    "message": "Data tidak ditemukan",
                    "errors": "Permohonan surat tidak ditemukan.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if surat_req.student != student_obj:
            return Response(
                {
                    "status": "error",
                    "message": "Akses ditolak",
                    "errors": "Anda tidak memiliki hak akses untuk merevisi permohonan surat ini.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if surat_req.status not in (SuratStatus.REVISION_REQUIRED, SuratStatus.FAILED):
            return Response(
                {
                    "status": "error",
                    "message": "Status tidak valid untuk revisi",
                    "errors": (
                        f"Permohonan surat saat ini berstatus '{surat_req.status}'. "
                        "Hanya surat dengan status REVISION_REQUIRED atau FAILED yang dapat direvisi."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ReDraftSuratRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "status": "error",
                    "message": "Validasi gagal",
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        additional_context = serializer.validated_data["additional_prompt_context"]
        combined_prompt = (
            f"{surat_req.user_prompt_context or ''}\n\n"
            f"[Tambahan Informasi Revisi Mahasiswa]: {additional_context}"
        ).strip()

        previous_draft = surat_req.ai_original_draft or ""
        previous_payload = dict(surat_req.payload_data or {})
        raw_new_payload = serializer.validated_data.get("payload_data")
        if isinstance(raw_new_payload, dict) and raw_new_payload:
            previous_payload.update(raw_new_payload)
        previous_score = int(surat_req.self_critique_score or 0)
        revision_notes = list(surat_req.revision_notes or [])

        student_metadata = {
            "nim": student_obj.nim,
            "nama": getattr(student_obj.user, "nama", ""),
            "prodi": getattr(student_obj.prodi, "nama_prodi", ""),
            "fakultas": getattr(student_obj.fakultas, "nama_fakultas", ""),
            "semester_aktif": student_obj.semester_aktif,
            "tahun_akademik": student_obj.tahun_akademik,
        }

        surat_req.user_prompt_context = combined_prompt
        surat_req.payload_data = previous_payload
        surat_req.status = SuratStatus.SUBMITTED
        surat_req.save(update_fields=["user_prompt_context", "payload_data", "status"])

        SuratAuditLog.objects.create(
            surat_request=surat_req,
            action_id="AI_REDRAFT_REQ",
            action="SURAT_REDRAFT_SUBMITTED_BY_STUDENT",
        )

        worker_thread = threading.Thread(
            target=_execute_redraft_agent_worker,
            kwargs={
                "surat_request_id": surat_req.id,
                "user_prompt_context": additional_context,
                "kode_surat": surat_req.kode_surat.kode_surat,
                "previous_draft": previous_draft,
                "previous_payload": previous_payload,
                "previous_score": previous_score,
                "revision_notes": revision_notes,
                "student_metadata": student_metadata,
                "agent": self.get_drafting_agent(),
            },
            name=f"surat-redraft-agent-{surat_req.id}",
            daemon=True,
        )
        SuratRequestRedraftAPIView._last_worker_thread = worker_thread
        worker_thread.start()

        return Response(
            {
                "status": "success",
                "message": (
                    f"Revisi permohonan surat {surat_req.kode_surat.nama_surat} berhasil diterima dan sedang "
                    "diproses ulang secara asinkron oleh agen AI."
                ),
                "request_id": surat_req.id,
                "surat_status": surat_req.status,
                "data": {
                    "request_id": surat_req.id,
                    "kode_surat": surat_req.kode_surat.kode_surat,
                    "status": surat_req.status,
                },
            },
            status=status.HTTP_202_ACCEPTED,
        )

    def patch(self, request, pk=None):
        return self.post(request, pk=pk)

class SuratTypeListAPIView(ListAPIView):
    """
    Endpoint untuk melihat daftar jenis surat yang tersedia (untuk dropdown form frontend).
    GET /api/surat/types/
    """
    queryset = SuratType.objects.all()
    serializer_class = SuratTypeSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly] 

class SuratRequestCreateAPIView(APIView):
    """
    Endpoint bagi mahasiswa untuk mengajukan surat baru berbasis Agentic AI (Fase 1).
    Menerima kode_surat serta konteks permohonan, membuat record awal dengan status SUBMITTED,
    dan menjalankan SuratDraftingAgent.draft_letter() secara asinkron di latar belakang
    hingga mencapai status PENDING_APPROVAL (State Pausing).
    POST /api/surat/request/
    """
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [CustomJWTAuthentication]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    agent_instance: Optional[SuratDraftingAgent] = None
    _last_worker_thread: Optional[threading.Thread] = None

    def get_drafting_agent(self) -> Optional[SuratDraftingAgent]:
        """
        Mengembalikan instance SuratDraftingAgent kustom apabila disuntikkan (misal pada pengujian),
        atau None agar worker menginisialisasi instance baru di dalam background thread.
        """
        return self.agent_instance

    @extend_schema(
        summary="Ajukan Surat Baru (Mahasiswa)",
        description=(
            "Digunakan mahasiswa untuk mengajukan permohonan pembuatan surat. "
            "Mendukung pengiriman konteks bahasa alami (user_prompt_context / konteks) "
            "dan payload dinamis. Pembuatan draf dieksekusi secara asinkron di latar belakang "
            "oleh SuratDraftingAgent dan berhenti pada status PENDING_APPROVAL (State Pausing)."
        ),
        request=SuratRequestCreateSerializer,
        responses={
            201: SuratRequestSuccessResponseSerializer,
            202: SuratRequestSuccessResponseSerializer,
            400: StandardErrorResponseSerializer,
            403: StandardErrorResponseSerializer,
            404: StandardErrorResponseSerializer,
        },
    )
    def post(self, request):
        try:
            student_obj = request.user.student_profile
        except (Student.DoesNotExist, AttributeError):
            return Response(
                {
                    "status": "error",
                    "message": "Validasi gagal",
                    "errors": "bukan akun mahasiswa. Hanya mahasiswa yang dapat mengajukan surat.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        raw_kode_surat = request.data.get("kode_surat")
        if isinstance(raw_kode_surat, str) and raw_kode_surat.strip():
            try:
                surat_type = SuratType.objects.get(kode_surat=raw_kode_surat.strip())
            except SuratType.DoesNotExist:
                return Response(
                    {
                        "status": "error",
                        "message": "Validasi gagal",
                        "errors": "Jenis surat tidak ditemukan.",
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            surat_type = None

        serializer = SuratRequestCreateSerializer(
            data=request.data,
            context={"request": request},
        )
        if not serializer.is_valid():
            return Response(
                {
                    "status": "error",
                    "message": "Validasi gagal",
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        kode_surat_str = serializer.validated_data["kode_surat"]
        if surat_type is None:
            try:
                surat_type = SuratType.objects.get(kode_surat=kode_surat_str)
            except SuratType.DoesNotExist:
                return Response(
                    {
                        "status": "error",
                        "message": "Validasi gagal",
                        "errors": "Jenis surat tidak ditemukan.",
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

        user_prompt_context = serializer.validated_data.get("user_prompt_context", "")
        initial_payload = serializer.validated_data.get("payload_data") or {}

        student_metadata = {
                    "nim": student_obj.nim,
                    "nama": getattr(student_obj.user, "nama", ""),
                    "prodi": getattr(student_obj.prodi, "nama_prodi", ""),
                    "fakultas": getattr(student_obj.fakultas, "nama_fakultas", ""),
                    "semester_aktif": student_obj.semester_aktif,
                    "tahun_akademik": student_obj.tahun_akademik,
                }
        
        agent = self.get_drafting_agent() or SuratDraftingAgent()
        # State Pausing: Buat rekam data awal dengan status SUBMITTED tanpa memicu
        # pembuatan Nomor Surat, TTE, QR Code, atau unggahan Cloudinary.
        chosen_destination = serializer.validated_data.get("chosen_destination") or request.data.get("chosen_destination")
        target_destination_address = serializer.validated_data.get("target_destination_address") or request.data.get("target_destination_address")
        # State Pausing: Buat rekam data awal dengan status SUBMITTED serta simpan preferensi tujuannya
        surat_req = SuratRequest.objects.create(
            student=student_obj,
            kode_surat=surat_type,
            status=SuratStatus.SUBMITTED,
            payload_data=initial_payload,
            user_prompt_context=user_prompt_context,
            chosen_destination=chosen_destination,
            target_destination_address=target_destination_address,
        )

        SuratAuditLog.objects.create(
            surat_request=surat_req,
            action_id="AI_01",
            action="SURAT_SUBMITTED_FOR_AI_DRAFTING",
        )

        # Ambil field dinamis yang tersimpan di kolom/atribut jenis surat (sesuaikan nama field modelnya, misal: required_fields_dict)
        dynamic_fields_dict = getattr(surat_type, "required_fields_dict", None)

        first_approval = SuratApproval.objects.filter(surat_request=surat_req).order_by('step_order').first()
        approval_id = first_approval.id if first_approval else None
        
        worker_thread = threading.Thread(
            target=_execute_drafting_agent_worker,
            kwargs={
                "surat_request_id": surat_req.id,
                "user_prompt_context": user_prompt_context,
                "kode_surat": surat_type.kode_surat,
                "student_metadata": student_metadata,
                "agent": self.get_drafting_agent(),
                "dynamic_fields_dict": dynamic_fields_dict,
            },
            name=f"surat-drafting-agent-{surat_req.id}",
            daemon=True,
        )
        SuratRequestCreateAPIView._last_worker_thread = worker_thread
        worker_thread.start()

        return Response(
            {
                "status": "success",
                "message": (
                    f"Permohonan surat {surat_type.nama_surat} berhasil diterima dan sedang "
                    "diproses secara asinkron oleh agen AI."
                ),
                "request_id": surat_req.id,
                "surat_status": surat_req.status,
                "data": {
                    "request_id": surat_req.id,
                    "kode_surat": surat_type.kode_surat,
                    "status": surat_req.status,
                    "approval_id": approval_id, 
                },
            },
            status=status.HTTP_202_ACCEPTED,
        )


class SuratRequestListAPIView(ListAPIView):
    """
    Endpoint untuk melihat daftar riwayat pengajuan surat milik mahasiswa yang sedang login
    (atau surat di lingkup wewenang Dosen/Pejabat).
    GET /api/surat/requests/
    """
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [CustomJWTAuthentication]
    serializer_class = SuratRequestListSerializer

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'student_profile'):
            return SuratRequest.objects.filter(student=user.student_profile).order_by('-created_at')
        if hasattr(user, 'lecturer_profile'):
            lecturer = user.lecturer_profile

            # Perluasan visibilitas antrean khusus akun demo Dr. Joel Evans, M.T. (lintas fakultas)
            demo_enabled = getattr(settings, 'DEMO_ONE_STEP_APPROVAL', True)
            demo_target_surat = getattr(settings, 'DEMO_TARGET_SURAT', ['SR-MAG', 'SR-BEA'])
            demo_approver_nip = getattr(settings, 'DEMO_APPROVER_NIP', '198001012005011001')
            is_demo_lecturer = (
                getattr(user, 'nip_nim', None) == demo_approver_nip
                or "Joel Evans" in getattr(user, 'nama', '')
            )
            if demo_enabled and is_demo_lecturer:
                demo_filter = models.Q(kode_surat__in=demo_target_surat)
                if lecturer.fakultas:
                    demo_filter |= models.Q(student__fakultas=lecturer.fakultas)
                else:
                    demo_filter |= models.Q(approvals__approver=lecturer)
                return (
                    SuratRequest.objects.filter(demo_filter)
                    .order_by('-created_at')
                    .distinct()
                )

            if lecturer.fakultas:
                return (
                    SuratRequest.objects.filter(student__fakultas=lecturer.fakultas)
                    .order_by('-created_at')
                    .distinct()
                )
            return (
                SuratRequest.objects.filter(approvals__approver=lecturer)
                .order_by('-created_at')
                .distinct()
            )
        if getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False) or getattr(user, 'role', '') == 'ADMIN':
            return SuratRequest.objects.all().order_by('-created_at')
        return SuratRequest.objects.none()


class SuratRequestDetailAPIView(RetrieveAPIView):
    """
    Endpoint untuk melihat detail lengkap suatu pengajuan surat beserta status TTE & Approval.
    Dilengkapi proteksi kepemilikan (anti-IDOR) agar mahasiswa hanya dapat mengakses surat miliknya sendiri.
    GET /api/surat/requests/<int:pk>/
    """
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [CustomJWTAuthentication]
    serializer_class = SuratRequestDetailSerializer

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'student_profile'):
            return SuratRequest.objects.filter(student=user.student_profile)
        if hasattr(user, 'lecturer_profile'):
            lecturer = user.lecturer_profile

            # Perluasan akses detail khusus akun demo Dr. Joel Evans, M.T. (lintas fakultas)
            demo_enabled = getattr(settings, 'DEMO_ONE_STEP_APPROVAL', True)
            demo_target_surat = getattr(settings, 'DEMO_TARGET_SURAT', ['SR-MAG', 'SR-BEA'])
            demo_approver_nip = getattr(settings, 'DEMO_APPROVER_NIP', '198001012005011001')
            is_demo_lecturer = (
                getattr(user, 'nip_nim', None) == demo_approver_nip
                or "Joel Evans" in getattr(user, 'nama', '')
            )
            if demo_enabled and is_demo_lecturer:
                demo_filter = models.Q(kode_surat__in=demo_target_surat)
                if lecturer.fakultas:
                    demo_filter |= models.Q(student__fakultas=lecturer.fakultas)
                else:
                    demo_filter |= models.Q(approvals__approver=lecturer)
                return SuratRequest.objects.filter(demo_filter).distinct()

            if lecturer.fakultas:
                return SuratRequest.objects.filter(student__fakultas=lecturer.fakultas).distinct()
            return SuratRequest.objects.filter(approvals__approver=lecturer).distinct()
        if getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False) or getattr(user, 'role', '') == 'ADMIN':
            return SuratRequest.objects.all()
        return SuratRequest.objects.none()


class LecturerApprovalActionAPIView(APIView):
    """
    Endpoint bagi Dosen/Pejabat untuk menyetujui (APPROVE) atau menolak (REJECT) antrean surat.
    Mendelegasikan seluruh eksekusi bisnis persetujuan, nomor, TTE, PDF, dan Fase 3 Memory Agent
    ke `process_approval_action`.
    
    POST /api/surat/approval/<int:approval_id>/action/
    """
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [CustomJWTAuthentication]
    _last_worker_thread: Optional[threading.Thread] = None

    @extend_schema(
        summary="Tindakan Persetujuan atau Penolakan Surat (Dosen/Pejabat)",
        description=(
            "Digunakan oleh Dosen atau Pejabat berwenang untuk menyetujui (APPROVE) "
            "atau menolak (REJECT) antrean pengajuan surat secara manual."
        ),
        request=LecturerApprovalActionRequestSerializer,
        responses={
            200: LecturerApprovalActionResponseSerializer,
            400: ApprovalActionErrorResponseSerializer,
            403: ApprovalActionErrorResponseSerializer,
            404: ApprovalActionErrorResponseSerializer,
        },
    )
    def post(self, request, approval_id):
        action = request.data.get("action")
        if action not in ["APPROVE", "REJECT"]:
            return Response(
                {"error": "Aksi harus bernilai 'APPROVE' atau 'REJECT'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            lecturer_obj = request.user.lecturer_profile
        except (Lecturer.DoesNotExist, AttributeError):
            return Response(
                {"error": "Anda tidak memiliki hak akses sebagai pejabat pemberi persetujuan."},
                status=status.HTTP_403_FORBIDDEN,
            )

        catatan = ""
        final_approved_content = None
        final_status = "PRINTED"
        if action == "APPROVE":
            serializer = SuratApprovalActionSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            catatan = serializer.validated_data.get("catatan") or ""
            final_approved_content = serializer.validated_data.get("final_approved_content")
            final_status = serializer.validated_data.get("final_status") or "PRINTED"
        elif action == "REJECT":
            serializer = SuratRejectActionSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            catatan = serializer.validated_data["alasan_penolakan"]

        # Validasi kepemilikan approval step sebelum dilempar ke service
        try:
            approval_step = SuratApproval.objects.select_related('approver', 'surat_request__kode_surat').get(id=approval_id)
        except SuratApproval.DoesNotExist:
            return Response({"error": "Antrean approval tidak ditemukan."}, status=status.HTTP_404_NOT_FOUND)

        demo_enabled = getattr(settings, 'DEMO_ONE_STEP_APPROVAL', True)
        demo_target_surat = getattr(settings, 'DEMO_TARGET_SURAT', ['SR-MAG', 'SR-BEA'])
        demo_approver_nip = getattr(settings, 'DEMO_APPROVER_NIP', '198001012005011001')
        is_demo_bypass = (
            demo_enabled
            and getattr(getattr(approval_step, 'surat_request', None), 'kode_surat_id', None) in demo_target_surat
            and (
                getattr(request.user, 'nip_nim', None) == demo_approver_nip
                or "Joel Evans" in getattr(request.user, 'nama', '')
            )
        )

        if not is_demo_bypass and approval_step.approver != lecturer_obj:
            return Response({"error": "Anda tidak memiliki hak akses untuk menyetujui antrean ini."}, status=status.HTTP_403_FORBIDDEN)

        # Panggil fungsi service utama yang sudah rapi beserta koreksi draf dosen
        result_data, http_code = process_approval_action(
            approval_id=approval_id,
            lecturer=lecturer_obj,
            action=action,
            catatan=catatan,
            final_approved_content=final_approved_content,
            final_status=final_status,
        )

        from .services import workflow_service
        LecturerApprovalActionAPIView._last_worker_thread = getattr(
            workflow_service, "_last_issuance_worker_thread", None
        )

        return Response(result_data, status=http_code)


class SuratVerifyAPIView(APIView):
    """
    Endpoint publik untuk memverifikasi keaslian surat via QR Code / Token TTE.
    GET /api/surat/verify/<str:token>/
    """
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        summary="Verifikasi Keaslian Dokumen Surat Publik (QR Code / Token TTE)",
        description=(
            "Endpoint publik tanpa autentikasi untuk memverifikasi keabsahan surat resmi "
            "berdasarkan token tanda tangan elektronik (TTE) yang tertera pada QR Code."
        ),
        responses={
            200: SuratVerifyValidResponseSerializer,
            404: SuratVerifyInvalidResponseSerializer,
        },
    )
    def get(self, request, token):
        try:
            tte_sig = TteSignature.objects.select_related(
                'surat_request',
                'surat_request__student',
                'surat_request__student__user',
                'surat_request__student__prodi',
                'surat_request__student__fakultas',
                'surat_request__kode_surat',
                'signer__user'
            ).get(token=token)
        except TteSignature.DoesNotExist:
            return Response({
                "status": "INVALID",
                "message": "Dokumen Surat TIDAK VALID atau palsu. Token verifikasi tidak ditemukan di sistem."
            }, status=status.HTTP_404_NOT_FOUND)

        surat_req = tte_sig.surat_request
        student = surat_req.student

        return Response({
            "status": "VALID",
            "message": "Dokumen Surat ASLI dan terdaftar secara resmi di sistem kampus.",
            "detail_surat": {
                "nomor_surat_resmi": surat_req.nomor_surat_resmi,
                "jenis_surat": surat_req.kode_surat.nama_surat,
                "kategori": surat_req.kode_surat.kategori,
                "tanggal_terbit": surat_req.created_at,
            },
            "mahasiswa": {
                "nim": student.nim,
                "nama": student.user.nama,
                "prodi": student.prodi.nama_prodi,
                "fakultas": student.fakultas.nama_fakultas,
            },
            "tte_info": {
                "hash_sha256": tte_sig.hash_document,
                "penandatangan": tte_sig.signer.user.nama if tte_sig.signer else "Sistem Otomatis Kampus",
                "tanggal_ttd": tte_sig.created_at
            }
        }, status=status.HTTP_200_OK)


class SuratPreviewPdfAPIView(APIView):
    """
    Endpoint internal gateway untuk pratinjau dokumen PDF resmi (Zero-Cloudinary dependency).
    Mendukung penayangan langsung di iframe peramban tanpa terhalang 401 Cloudinary atau CORS.
    GET /surat/requests/<int:pk>/preview-pdf/
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, pk: int):
        try:
            surat_req = SuratRequest.objects.select_related(
                'student',
                'student__user',
                'student__prodi',
                'student__fakultas',
                'kode_surat',
            ).get(pk=pk)
        except SuratRequest.DoesNotExist:
            raise Http404("Surat tidak ditemukan.")

        pdf_dir = os.path.join(settings.BASE_DIR, "media", "generated_pdf")
        os.makedirs(pdf_dir, exist_ok=True)

        nomor_clean = str(surat_req.nomor_surat_resmi or f"req_{pk}").replace("/", "_")
        possible_files = [
            os.path.join(pdf_dir, f"surat_{pk}.pdf"),
            os.path.join(pdf_dir, f"surat_{nomor_clean}.pdf"),
        ]

        found_path = None
        for p in possible_files:
            if os.path.exists(p) and os.path.getsize(p) > 0:
                found_path = p
                break

        # Jika berkas PDF belum tersimpan di disk lokal, render on-demand via execution tools
        if not found_path:
            try:
                tools = SuratExecutionTools()
                nomor_resmi = surat_req.nomor_surat_resmi or tools.generate_official_number(surat_req)
                qr_code = surat_req.qr_verification_code or nomor_resmi
                effective_content = (
                    (surat_req.final_approved_content or "").strip()
                    or (surat_req.ai_original_draft or "").strip()
                )
                tools.render_pdf_and_upload(
                    surat_request=surat_req,
                    nomor_surat=nomor_resmi,
                    qr_code_url=qr_code,
                    final_approved_content=effective_content,
                )
                for p in possible_files:
                    if os.path.exists(p) and os.path.getsize(p) > 0:
                        found_path = p
                        break
            except Exception as render_err:
                logger.error("Gagal men-generate PDF on-demand untuk surat pk=%s: %s", pk, render_err)

        if not found_path or not os.path.exists(found_path):
            raise Http404("Berkas PDF dokumen belum tersedia untuk surat ini.")

        response = FileResponse(open(found_path, "rb"), content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="surat_{nomor_clean}.pdf"'
        response["X-Frame-Options"] = "SAMEORIGIN"
        return response


class SuratDownloadPdfAPIView(APIView):
    """
    Endpoint internal gateway untuk pengunduhan berkas PDF resmi (Zero-Cloudinary dependency).
    GET /surat/requests/<int:pk>/download-pdf/
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, pk: int):
        try:
            surat_req = SuratRequest.objects.select_related(
                'student',
                'student__user',
                'student__prodi',
                'student__fakultas',
                'kode_surat',
            ).get(pk=pk)
        except SuratRequest.DoesNotExist:
            raise Http404("Surat tidak ditemukan.")

        pdf_dir = os.path.join(settings.BASE_DIR, "media", "generated_pdf")
        os.makedirs(pdf_dir, exist_ok=True)

        nomor_clean = str(surat_req.nomor_surat_resmi or f"req_{pk}").replace("/", "_")
        possible_files = [
            os.path.join(pdf_dir, f"surat_{pk}.pdf"),
            os.path.join(pdf_dir, f"surat_{nomor_clean}.pdf"),
        ]

        found_path = None
        for p in possible_files:
            if os.path.exists(p) and os.path.getsize(p) > 0:
                found_path = p
                break

        if not found_path:
            try:
                tools = SuratExecutionTools()
                nomor_resmi = surat_req.nomor_surat_resmi or tools.generate_official_number(surat_req)
                qr_code = surat_req.qr_verification_code or nomor_resmi
                effective_content = (
                    (surat_req.final_approved_content or "").strip()
                    or (surat_req.ai_original_draft or "").strip()
                )
                tools.render_pdf_and_upload(
                    surat_request=surat_req,
                    nomor_surat=nomor_resmi,
                    qr_code_url=qr_code,
                    final_approved_content=effective_content,
                )
                for p in possible_files:
                    if os.path.exists(p) and os.path.getsize(p) > 0:
                        found_path = p
                        break
            except Exception as render_err:
                logger.error("Gagal men-generate PDF on-demand untuk surat pk=%s: %s", pk, render_err)

        if not found_path or not os.path.exists(found_path):
            raise Http404("Berkas PDF dokumen belum tersedia untuk surat ini.")

        response = FileResponse(open(found_path, "rb"), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="surat_{nomor_clean}.pdf"'
        return response

