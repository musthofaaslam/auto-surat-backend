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
)
from .services.workflow_service import process_approval_action

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
        has_missing_info = any("tidak disebutkan" in str(v).lower() for v in structured_payload.values())

        if critique_score < 8 or has_missing_info:
            # JANGAN LOLOSKAN KE PENDING_APPROVAL! Ubah ke status butuh revisi/gagal karena kurang info
            surat_req.status = SuratStatus.REVISION_REQUIRED # Pastikan status ini ada di model SuratStatus, atau buat status REJECTED/FAILED
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
                action="AI_DRAFTING_REJECTED_INCOMPLETE_INFO",
            )
            logger.warning(
                "SuratRequest id=%s dikembalikan karena informasi kurang (Skor: %s).",
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


def _execute_approval_pipeline_worker(
    surat_request_id: int,
    lecturer_id: Optional[Any] = None,
    final_approved_content: Optional[str] = None,
    final_status: str = SuratStatus.SENT,
    execution_tools: Optional[SuratExecutionTools] = None,
    memory_agent: Optional[AgenticMemoryAgent] = None,
) -> None:
    """
    Worker asinkron untuk menjalankan pipeline Fase 2 (Eksekusi Alat: Nomor Surat,
    QR Code TTE, Render PDF & Unggah Cloudinary) serta Fase 3 (Agentic Memory Loop:
    komparasi diff antara ai_original_draft dan final_approved_content) di latar belakang.
    Memperbarui kolom file_pdf_url, qr_verification_code, TteSignature, dan mengubah
    status akhir SuratRequest menjadi SENT atau PRINTED.
    """
    close_old_connections()
    try:
        surat_req = SuratRequest.objects.select_related(
            "kode_surat",
            "student",
            "student__user",
            "student__fakultas",
            "student__prodi",
        ).get(pk=surat_request_id)

        signer = (
            Lecturer.objects.select_related("user").filter(pk=lecturer_id).first()
            if lecturer_id is not None
            else None
        )

        active_tools = (
            execution_tools if execution_tools is not None else SuratExecutionTools()
        )
        pipeline_result = active_tools.execute_approval_pipeline(
            surat_request=surat_req,
            signer=signer,
            final_approved_content=final_approved_content,
            final_status=final_status,
        )

        logger.info(
            "Eksekusi alat pasca-approval berhasil untuk SuratRequest id=%s "
            "(status=%s, pdf_url=%s).",
            surat_request_id,
            pipeline_result.final_status,
            pipeline_result.file_pdf_url,
        )

        # Kegagalan non-kritis pada pembelajaran memori tidak boleh membatalkan surat
        # resmi yang sudah terbit dan berstatus SENT / PRINTED.
        try:
            active_memory_agent = (
                memory_agent if memory_agent is not None else AgenticMemoryAgent()
            )
            active_memory_agent.record_feedback_memory(
                surat_request=surat_req,
                ai_original_draft=surat_req.ai_original_draft,
                final_approved_content=surat_req.final_approved_content,
                allow_heuristic_fallback=True,
            )
        except MemoryAgentError as mem_exc:
            logger.warning(
                "Kendala operasional AgenticMemoryAgent pada SuratRequest id=%s: %s",
                surat_request_id,
                mem_exc,
            )
            SuratAuditLog.objects.create(
                surat_request=surat_req,
                action_id="MEM_WARN",
                action=f"MEMORY_DIFF_SKIPPED: {mem_exc}"[:255],
            )
        except Exception as mem_unexpected:
            logger.warning(
                "Kesalahan tak terduga saat evaluasi memori pada SuratRequest id=%s: %s",
                surat_request_id,
                mem_unexpected,
            )

    except ExecutionToolError as exc:
        logger.error(
            "Kegagalan eksekusi alat pasca-approval pada SuratRequest id=%s (%s): %s",
            surat_request_id,
            type(exc).__name__,
            exc,
        )
        _mark_surat_request_failed(
            surat_request_id=surat_request_id,
            error_code="EXEC_ERR_TOOL",
            error_reason=f"{type(exc).__name__}: {exc}",
        )
    except Exception as exc:
        logger.exception(
            "Kesalahan tak terduga pada pipeline approval SuratRequest id=%s: %s",
            surat_request_id,
            exc,
        )
        _mark_surat_request_failed(
            surat_request_id=surat_request_id,
            error_code="EXEC_ERR_UNEXPECTED",
            error_reason=f"{type(exc).__name__}: {exc}",
        )
    finally:
        close_old_connections()


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

        student_metadata = {
            "nim": student_obj.nim,
            "nama": getattr(student_obj.user, "nama", ""),
            "prodi": getattr(student_obj.prodi, "nama_prodi", ""),
            "fakultas": getattr(student_obj.fakultas, "nama_fakultas", ""),
            "semester_aktif": student_obj.semester_aktif,
            "tahun_akademik": student_obj.tahun_akademik,
        }
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
    Saat keputusan APPROVE final diterima, sistem menyimpan naskah final (`final_approved_content`)
    dan mendelegasikan pembuatan TTE, QR Code, PDF Cloudinary (`execution_tools`), serta
    pembelajaran gaya bahasa (`memory_agent`) ke dalam background thread asinkron.
    POST /api/surat/approval/<int:approval_id>/action/
    """
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [CustomJWTAuthentication]
    execution_tools_instance: Optional[SuratExecutionTools] = None
    memory_agent_instance: Optional[AgenticMemoryAgent] = None
    _last_worker_thread: Optional[threading.Thread] = None

    def get_execution_tools(self) -> Optional[SuratExecutionTools]:
        """
        Mengembalikan instance SuratExecutionTools kustom apabila disuntikkan (misal pada pengujian),
        atau None agar worker menginisialisasi instance baru di dalam background thread.
        """
        return self.execution_tools_instance

    def get_memory_agent(self) -> Optional[AgenticMemoryAgent]:
        """
        Mengembalikan instance AgenticMemoryAgent kustom apabila disuntikkan (misal pada pengujian),
        atau None agar worker menginisialisasi instance baru di dalam background thread.
        """
        return self.memory_agent_instance

    # SARAN PERBAIKAN ARSITEKTURAL:
    # 1. Dekorator `@extend_schema` mendefinisikan kontrak input dan output secara eksplisit
    #    bagi `drf-spectacular` termasuk atribut baru `final_approved_content` dan `final_status`.
    # 2. Pada cabang `APPROVE` tahap akhir, operasi berat (WeasyPrint PDF, unggah Cloudinary,
    #    dan inferensi diff LLM `gemini-3.8-flash`) dieksekusi di dalam background thread
    #    `_execute_approval_pipeline_worker` agar endpoint merespons seketika tanpa timeout.
    @extend_schema(
        summary="Tindakan Persetujuan atau Penolakan Surat (Dosen/Pejabat)",
        description=(
            "Digunakan oleh Dosen atau Pejabat berwenang untuk menyetujui (APPROVE) "
            "atau menolak (REJECT) antrean pengajuan surat berdasarkan approval_id. "
            "Saat APPROVE final dilakukan, teks final disimpan dan eksekusi PDF/TTE/Cloudinary "
            "serta Agentic Memory Loop dijalankan secara asinkron di latar belakang."
        ),
        request=LecturerApprovalActionRequestSerializer,
        responses={
            200: LecturerApprovalActionResponseSerializer,
            202: LecturerApprovalActionResponseSerializer,
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
        submitted_final_content: Optional[str] = None
        requested_final_status: str = SuratStatus.SENT

        if action == "APPROVE":
            serializer = SuratApprovalActionSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            catatan = serializer.validated_data.get("catatan") or ""
            submitted_final_content = serializer.validated_data.get("final_approved_content")
            requested_final_status = (
                serializer.validated_data.get("final_status") or SuratStatus.SENT
            )
        elif action == "REJECT":
            serializer = SuratRejectActionSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            catatan = serializer.validated_data["alasan_penolakan"]

        # Fallback defensif apabila approval_id merujuk langsung pada SuratRequest
        # berstatus PENDING_APPROVAL yang belum memiliki baris SuratApproval
        try:
            approval_step = SuratApproval.objects.select_related(
                "surat_request",
                "surat_request__kode_surat",
                "surat_request__student",
                "surat_request__student__user",
                "surat_request__student__fakultas",
                "surat_request__student__prodi",
            ).get(id=approval_id)
        except SuratApproval.DoesNotExist:
            surat_req_candidate = (
                SuratRequest.objects.select_related(
                    "kode_surat",
                    "student",
                    "student__user",
                    "student__fakultas",
                    "student__prodi",
                )
                .filter(id=approval_id, status=SuratStatus.PENDING_APPROVAL)
                .first()
            )
            if (
                surat_req_candidate is not None
                and not SuratApproval.objects.filter(surat_request=surat_req_candidate).exists()
            ):
                approval_step = SuratApproval.objects.create(
                    surat_request=surat_req_candidate,
                    step_order=1,
                    approver=lecturer_obj,
                    status=ApprovalStatus.PENDING,
                )
            else:
                return Response(
                    {"error": "Antrean approval tidak ditemukan."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        if approval_step.approver != lecturer_obj:
            return Response(
                {"error": "Anda tidak memiliki hak akses untuk menyetujui antrean ini."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if approval_step.status != ApprovalStatus.PENDING:
            return Response(
                {"error": "Langkah persetujuan ini belum aktif atau sudah diproses sebelumnya."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if action == "REJECT":
            result, http_code = process_approval_action(
                approval_id=approval_step.id,
                lecturer=lecturer_obj,
                action=action,
                catatan=catatan,
            )
            return Response(result, status=http_code)

        surat_req = approval_step.surat_request

        for alias_key in ("final_approved_content", "approved_content", "final_content"):
            if not submitted_final_content:
                candidate_val = request.data.get(alias_key)
                if isinstance(candidate_val, str) and candidate_val.strip():
                    submitted_final_content = candidate_val.strip()

        resolved_final_content = (
            submitted_final_content.strip()
            if isinstance(submitted_final_content, str) and submitted_final_content.strip()
            else (
                (surat_req.final_approved_content or "").strip()
                or (surat_req.ai_original_draft or "").strip()
            )
        )

        raw_status_override = request.data.get("final_status") or request.data.get("target_status")
        if isinstance(raw_status_override, str) and raw_status_override.strip().upper() in (
            SuratStatus.SENT,
            SuratStatus.PRINTED,
        ):
            requested_final_status = raw_status_override.strip().upper()

        approval_step.status = ApprovalStatus.APPROVED
        approval_step.catatan = catatan
        approval_step.created_at = timezone.now()
        approval_step.save(update_fields=["status", "catatan", "created_at"])

        next_step = SuratApproval.objects.filter(
            surat_request=surat_req,
            step_order=approval_step.step_order + 1,
        ).first()

        if next_step is not None:
            next_step.status = ApprovalStatus.PENDING
            next_step.save(update_fields=["status"])
            surat_req.status = SuratStatus.IN_REVIEW
            surat_req.final_approved_content = resolved_final_content
            surat_req.save(update_fields=["status", "final_approved_content"])

            SuratAuditLog.objects.create(
                surat_request=surat_req,
                action_id=f"APP_0{approval_step.step_order}",
                action=f"APPROVED_STEP_{approval_step.step_order}_FORWARDED",
            )
            return Response(
                {
                    "status": "success",
                    "message": "Persetujuan tahap ini berhasil. Surat diteruskan ke pejabat selanjutnya.",
                    "request_id": surat_req.id,
                    "surat_status": surat_req.status,
                },
                status=status.HTTP_200_OK,
            )

        # Persetujuan tahap akhir: kunci final_approved_content dan delegasikan eksekusi
        # alat (PDF, TTE, Cloudinary) serta Memory Agent ke background thread
        surat_req.final_approved_content = resolved_final_content
        surat_req.status = SuratStatus.APPROVED
        surat_req.save(update_fields=["final_approved_content", "status"])

        SuratAuditLog.objects.create(
            surat_request=surat_req,
            action_id="APP_FINAL",
            action=f"APPROVED_BY_{lecturer_obj.id}_ASYNC_PIPELINE_DISPATCHED",
        )

        worker_thread = threading.Thread(
            target=_execute_approval_pipeline_worker,
            kwargs={
                "surat_request_id": surat_req.id,
                "lecturer_id": lecturer_obj.id,
                "final_approved_content": resolved_final_content,
                "final_status": requested_final_status,
                "execution_tools": self.get_execution_tools(),
                "memory_agent": self.get_memory_agent(),
            },
            name=f"surat-approval-pipeline-{surat_req.id}",
            daemon=True,
        )
        LecturerApprovalActionAPIView._last_worker_thread = worker_thread
        worker_thread.start()

        return Response(
            {
                "status": "success",
                "message": (
                    "Persetujuan final diterima. Pembuatan TTE, QR Code, PDF Cloudinary, "
                    "dan pembelajaran memori sedang diproses secara asinkron."
                ),
                "request_id": surat_req.id,
                "approval_id": approval_step.id,
                "surat_status": surat_req.status,
                "target_final_status": requested_final_status,
                "final_approved_content": surat_req.final_approved_content,
                "nomor_surat_resmi": surat_req.nomor_surat_resmi,
                "file_pdf_url": surat_req.file_pdf_url,
            },
            status=status.HTTP_200_OK,
        )


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
