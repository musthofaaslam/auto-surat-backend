import json
import logging
import os
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, Union

try:
    from django.conf import settings
    from django.core.exceptions import ImproperlyConfigured
except ImportError:  # pragma: no cover
    settings = None  # type: ignore[assignment]
    ImproperlyConfigured = Exception  # type: ignore[assignment,misc]

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

from surat.agents.prompts import (
    build_initial_user_prompt,
    build_self_reflection_revision_prompt,
    build_system_prompt,
)
from surat.agents.schemas import (
    # AgentSuratDraftOutputSchema,
    SelfEvaluationSchema,
    # SuratMagangPayloadSchema,
    build_dynamic_payload_schema,
    create_dynamic_agent_output_schema,
)

# SARAN PERBAIKAN ARSITEKTURAL:
# 1. Hierarki exception khusus (`SuratAgentError` beserta sub-kelas spesifik untuk Timeout,
#    Rate-Limit, Konfigurasi, dan Validasi) mengisolasi detail implementasi SDK `google-genai`
#    agar layer service/views (dan worker asinkron Celery/ASGI) dapat menangani kegagalan
#    secara deterministik tanpa menangkap `Exception` generik yang kabur.
# 2. Mekanisme Self-Reflection dibatasi secara ketat pada maksimal 1 kali iterasi perbaikan
#    otomatis (`max_revisions=1`) ketika `self_critique_score < 8`. Pembatasan deterministik
#    ini mencegah infinite loop, menjaga latensi inferensi tetap terkendali, dan memastikan
#    kasus yang memang kekurangan data dari pengguna tetap diteruskan ke Admin beserta
#    `revision_notes` pada status `PENDING_APPROVAL`.
# 3. `SuratDraftingAgent` mendukung Dependency Injection pada parameter `client` sehingga
#    pengujian unit dan integrasi pipeline dapat dijalankan secara terisolasi tanpa
#    ketergantungan jaringan eksternal.

logger = logging.getLogger(__name__)


class SuratAgentError(Exception):
    """Base exception untuk seluruh kesalahan operasional pada SuratDraftingAgent."""

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        original_exception: Optional[BaseException] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.original_exception = original_exception


class SuratAgentConfigurationError(SuratAgentError):
    """Dilempar ketika konfigurasi API Key, model, atau berkas kontrak data tidak valid."""


class SuratAgentTimeoutError(SuratAgentError):
    """Dilempar ketika permintaan ke layanan LLM melampaui batas waktu tunggu (timeout)."""


class SuratAgentRateLimitError(SuratAgentError):
    """Dilempar ketika kuota atau batas frekuensi permintaan (HTTP 429) layanan LLM terlampaui."""


class SuratAgentUpstreamError(SuratAgentError):
    """Dilempar ketika layanan LLM mengalami kegagalan internal atau gangguan jaringan lainnya."""


class SuratAgentValidationError(SuratAgentError):
    """Dilempar ketika keluaran LLM gagal memenuhi kontrak skema Pydantic di schemas.py."""


def _get_django_or_env_setting(name: str, default: Any = None) -> Any:
    """
    Mengambil nilai konfigurasi dari `django.conf.settings` apabila runtime Django aktif,
    atau melakukan fallback secara aman ke variabel environment sistem.
    """
    if settings is not None:
        try:
            if getattr(settings, "configured", False) and hasattr(settings, name):
                return getattr(settings, name)
        except ImproperlyConfigured:
            pass
    return os.environ.get(name, default)


