import logging
import threading
from typing import Any, Dict, Optional

from django.db import close_old_connections
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
from .services.session import AutoSuratSessionManager

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
        active_agent = agent if agent is not None else SuratDraftingAgent()
        draft_output = active_agent.draft_letter(
            user_prompt_context=user_prompt_context,
            kode_surat=kode_surat,
            student_metadata=student_metadata,
            # dynamic_fields=dynamic_fields_dict
        )

        if hasattr(draft_output, "to_payload_dict") and callable(draft_output.to_payload_dict):
            structured_payload: Dict[str, Any] = draft_output.to_payload_dict()
        else:
            structured_payload = draft_output.extracted_payload.model_dump(mode="json")

        surat_req = SuratRequest.objects.get(pk=surat_request_id)
        surat_req.payload_data = structured_payload
        surat_req.ai_original_draft = draft_output.ai_original_draft
        surat_req.self_critique_score = draft_output.evaluation.self_critique_score
        surat_req.revision_notes = list(draft_output.evaluation.revision_notes)
        
        critique_score = draft_output.evaluation.self_critique_score
        
        # Pengecekan has_missing_info dihapus karena slot data sudah divalidasi tuntas di sesi chat.
        # Kita hanya menjaga ambang batas kualitas redaksi AI (misal skor di bawah 7 memerlukan tinjauan ulang).
        if critique_score < 7:
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
                "SuratRequest id=%s dikembalikan karena skor evaluasi diri AI terlalu rendah (Skor: %s).",
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
    student_metadata: dict
) -> None:
    """
    Worker asinkron untuk memproses ulang penyusunan draf surat (Self-Reflection Re-draft)
    ketika pengguna memberikan informasi tambahan berdasarkan revision_notes.
    """
    close_old_connections()
    try:
        surat_req = SuratRequest.objects.get(pk=surat_request_id)
        
        active_agent = SuratDraftingAgent()
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

        if hasattr(draft_output, "to_payload_dict") and callable(draft_output.to_payload_dict):
            structured_payload = draft_output.to_payload_dict()
        else:
            structured_payload = draft_output.extracted_payload.model_dump(mode="json")

        critique_score = draft_output.evaluation.self_critique_score
        # Memeriksa apakah masih ada field opsional penting yang bernilai kosong/null
        has_null_required = any(
            v is None for k, v in structured_payload.items() 
            if k in ["tanggal_mulai", "tanggal_selesai", "posisi_dilamar"]
        )

        surat_req.payload_data = structured_payload
        surat_req.ai_original_draft = draft_output.ai_original_draft
        surat_req.self_critique_score = critique_score
        surat_req.revision_notes = list(draft_output.evaluation.revision_notes)

        if critique_score < 8 or has_null_required:
            surat_req.status = SuratStatus.REVISION_REQUIRED
            action_code = "AI_REDRAFT_STILL_INCOMPLETE"
        else:
            surat_req.status = SuratStatus.PENDING_APPROVAL
            action_code = "AI_REDRAFT_SUCCESS_PENDING_APPROVAL"

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

        return Response({
            "status": "success",
            "message": "Sesi chat (thread) berhasil diinisialisasi.",
            "thread_id": str(thread.id),
            "title": thread.title,
            "document_type": thread.document_type,
            "created_at": thread.created_at
        }, status=status.HTTP_201_CREATED)
class ChatSessionMessageAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [CustomJWTAuthentication]

    def post(self, request, thread_id):
        user_msg = request.data.get("message", "").strip()
        if not user_msg:
            return Response(
                {"status": "error", "message": "Pesan tidak boleh kosong."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 1. Pastikan thread milik user yang sedang login
        thread = ChatThread.objects.filter(id=thread_id, user=request.user).first()
        if not thread:
            return Response(
                {"status": "error", "message": "Sesi chat atau thread tidak ditemukan."},
                status=status.HTTP_404_NOT_FOUND
            )

        # 2. Jalankan SessionManager (Menangani Guardrail "batal", TTL 30 menit, & State Redis)
        session_result = AutoSuratSessionManager.handle_incoming_message(
            thread_id=str(thread.id),
            user_message=user_msg,
            user_obj=request.user
        )

        if session_result["state"] in ["CANCELLED", "EXPIRED"]:
            return Response({
                "status": "success",
                "state": session_result["state"],
                "reply": session_result["reply"]
            }, status=status.HTTP_200_OK)

        current_state = session_result["state"]
        intent = session_result["intent"] # Kode surat yang tersimpan di Redis (misal: "SR-MAG")
        slots = session_result["slots"]

        # 3. CEK KONFIRMASI: Jika sesi sedang menunggu konfirmasi (preview sudah tampil) 
        if current_state == "AWAITING_CONFIRMATION" and user_msg.lower() in ["lanjut", "ya", "proses", "oke", "buatkan", "ok", "yes"]:
            return Response({
                "status": "trigger_create_request",
                "state": "AWAITING_CONFIRMATION",
                "reply": "Konfirmasi diterima! Memproses pembuatan draf surat resmi Anda...",
                "kode_surat": intent,
                "collected_slots": slots
            }, status=status.HTTP_200_OK)

        agent = SuratDraftingAgent()

        # Ambil metadata mahasiswa
        student_obj = getattr(request.user, 'student_profile', None)
        student_metadata = {
            "nim": getattr(student_obj, "nim", ""),
            "nama": getattr(request.user, "nama", ""),
            "prodi": getattr(getattr(student_obj, "prodi", None), "nama_prodi", ""),
        } if student_obj else {}

        # 4. Jalankan AI Agent (Mendukung Intent Classification jika `intent` masih kosong)
        try:
            clarification_result = agent.check_or_clarify_request(
                user_prompt_context=user_msg,
                kode_surat=intent, # Akan bernilai None jika pesan pertama, sehingga AI otomatis mendeteksi
                student_metadata=student_metadata
            )
        except Exception as exc:
            logger.exception("Gagal melakukan clarification check pada chat session:")
            return Response(
                {"status": "error", "message": "Terjadi kendala pada pemrosesan AI."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # Jika intent belum ada di Redis, simpan `detected_intent` hasil tebakan AI ke Redis
        if not intent and getattr(clarification_result, "detected_intent", None):
            intent = clarification_result.detected_intent

        # 5. Jika Data Belum Lengkap -> Minta Klarifikasi / Slot Filling Lanjutan
        if not clarification_result.is_complete:
            AutoSuratSessionManager.save_session(
                str(thread.id), 
                state="COLLECTING_SLOTS", 
                intent=intent, # Simpan intent yang baru terdeteksi
                missing_slots=clarification_result.missing_fields
            )
            return Response({
                "status": "needs_clarification",
                "state": "COLLECTING_SLOTS",
                "detected_intent": intent,
                "reply": clarification_result.clarification_message,
                "missing_fields": clarification_result.missing_fields
            }, status=status.HTTP_200_OK)

        # 6. Jika Data SUDAH LENGKAP -> Transisi ke State Konfirmasi (Preview)
        AutoSuratSessionManager.save_session(
            str(thread.id), 
            state="AWAITING_CONFIRMATION", 
            intent=intent,
            slots=clarification_result.extracted_slots
        )
        
        preview_summary = "\n".join([f"- **{k}**: {v}" for k, v in clarification_result.extracted_slots.items()])

        return Response({
            "status": "ready_to_preview",
            "state": "AWAITING_CONFIRMATION",
            "detected_intent": intent,
            "reply": f"Beres! Semua data yang diperlukan sudah terkumpul. Berikut ringkasan datanya:\n\n{preview_summary}\n\nApakah data di atas sudah benar? Silakan ketik **'Lanjut'** untuk memproses draf resmi.",
            "collected_slots": clarification_result.extracted_slots
        }, status=status.HTTP_200_OK)
        
class SuratRequestRedraftAPIView(APIView):
    """
    Endpoint bagi mahasiswa untuk memberikan informasi tambahan / revisi 
    pada surat yang berstatus REVISION_REQUIRED.
    PATCH /api/surat/requests/<int:pk>/re-draft/
    """
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [CustomJWTAuthentication]
    parser_classes = [JSONParser, FormParser, MultiPartParser]
    _last_worker_thread: Optional[threading.Thread] = None

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
                    "errors": "Bukan akun mahasiswa. Hanya mahasiswa yang dapat mengajukan surat.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

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

        # =========================================================================
        # PENCEGAHAN DOUBLE REQUEST:
        # Cek apakah mahasiswa ini masih memiliki permohonan aktif untuk kode_surat yang sama.
        # Status aktif meliputi: Sedang diproses AI, Menunggu Dosen, atau Perlu Revisi.
        # =========================================================================
        active_statuses = [
            SuratStatus.SUBMITTED,
            SuratStatus.PENDING_APPROVAL,
            SuratStatus.REVISION_REQUIRED,
        ]
        existing_active_request = SuratRequest.objects.filter(
            student=student_obj,
            kode_surat=surat_type,
            status__in=active_statuses
        ).first()

        if existing_active_request:
            return Response(
                {
                    "status": "error",
                    "message": "Pengajuan Ganda Ditolak",
                    "errors": (
                        f"Anda masih memiliki permohonan aktif untuk jenis surat '{surat_type.nama_surat}' "
                        f"dengan status '{existing_active_request.status}'. "
                        "Silakan selesaikan atau periksa permohonan yang sudah ada."
                    ),
                    "existing_request_id": existing_active_request.id,
                    "surat_status": existing_active_request.status,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        # =========================================================================

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

        # Buat rekam data awal dengan status SUBMITTED
        surat_req = SuratRequest.objects.create(
            student=student_obj,
            kode_surat=surat_type,
            status=SuratStatus.SUBMITTED,
            payload_data=initial_payload,
            user_prompt_context=user_prompt_context,
        )

        SuratAuditLog.objects.create(
            surat_request=surat_req,
            action_id="AI_01",
            action="SURAT_SUBMITTED_FOR_AI_DRAFTING",
        )

        dynamic_fields_dict = getattr(surat_type, "required_fields_dict", None)

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
          },
            },
            status=status.HTTP_202_ACCEPTED,
        )

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
        # ndwfevirc kwc
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
        surat_req = SuratRequest.objects.create(
            student=student_obj,
            kode_surat=surat_type,
            status=SuratStatus.SUBMITTED,
            payload_data=initial_payload,
            user_prompt_context=user_prompt_context,
        )

        SuratAuditLog.objects.create(
            surat_request=surat_req,
            action_id="AI_01",
            action="SURAT_SUBMITTED_FOR_AI_DRAFTING",
        )

        # Ambil field dinamis yang tersimpan di kolom/atribut jenis surat (sesuaikan nama field modelnya, misal: required_fields_dict)
        dynamic_fields_dict = getattr(surat_type, "required_fields_dict", None)

        worker_thread = threading.Thread(
            target=_execute_drafting_agent_worker,
            kwargs={
                "surat_request_id": surat_req.id,
                "user_prompt_context": user_prompt_context,
                "kode_surat": surat_type.kode_surat,
                "student_metadata": student_metadata,
                "agent": self.get_drafting_agent(),
                "dynamic_fields_dict": dynamic_fields_dict, # <-- Teruskan data dinamis ke worker
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
                },
            },
            status=status.HTTP_202_ACCEPTED,
        )


class SuratRequestListAPIView(ListAPIView):
    """
    Endpoint untuk melihat daftar riwayat pengajuan surat milik mahasiswa yang sedang login.
    GET /api/surat/requests/
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SuratRequestListSerializer

    def get_queryset(self):
        user = self.request.user
        if hasattr(user, 'student_profile'):
            return SuratRequest.objects.filter(student=user.student_profile).order_by('-created_at')
        return SuratRequest.objects.all().order_by('-created_at')


class SuratRequestDetailAPIView(RetrieveAPIView):
    """
    Endpoint untuk melihat detail lengkap suatu pengajuan surat beserta status TTE & Approval.
    GET /api/surat/requests/<int:pk>/
    """
    permission_classes = [permissions.IsAuthenticated]
    queryset = SuratRequest.objects.all()
    serializer_class = SuratRequestDetailSerializer


class LecturerApprovalActionAPIView(APIView):
    """
    Endpoint bagi Dosen/Pejabat untuk menyetujui (APPROVE) atau menolak (REJECT) antrean surat.
    Mendelegasikan seluruh eksekusi bisnis persetujuan, nomor, TTE, dan PDF ke `process_approval_action`.
    
    POST /api/surat/approval/<int:approval_id>/action/
    """
    permission_classes = [permissions.IsAuthenticated]

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
        if action == "APPROVE":
            serializer = SuratApprovalActionSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            catatan = serializer.validated_data.get("catatan") or ""
        elif action == "REJECT":
            serializer = SuratRejectActionSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            catatan = serializer.validated_data["alasan_penolakan"]

        # Validasi kepemilikan approval step sebelum dilempar ke service
        try:
            approval_step = SuratApproval.objects.select_related('approver').get(id=approval_id)
        except SuratApproval.DoesNotExist:
            return Response({"error": "Antrean approval tidak ditemukan."}, status=status.HTTP_404_NOT_FOUND)

        if approval_step.approver != lecturer_obj:
            return Response({"error": "Anda tidak memiliki hak akses untuk menyetujui antrean ini."}, status=status.HTTP_403_FORBIDDEN)

        # Panggil fungsi service utama yang sudah rapi
        result_data, http_code = process_approval_action(
            approval_id=approval_id,
            lecturer=lecturer_obj,
            action=action,
            catatan=catatan
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