class SuratDraftingAgent:
    """
    Agen penyusun draf surat resmi (Agentic AI Level 2 - Fase 1: Pra-Approval).
    Bertugas mengekstrak payload sesuai `required_field_surat.json`, menyusun draf surat
    berstandar administrasi universitas, dan menjalankan Self-Reflection Loop maksimal 1 kali
    apabila `self_critique_score < 8`.
    """

    DEFAULT_CRITIQUE_THRESHOLD: int = 8
    DEFAULT_MAX_REVISIONS: int = 1
    DEFAULT_MODEL_NAME: str = "gemini-3.1-flash-lite"
    FALLBACK_MODELS: tuple = (
        "gemini-3.1-flash-lite",
        "gemini-3.8-flash",
        "gemini-flash-lite-latest",
    )
    DEFAULT_TIMEOUT_SECONDS: float = 30.0

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        required_fields_path: Optional[Union[str, Path]] = None,
        critique_min_score: Optional[int] = None,
        max_revisions: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
        client: Optional[Any] = None,
    ) -> None:
        resolved_key = _get_django_or_env_setting(
            "GEMINI_API_KEY", os.environ.get("GOOGLE_API_KEY", "")
        )
        self.api_key: str = api_key if api_key is not None else str(resolved_key or "")
        self.model_name: str = (
            model_name
            if model_name is not None
            else str(_get_django_or_env_setting("GEMINI_MODEL_NAME", self.DEFAULT_MODEL_NAME))
        )
        self.critique_min_score: int = int(
            critique_min_score
            if critique_min_score is not None
            else _get_django_or_env_setting(
                "AGENT_CRITIQUE_MIN_SCORE", self.DEFAULT_CRITIQUE_THRESHOLD
            )
        )
        # Kunci batas iterasi perbaikan maksimal 1 kali sesuai spesifikasi arsitektur Tahap 2
        configured_revisions = (
            max_revisions
            if max_revisions is not None
            else _get_django_or_env_setting("AGENT_MAX_REVISIONS", self.DEFAULT_MAX_REVISIONS)
        )
        self.max_revisions: int = min(max(int(configured_revisions), 0), 1)

        self.timeout_seconds: float = float(
            timeout_seconds
            if timeout_seconds is not None
            else _get_django_or_env_setting(
                "AGENT_TIMEOUT_SECONDS", self.DEFAULT_TIMEOUT_SECONDS
            )
        )

        base_dir = _get_django_or_env_setting(
            "BASE_DIR", Path(__file__).resolve().parent.parent.parent
        )
        default_path = _get_django_or_env_setting(
            "REQUIRED_FIELD_SURAT_PATH",
            Path(base_dir) / "required_field_surat.json",
        )
        self.required_fields_path: Path = Path(required_fields_path or default_path)
        self._client: Optional[Any] = client

    def _get_or_create_client(self) -> Any:
        """
        Menginisialisasi instance `google.genai.Client` secara lazy dengan konfigurasi timeout.
        """
        if self._client is not None:
            return self._client

        if not self.api_key or not self.api_key.strip():
            raise SuratAgentConfigurationError(
                "Konfigurasi GEMINI_API_KEY belum diatur pada environment atau core/settings.py."
            )

        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise SuratAgentConfigurationError(
                "Pustaka 'google-genai' belum terpasang di environment Python."
            ) from exc

        timeout_ms = int(self.timeout_seconds * 1000)
        http_options = types.HttpOptions(timeout=timeout_ms)
        self._client = genai.Client(
            api_key=self.api_key.strip(),
            http_options=http_options,
        )
        return self._client

    def get_required_fields_for_kode(self, kode_surat: str, dynamic_fields_dict: Optional[Dict[str, str]] = None) -> List[Dict[str, str]]:
        """
        Mengambil aturan field dari `required_field_surat.json` berdasarkan `kode_surat`.
        Mendukung struktur JSON berupa pemetaan per `kode_surat` (dict) maupun daftar
        spesifikasi kanonik langsung (list).
        """
        if dynamic_fields_dict and isinstance(dynamic_fields_dict, dict):
            formatted_fields = []
            for field_name, field_desc in dynamic_fields_dict.items():
                formatted_fields.append({
                    "field": field_name,
                    "type": "string",
                    "description": str(field_desc)
                })
            return formatted_fields
        
        normalized_kode = (kode_surat or "").strip().upper()
        if not normalized_kode:
            raise SuratAgentConfigurationError(
                "Parameter kode_surat wajib diisi untuk memuat spesifikasi field surat."
            )

        if not self.required_fields_path.exists():
            raise SuratAgentConfigurationError(
                f"Berkas kontrak data tidak ditemukan pada jalur: {self.required_fields_path}"
            )

        try:
            with open(self.required_fields_path, "r", encoding="utf-8") as file_obj:
                raw_data = json.load(file_obj)
        except (OSError, json.JSONDecodeError) as exc:
            raise SuratAgentConfigurationError(
                f"Gagal membaca atau mengurai berkas {self.required_fields_path}: {exc}"
            ) from exc

        selected_fields: Optional[List[Dict[str, str]]] = None

        if isinstance(raw_data, dict):
            # Jika JSON dipetakan berdasarkan kode_surat, cari kode terkait atau fallback DEFAULT
            if normalized_kode in raw_data and isinstance(raw_data[normalized_kode], list):
                selected_fields = raw_data[normalized_kode]
            elif "DEFAULT" in raw_data and isinstance(raw_data["DEFAULT"], list):
                selected_fields = raw_data["DEFAULT"]
            else:
                raise SuratAgentConfigurationError(
                    f"Aturan field untuk kode_surat '{normalized_kode}' tidak ditemukan "
                    f"di dalam {self.required_fields_path.name}."
                )
        elif isinstance(raw_data, list):
            selected_fields = raw_data
        else:
            raise SuratAgentConfigurationError(
                f"Format struktur {self.required_fields_path.name} tidak valid. "
                "Harus berupa JSON Array atau JSON Object."
            )

        if not selected_fields:
            raise SuratAgentConfigurationError(
                f"Daftar spesifikasi field untuk kode_surat '{normalized_kode}' kosong."
            )

        for item in selected_fields:
            if not isinstance(item, dict) or not item.get("field"):
                raise SuratAgentConfigurationError(
                    "Setiap entri pada required_field_surat.json wajib memiliki atribut 'field'."
                )

        return selected_fields

    def resolve_output_schema(
        self, kode_surat: str, required_fields: List[Dict[str, str]]
    ) -> Type[BaseModel]:
        """
        Menentukan skema Pydantic yang akan diikat ke fitur Structured Outputs LLM.
        Menggunakan `AgentSuratDraftOutputSchema` secara langsung apabila definisi field
        identik dengan `SuratMagangPayloadSchema`, atau membangun skema dinamis turunan
        jika terdapat variasi field untuk `kode_surat` tertentu.
        """
        # canonical_fields = set(SuratMagangPayloadSchema.model_fields.keys())
        # requested_fields = {item["field"] for item in required_fields}

        # if requested_fields == canonical_fields:
        #     return AgentSuratDraftOutputSchema

        normalized_kode = "".join(ch for ch in kode_surat.upper() if ch.isalnum()) or "Custom"
        dynamic_payload_model = build_dynamic_payload_schema(
            f"Surat{normalized_kode}PayloadSchema",
            required_fields,
        )

        def _dynamic_to_payload_dict(instance: Any) -> Dict[str, Any]:
            raw_dict = instance.extracted_payload.model_dump()
            serialized: Dict[str, Any] = {}
            for key, val in raw_dict.items():
                serialized[key] = val.isoformat() if isinstance(val, date) else val
            return serialized

        dynamic_output_schema = create_model(
            f"AgentSurat{normalized_kode}DraftOutputSchema",
            __config__=ConfigDict(extra="forbid", str_strip_whitespace=True),
            extracted_payload=(
                dynamic_payload_model,
                Field(
                    ...,
                    description="Data atribut terstruktur yang diekstrak dari konteks pengguna.",
                ),
            ),
            ai_original_draft=(
                str,
                Field(
                    ...,
                    min_length=50,
                    description="Naskah draf surat formal utuh yang disusun oleh agen.",
                ),
            ),
            evaluation=(
                SelfEvaluationSchema,
                Field(
                    ...,
                    description="Hasil evaluasi internal agen terhadap draf yang baru disusun.",
                ),
            ),
        )
        setattr(dynamic_output_schema, "to_payload_dict", _dynamic_to_payload_dict)
        return dynamic_output_schema  # type: ignore[return-value]

    def _load_active_style_rules(self, kode_surat: str) -> List[str]:
        """
        Memuat aturan preferensi gaya bahasa Admin dari tabel `AgentFeedbackMemory` (Fase 3)
        apabila tersedia di database. Jika tabel belum termigrasi atau koneksi tidak aktif,
        kembalikan list kosong secara aman.
        """
        try:
            from surat.models import AgentFeedbackMemory

            queryset = (
                AgentFeedbackMemory.objects.filter(
                    kode_surat_id=kode_surat.strip().upper(),
                    is_active=True,
                )
                .order_by("-created_at")
                .values_list("extracted_rule", flat=True)[:10]
            )
            return [rule for rule in queryset if rule and rule.strip()]
        except Exception:
            return []

    @classmethod
    def _sanitize_schema_node(cls, node: Any) -> Any:
        if isinstance(node, dict):
            return {
                key: cls._sanitize_schema_node(val)
                for key, val in node.items()
                if key not in ("additionalProperties", "minLength", "maxLength")
            }
        if isinstance(node, list):
            return [cls._sanitize_schema_node(item) for item in node]
        return node

    @classmethod
    def _build_gemini_compatible_json_schema(
        cls,
        response_schema: Type[BaseModel],
    ) -> Dict[str, Any]:
        """
        Membangun JSON Schema dari class Pydantic di `schemas.py` untuk fitur Structured
        Outputs Gemini API, menyederhanakan atribut kompilasi grammar (`additionalProperties`,
        `minLength`, `maxLength`) agar tidak memicu HTTP 400/504 pada server Gemini,
        sembari mempertahankan validasi penuh pada proses `model_validate_json` Pydantic.
        """
        raw_schema = response_schema.model_json_schema()
        return cls._sanitize_schema_node(raw_schema)

    def _invoke_structured_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: Type[BaseModel],
    ) -> Any:
        """
        Memanggil LLM menggunakan fitur Structured Outputs yang diikat langsung ke class
        Pydantic (`response_schema`), memvalidasi hasilnya, dan menerjemahkan error API
        (timeout / rate-limit / upstream) ke dalam exception khusus yang bersih.
        """
        client = self._get_or_create_client()
        json_schema = self._build_gemini_compatible_json_schema(response_schema)

        config: Any
        try:
            from google.genai import types

            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_json_schema=json_schema,
                temperature=0.2,
            )
        except ImportError:
            config = {
                "system_instruction": system_prompt,
                "response_mime_type": "application/json",
                "response_json_schema": json_schema,
                "temperature": 0.2,
            }

        response: Any = None
        try:
            response = client.models.generate_content(
                model=self.model_name,
                contents=user_prompt,
                config=config,
            )
        except Exception as exc:
            status_code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
            exc_text = str(exc).lower()
            is_retriable_model_issue = (
                status_code in (404, 503)
                or "404" in exc_text
                or "not_found" in exc_text
                or "503" in exc_text
                or "high demand" in exc_text
            )
            if is_retriable_model_issue:
                fallback_candidates = [
                    candidate
                    for candidate in self.FALLBACK_MODELS
                    if candidate != self.model_name
                ]
                last_exc: BaseException = exc
                for fallback_model in fallback_candidates:
                    logger.warning(
                        "Model '%s' tidak tersedia/sibuk (code=%s). Mencoba fallback ke '%s'.",
                        self.model_name,
                        status_code,
                        fallback_model,
                    )
                    try:
                        response = client.models.generate_content(
                            model=fallback_model,
                            contents=user_prompt,
                            config=config,
                        )
                        self.model_name = fallback_model
                        break
                    except Exception as fallback_exc:
                        last_exc = fallback_exc
                if response is None:
                    self._handle_api_exception(last_exc)
            else:
                self._handle_api_exception(exc)

        return self._parse_and_validate_response(response, response_schema)

    def _handle_api_exception(self, exc: BaseException) -> None:
        """
        Menerjemahkan exception dari SDK LLM atau layer transportasi HTTP menjadi
        exception domain `SuratAgentError` yang bersih dan spesifik.
        """
        if isinstance(exc, SuratAgentError):
            raise exc

        exc_type_name = type(exc).__name__.lower()
        exc_message = str(exc)
        exc_message_lower = exc_message.lower()
        status_code: Optional[int] = getattr(exc, "code", None) or getattr(
            exc, "status_code", None
        )

        if (
            isinstance(exc, TimeoutError)
            or "timeout" in exc_type_name
            or "timed out" in exc_message_lower
            or "deadline exceeded" in exc_message_lower
            or status_code in (408, 504)
        ):
            logger.error(
                "Timeout saat memanggil layanan LLM (model=%s, timeout=%ss): %s",
                self.model_name,
                self.timeout_seconds,
                exc_message,
            )
            raise SuratAgentTimeoutError(
                f"Permintaan penyusunan draf surat melebihi batas waktu ({self.timeout_seconds} detik).",
                status_code=status_code or 504,
                original_exception=exc,
            ) from exc

        if (
            status_code == 429
            or "429" in exc_message_lower
            or "rate limit" in exc_message_lower
            or "ratelimit" in exc_type_name
            or "resource_exhausted" in exc_message_lower
            or "quota" in exc_message_lower
        ):
            logger.warning(
                "Batas kuota/rate-limit layanan LLM tercapai (model=%s): %s",
                self.model_name,
                exc_message,
            )
            raise SuratAgentRateLimitError(
                "Layanan AI sedang mencapai batas kuota permintaan (rate limit). Silakan coba beberapa saat lagi.",
                status_code=429,
                original_exception=exc,
            ) from exc

        if status_code in (401, 403) or "api_key_invalid" in exc_message_lower:
            logger.error("Kredensial API Key LLM tidak valid atau ditolak: %s", exc_message)
            raise SuratAgentConfigurationError(
                "Kredensial konfigurasi layanan AI tidak valid atau tidak memiliki akses.",
                status_code=status_code or 401,
                original_exception=exc,
            ) from exc

        logger.error(
            "Kegagalan upstream layanan LLM (model=%s, code=%s): %s",
            self.model_name,
            status_code,
            exc_message,
        )
        raise SuratAgentUpstreamError(
            f"Terjadi gangguan komunikasi dengan layanan AI upstream: {exc_message}",
            status_code=status_code or 502,
            original_exception=exc,
        ) from exc

    def _parse_and_validate_response(
        self,
        response: Any,
        response_schema: Type[BaseModel],
    ) -> Any:
        """
        Memastikan hasil keluaran LLM tervalidasi secara ketat oleh class Pydantic
        di `schemas.py` (termasuk seluruh `@field_validator` dan `@model_validator`).
        """
        if response is None:
            raise SuratAgentValidationError(
                "Layanan AI mengembalikan respons kosong (None)."
            )

        try:
            parsed_obj = getattr(response, "parsed", None)
            if parsed_obj is not None:
                if isinstance(parsed_obj, response_schema):
                    # Validasi ulang melalui model_validate untuk menjamin seluruh validator
                    # kustom Pydantic dieksekusi secara utuh
                    return response_schema.model_validate(parsed_obj.model_dump())
                if isinstance(parsed_obj, BaseModel):
                    return response_schema.model_validate(parsed_obj.model_dump())
                if isinstance(parsed_obj, dict):
                    return response_schema.model_validate(parsed_obj)

            raw_text = getattr(response, "text", None)
            if isinstance(raw_text, str) and raw_text.strip():
                return response_schema.model_validate_json(raw_text.strip())

            if isinstance(response, dict):
                return response_schema.model_validate(response)

            raise SuratAgentValidationError(
                "Respons LLM tidak memuat atribut 'parsed' maupun teks JSON yang dapat divalidasi."
            )
        except ValidationError as exc:
            logger.error("Validasi Structured Output Pydantic gagal: %s", exc)
            raise SuratAgentValidationError(
                f"Keluaran agen tidak memenuhi kontrak skema Pydantic: {exc}",
                original_exception=exc,
            ) from exc

    def draft_letter(
        self,
        user_prompt_context: str,
        kode_surat: str,
        student_metadata: Optional[Dict[str, Any]] = None,
        style_rules: Optional[List[str]] = None,
    ) -> BaseModel:
        """
        Menjalankan alur penyusunan draf surat (Fase 1) beserta mekanisme Self-Reflection:
        1. Memuat spesifikasi field dari `required_field_surat.json` berdasarkan `kode_surat`.
        2. Memanggil LLM dengan Structured Outputs yang terikat ke skema Pydantic di `schemas.py`.
        3. Mengevaluasi `evaluation.self_critique_score`: apabila `< 8`, melakukan maksimal
           1 kali iterasi perbaikan otomatis menggunakan `evaluation.revision_notes`.
        4. Mengembalikan instance `AgentSuratDraftOutputSchema` akhir yang siap disimpan ke
           database dengan status `PENDING_APPROVAL`.
        """
        if not user_prompt_context or not user_prompt_context.strip():
            raise SuratAgentValidationError(
                "Konteks permohonan surat (user_prompt_context) wajib diisi."
            )

        required_fields = self.get_required_fields_for_kode(kode_surat)
        output_schema = self.resolve_output_schema(kode_surat, required_fields)

        effective_style_rules = (
            style_rules
            if style_rules is not None
            else self._load_active_style_rules(kode_surat)
        )

        system_prompt = build_system_prompt(
            kode_surat=kode_surat,
            required_fields=required_fields,
            style_rules=effective_style_rules,
        )
        initial_user_prompt = build_initial_user_prompt(
            user_prompt_context=user_prompt_context,
            kode_surat=kode_surat,
            student_metadata=student_metadata,
        )

        logger.info(
            "Memulai penyusunan draf surat (Iterasi 1) untuk kode_surat=%s menggunakan model=%s.",
            kode_surat,
            self.model_name,
        )
        first_draft: BaseModel = self._invoke_structured_llm(
            system_prompt=system_prompt,
            user_prompt=initial_user_prompt,
            response_schema=output_schema,
        )

        initial_score = first_draft.evaluation.self_critique_score
        if initial_score >= self.critique_min_score or self.max_revisions < 1:
            logger.info(
                "Draf surat lulus evaluasi Self-Reflection pada Iterasi 1 (skor=%d/%d).",
                initial_score,
                self.critique_min_score,
            )
            return first_draft

        # Self-Reflection Loop: Maksimal 1 kali iterasi perbaikan otomatis
        logger.info(
            "Skor evaluasi Iterasi 1 (%d) di bawah ambang batas (%d). "
            "Menjalankan 1 kali iterasi perbaikan otomatis berbasis revision_notes.",
            initial_score,
            self.critique_min_score,
        )

        revision_user_prompt = build_self_reflection_revision_prompt(
            user_prompt_context=user_prompt_context,
            kode_surat=kode_surat,
            previous_draft=first_draft.ai_original_draft,
            previous_payload=first_draft.to_payload_dict(),
            previous_score=initial_score,
            revision_notes=first_draft.evaluation.revision_notes,
            required_fields=required_fields,
        )

        revised_draft: BaseModel = self._invoke_structured_llm(
            system_prompt=system_prompt,
            user_prompt=revision_user_prompt,
            response_schema=output_schema,
        )

        logger.info(
            "Iterasi perbaikan Self-Reflection selesai (skor awal=%d, skor akhir=%d).",
            initial_score,
            revised_draft.evaluation.self_critique_score,
        )
        return revised_draft
    
    def draft_letter_with_reflection(
        self,
        user_prompt_context: str,
        kode_surat: str,
        previous_draft: str,
        previous_payload: dict,
        previous_score: int,
        revision_notes: list,
        student_metadata: Optional[dict] = None,
    ):
        """
        Wrapper untuk memproses ulang draf dengan membawa konteks refleksi sebelumnya.
        Untuk sementara bisa mengarah langsung ke method draft_letter utama atau 
        menggunakan prompt khusus perbaikan.
        """
        # Karena user_prompt_context di re-draft sudah digabung dengan koreksi baru,
        # kita bisa langsung melesternya ke method draft_letter utama:
        return self.draft_letter(
            user_prompt_context=user_prompt_context,
            kode_surat=kode_surat,
            student_metadata=student_metadata,
        )

    def run(
        self,
        user_prompt_context: str,
        kode_surat: str,
        student_metadata: Optional[Dict[str, Any]] = None,
        style_rules: Optional[List[str]] = None,
    ) -> BaseModel:
        """Alias eksekusi utama yang memanggil `draft_letter`."""
        return self.draft_letter(
            user_prompt_context=user_prompt_context,
            kode_surat=kode_surat,
            student_metadata=student_metadata,
            style_rules=style_rules,
        )
