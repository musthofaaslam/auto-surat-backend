import difflib
import logging
import os
import re
from typing import Any, Dict, List, Optional, Type

try:
    from django.conf import settings
    from django.core.exceptions import ImproperlyConfigured
except ImportError:  # pragma: no cover
    settings = None  # type: ignore[assignment]
    ImproperlyConfigured = Exception  # type: ignore[assignment,misc]

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from surat.agents.letter_agent import (
    SuratAgentConfigurationError,
    SuratAgentError,
    SuratAgentRateLimitError,
    SuratAgentTimeoutError,
    SuratAgentUpstreamError,
    SuratAgentValidationError,
    _get_django_or_env_setting,
)

# SARAN PERBAIKAN ARSITEKTURAL:
# 1. Evaluasi Agentic Memory Loop (Fase 3) dikombinasikan dengan pra-filter deterministik
#    berbasis `difflib.SequenceMatcher` agar panggilan LLM (`gemini-3.8-flash`) hanya
#    dipicu ketika benar-benar terdapat modifikasi teks antara `ai_original_draft` dan
#    `final_approved_content` (menghemat biaya token dan latensi secara signifikan).
# 2. Keluaran analisis diff diikat secara ketat pada skema Pydantic `MemoryDiffEvaluationSchema`
#    menggunakan fitur Structured Outputs, sehingga hanya aturan gaya bahasa yang bersifat
#    substantif (`is_significant=True`) yang disimpan ke tabel `AgentFeedbackMemory`.
# 3. `AgenticMemoryAgent` mendukung Dependency Injection pada parameter `client` serta
#    fallback heuristik terukur apabila dijalankan pada lingkungan terisolasi tanpa koneksi
#    eksternal, menjaga keandalan pipeline pasca-approval di background thread.

logger = logging.getLogger(__name__)


class MemoryAgentError(SuratAgentError):
    """Base exception untuk seluruh kesalahan operasional pada AgenticMemoryAgent."""


class MemoryAgentConfigurationError(SuratAgentConfigurationError, MemoryAgentError):
    """Dilempar ketika konfigurasi API Key atau parameter AgenticMemoryAgent tidak valid."""


class MemoryAgentTimeoutError(SuratAgentTimeoutError, MemoryAgentError):
    """Dilempar ketika permintaan evaluasi diff ke LLM melampaui batas waktu tunggu."""


class MemoryAgentRateLimitError(SuratAgentRateLimitError, MemoryAgentError):
    """Dilempar ketika kuota atau batas frekuensi permintaan (HTTP 429) LLM terlampaui."""


class MemoryAgentUpstreamError(SuratAgentUpstreamError, MemoryAgentError):
    """Dilempar ketika layanan LLM mengalami kegagalan internal atau gangguan jaringan."""


class MemoryAgentValidationError(SuratAgentValidationError, MemoryAgentError):
    """Dilempar ketika keluaran evaluasi diff LLM gagal memenuhi kontrak skema Pydantic."""


MEMORY_DIFF_SYSTEM_PROMPT = """Anda adalah Agen Evaluasi Memori & Gaya Bahasa Administrasi Universitas (Agentic Memory & Style Preference Extractor) yang beroperasi pada Fase 3 (Human-in-the-Loop Feedback Loop).

TUGAS UTAMA:
Membandingkan draf asli yang dihasilkan AI (`ai_original_draft`) dengan naskah akhir yang telah disunting dan disetujui oleh Pejabat/Dosen (`final_approved_content`), lalu mengekstrak aturan pedoman gaya bahasa (style guidelines) yang dapat digunakan kembali pada pembuatan surat berikutnya.

ATURAN EVALUASI SIGNIFIKANSI PERUBAHAN:
1. Tandai `is_significant = true` HANYA apabila terdapat koreksi substantif pada struktur kalimat, pilihan diksi formal/akademik, format sapaan jabatan, penyebutan nama instansi, atau tata naskah dinas.
2. Tandai `is_significant = false` apabila kedua teks identik atau hanya berbeda pada spasi kosong / tanda baca sepele yang tidak mengubah kaidah penulisan.
3. Apabila `is_significant = true`:
   - Susun `diff_summary` yang merangkum secara objektif bagian mana yang diubah oleh Pejabat/Dosen.
   - Susun `extracted_rule` berupa instruksi kaidah penulisan yang bersifat umum, tegas, dan dapat langsung diinjeksikan ke dalam System Prompt untuk kode surat terkait di masa mendatang (jangan menyalin nama mahasiswa spesifik ke dalam aturan umum).
   - Isi `style_guidelines` dengan daftar butir aturan gaya bahasa yang spesifik dan dapat dieksekusi."""


MEMORY_DIFF_USER_TEMPLATE = """Analisis perbedaan antara draf asli AI dan naskah final yang disetujui untuk kode surat [{kode_surat}] berikut:

RASIO KEMIRIPAN TEKS (SEQUENCE MATCHER): {similarity_ratio:.4f}

DRAF ASLI AI (`ai_original_draft`):
\"\"\"
{ai_original_draft}
\"\"\"

NASKAH FINAL DISETUJUI (`final_approved_content`):
\"\"\"
{final_approved_content}
\"\"\"

RINGKASAN UNIFIED DIFF:
\"\"\"
{unified_diff_text}
\"\"\"

Hasilkan evaluasi terstruktur sesuai skema yang ditentukan."""


class MemoryDiffEvaluationSchema(BaseModel):
    """
    Kontrak Structured Output untuk hasil analisis komparasi (diff) antara
    `ai_original_draft` dan `final_approved_content`.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    is_significant: bool = Field(
        ...,
        description=(
            "Bernilai True apabila terdapat perbedaan gaya bahasa, terminologi, atau "
            "struktur redaksional yang signifikan antara draf asli dan teks final."
        ),
    )
    diff_summary: str = Field(
        ...,
        min_length=5,
        description="Ringkasan objektif mengenai perbedaan antara draf AI dan teks final Admin.",
    )
    extracted_rule: str = Field(
        default="",
        description=(
            "Ringkasan aturan pedoman gaya bahasa (style guideline) terpadu yang siap "
            "disimpan ke kolom AgentFeedbackMemory.extracted_rule."
        ),
    )
    style_guidelines: List[str] = Field(
        default_factory=list,
        description="Daftar butir pedoman gaya bahasa hasil ekstraksi koreksi Admin.",
    )

    @property
    def has_significant_changes(self) -> bool:
        """Alias properti untuk memeriksa signifikansi perubahan."""
        return self.is_significant

    @model_validator(mode="after")
    def validate_rule_consistency(self) -> "MemoryDiffEvaluationSchema":
        cleaned_guidelines = [
            item.strip() for item in self.style_guidelines if item and item.strip()
        ]
        self.style_guidelines = cleaned_guidelines

        if self.is_significant:
            if not self.extracted_rule and cleaned_guidelines:
                self.extracted_rule = "; ".join(cleaned_guidelines)
            elif self.extracted_rule and not cleaned_guidelines:
                self.style_guidelines = [self.extracted_rule]

            if not self.extracted_rule or not self.extracted_rule.strip():
                raise ValueError(
                    "Apabila is_significant bernilai True, extracted_rule atau "
                    "style_guidelines wajib memuat minimal satu aturan gaya bahasa."
                )
        return self


class AgenticMemoryAgent:
    """
    Agen pembelajar preferensi gaya bahasa (Fase 3: Agentic Memory & Feedback Loop).
    Menggunakan LLM berbiaya rendah (`gemini-3.8-flash`) untuk membandingkan
    `ai_original_draft` dengan `final_approved_content` dan menyimpan aturan gaya bahasa
    baru ke model `AgentFeedbackMemory` serta `SuratAuditLog`.
    """

    DEFAULT_MODEL_NAME: str = "gemini-3.8-flash"
    FALLBACK_MODELS: tuple = (
        "gemini-3.8-flash",
        "gemini-3.1-flash-lite",
        "gemini-flash-lite-latest",
    )
    DEFAULT_TIMEOUT_SECONDS: float = 20.0
    IDENTICAL_SIMILARITY_THRESHOLD: float = 0.999

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
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
            else str(
                _get_django_or_env_setting(
                    "GEMINI_MEMORY_MODEL_NAME", self.DEFAULT_MODEL_NAME
                )
            )
        )
        self.timeout_seconds: float = float(
            timeout_seconds
            if timeout_seconds is not None
            else _get_django_or_env_setting(
                "AGENT_MEMORY_TIMEOUT_SECONDS", self.DEFAULT_TIMEOUT_SECONDS
            )
        )
        self._client: Optional[Any] = client

    def _get_or_create_client(self) -> Any:
        if self._client is not None:
            return self._client

        if not self.api_key or not self.api_key.strip():
            raise MemoryAgentConfigurationError(
                "Konfigurasi GEMINI_API_KEY belum diatur untuk AgenticMemoryAgent."
            )

        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise MemoryAgentConfigurationError(
                "Pustaka 'google-genai' belum terpasang di environment Python."
            ) from exc

        timeout_ms = int(self.timeout_seconds * 1000)
        http_options = types.HttpOptions(timeout=timeout_ms)
        self._client = genai.Client(
            api_key=self.api_key.strip(),
            http_options=http_options,
        )
        return self._client

    @staticmethod
    def _normalize_whitespace(text: Optional[str]) -> str:
        if not text:
            return ""
        lines = [" ".join(line.strip().split()) for line in str(text).strip().splitlines()]
        return "\n".join(line for line in lines if line)

    @classmethod
    def compute_text_diff(
        cls,
        ai_original_draft: Optional[str],
        final_approved_content: Optional[str],
    ) -> Dict[str, Any]:
        """
        Menghitung rasio kemiripan dan unified diff secara lokal menggunakan `difflib`
        sebelum memutuskan apakah perlu memanggil LLM.
        """
        norm_original = cls._normalize_whitespace(ai_original_draft)
        norm_final = cls._normalize_whitespace(final_approved_content)

        if not norm_original or not norm_final:
            return {
                "has_changes": False,
                "similarity_ratio": 1.0,
                "unified_diff": "",
                "normalized_original": norm_original,
                "normalized_final": norm_final,
            }

        if norm_original == norm_final:
            return {
                "has_changes": False,
                "similarity_ratio": 1.0,
                "unified_diff": "",
                "normalized_original": norm_original,
                "normalized_final": norm_final,
            }

        matcher = difflib.SequenceMatcher(None, norm_original, norm_final)
        ratio = matcher.ratio()
        diff_lines = list(
            difflib.unified_diff(
                norm_original.splitlines(),
                norm_final.splitlines(),
                fromfile="ai_original_draft",
                tofile="final_approved_content",
                lineterm="",
            )
        )
        unified_diff_str = "\n".join(diff_lines)
        has_changes = ratio < cls.IDENTICAL_SIMILARITY_THRESHOLD and bool(diff_lines)

        return {
            "has_changes": has_changes,
            "similarity_ratio": ratio,
            "unified_diff": unified_diff_str,
            "normalized_original": norm_original,
            "normalized_final": norm_final,
        }

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
        raw_schema = response_schema.model_json_schema()
        return cls._sanitize_schema_node(raw_schema)

    def _handle_api_exception(self, exc: BaseException) -> None:
        if isinstance(exc, MemoryAgentError):
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
            raise MemoryAgentTimeoutError(
                f"Permintaan evaluasi memori diff melebihi batas waktu ({self.timeout_seconds} detik).",
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
            raise MemoryAgentRateLimitError(
                "Layanan AI untuk evaluasi memori mencapai batas kuota permintaan (HTTP 429).",
                status_code=429,
                original_exception=exc,
            ) from exc

        if status_code in (401, 403) or "api_key_invalid" in exc_message_lower:
            raise MemoryAgentConfigurationError(
                "Kredensial API Key layanan AI tidak valid untuk evaluasi memori.",
                status_code=status_code or 401,
                original_exception=exc,
            ) from exc

        raise MemoryAgentUpstreamError(
            f"Gangguan komunikasi dengan layanan AI saat evaluasi memori: {exc_message}",
            status_code=status_code or 502,
            original_exception=exc,
        ) from exc

    def _parse_and_validate_response(
        self,
        response: Any,
        response_schema: Type[MemoryDiffEvaluationSchema],
    ) -> MemoryDiffEvaluationSchema:
        if response is None:
            raise MemoryAgentValidationError(
                "Layanan AI mengembalikan respons kosong (None) saat evaluasi diff."
            )

        try:
            parsed_obj = getattr(response, "parsed", None)
            if parsed_obj is not None:
                if isinstance(parsed_obj, BaseModel):
                    return response_schema.model_validate(parsed_obj.model_dump())
                if isinstance(parsed_obj, dict):
                    return response_schema.model_validate(parsed_obj)
                if hasattr(parsed_obj, "__dict__"):
                    return response_schema.model_validate(vars(parsed_obj))

            raw_text = getattr(response, "text", None)
            if isinstance(raw_text, str) and raw_text.strip():
                cleaned_text = raw_text.strip()
                if cleaned_text.startswith("```"):
                    cleaned_text = re.sub(r"^```(?:json)?\s*", "", cleaned_text, flags=re.IGNORECASE)
                    cleaned_text = re.sub(r"\s*```$", "", cleaned_text)
                    cleaned_text = cleaned_text.strip()
                return response_schema.model_validate_json(cleaned_text)

            if isinstance(response, dict):
                return response_schema.model_validate(response)

            raise MemoryAgentValidationError(
                "Respons LLM tidak memuat atribut 'parsed' maupun teks JSON yang valid."
            )
        except ValidationError as exc:
            logger.error("Validasi Structured Output MemoryDiffEvaluationSchema gagal: %s", exc)
            raise MemoryAgentValidationError(
                f"Keluaran agen memori tidak memenuhi skema Pydantic: {exc}",
                original_exception=exc,
            ) from exc

    def _invoke_diff_llm(
        self,
        user_prompt: str,
    ) -> MemoryDiffEvaluationSchema:
        client = self._get_or_create_client()
        json_schema = self._build_gemini_compatible_json_schema(MemoryDiffEvaluationSchema)

        config: Any
        try:
            from google.genai import types

            config = types.GenerateContentConfig(
                system_instruction=MEMORY_DIFF_SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_json_schema=json_schema,
                temperature=0.1,
            )
        except ImportError:
            config = {
                "system_instruction": MEMORY_DIFF_SYSTEM_PROMPT,
                "response_mime_type": "application/json",
                "response_json_schema": json_schema,
                "temperature": 0.1,
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
                status_code in (404, 429, 503)
                or "404" in exc_text
                or "not_found" in exc_text
                or "429" in exc_text
                or "resource_exhausted" in exc_text
                or "quota" in exc_text
                or "rate limit" in exc_text
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
                        "Model memori '%s' tidak tersedia/sibuk (code=%s). Fallback ke '%s'.",
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

        return self._parse_and_validate_response(response, MemoryDiffEvaluationSchema)

    @staticmethod
    def _sanitize_pii_from_text(text: str) -> str:
        """
        Menyensor informasi identitas pribadi (PII) seperti NIM, NIP, nomor telepon,
        email, tanggal spesifik, dan nilai setelah label biodata (Nama/NIM/Alamat)
        agar tidak pernah bocor ke dalam aturan gaya bahasa umum (System Prompt).
        """
        if not text:
            return ""
        sanitized = text
        # Sensor label biodata spesifik beserta nilainya (misal: "Nama: Andi Pratama", "NIM : 240601...")
        sanitized = re.sub(
            r"(?i)\b(nama(?:\s+mahasiswa|\s+lengkap)?|nim|nip|nik|tempat\s*,?\s*tanggal\s+lahir|ttl|alamat|no\.?\s*(?:hp|telp|telepon|wa)|telepon|hp|email)\s*[:=]\s*[^\n,;()]+",
            r"\1: [DATA_MAHASISWA]",
            sanitized,
        )
        # Sensor alamat email
        sanitized = re.sub(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
            "[EMAIL]",
            sanitized,
        )
        # Sensor nomor telepon / WA (08xx, +628xx, 628xx)
        sanitized = re.sub(
            r"(?:\+62|62|0)8[0-9]{7,12}\b",
            "[NO_TELP]",
            sanitized,
        )
        # Sensor deretan angka panjang >= 8 digit (NIM / NIP / NIK / Nomor Akun)
        sanitized = re.sub(r"\b\d{8,20}\b", "[NOMOR_IDENTITAS]", sanitized)
        return sanitized.strip()

    @classmethod
    def _is_purely_biodata_or_pii_line(cls, line: str) -> bool:
        """
        Mendeteksi apakah suatu baris diff semata-mata berisi pengisian biodata/identitas
        mahasiswa dan bukan perubahan struktur kalimat redaksional surat.
        """
        stripped = line.strip()
        if not stripped:
            return True
        if re.match(
            r"(?i)^(nama(?:\s+mahasiswa|\s+lengkap)?|nim|nip|nik|tempat\s*,?\s*tanggal\s+lahir|ttl|alamat|no\.?\s*(?:hp|telp|telepon|wa)|telepon|hp|email|ipk|semester|program\s+studi|prodi|fakultas)\s*[:=]",
            stripped,
        ):
            return True
        return False

    @classmethod
    def _build_heuristic_fallback_evaluation(
        cls,
        diff_meta: Dict[str, Any],
        kode_surat: str,
    ) -> MemoryDiffEvaluationSchema:
        """
        Fallback deterministik apabila API Key tidak tersedia di environment lokal/pengujian
        namun terdapat perbedaan nyata antara draf asli AI dan teks final Admin.
        Dilengkapi filter anti-PII agar data pribadi mahasiswa tidak pernah bocor ke
        tabel `AgentFeedbackMemory` maupun System Prompt mahasiswa lain.
        """
        ratio = diff_meta.get("similarity_ratio", 1.0)
        unified_diff = diff_meta.get("unified_diff", "")
        added_lines = [
            line[1:].strip()
            for line in unified_diff.splitlines()
            if line.startswith("+") and not line.startswith("+++") and line[1:].strip()
        ]

        # Saring baris yang murni merupakan atribut biodata/PII mahasiswa
        stylistic_lines = [
            line for line in added_lines if not cls._is_purely_biodata_or_pii_line(line)
        ]

        if stylistic_lines:
            sanitized_sample = cls._sanitize_pii_from_text(stylistic_lines[0])[:180]
            rule = (
                f"Utamakan gaya redaksi dan struktur kalimat formal sesuai koreksi Pejabat "
                f"pada {kode_surat}: {sanitized_sample}"
            )
        else:
            rule = (
                f"Utamakan struktur kalimat baku, tata letak biodata rapi, dan diksi formal "
                f"sesuai standar koreksi Pejabat pada {kode_surat}."
            )

        summary = (
            f"Terdeteksi revisi redaksional oleh Pejabat/Admin pada kode surat {kode_surat} "
            f"(rasio kemiripan={ratio:.2f})."
        )
        return MemoryDiffEvaluationSchema(
            is_significant=True,
            diff_summary=summary,
            extracted_rule=rule,
            style_guidelines=[rule],
        )

    def compare_drafts(
        self,
        ai_original_draft: Optional[str],
        final_approved_content: Optional[str],
        kode_surat: str = "DEFAULT",
        allow_heuristic_fallback: bool = False,
    ) -> MemoryDiffEvaluationSchema:
        """
        Membandingkan `ai_original_draft` dan `final_approved_content` menggunakan
        model berbiaya rendah (`gemini-3.8-flash`). Jika kedua teks identik atau kosong,
        langsung mengembalikan hasil `is_significant=False` tanpa memanggil LLM.
        """
        diff_meta = self.compute_text_diff(ai_original_draft, final_approved_content)
        if not diff_meta["has_changes"]:
            return MemoryDiffEvaluationSchema(
                is_significant=False,
                diff_summary=(
                    "Tidak terdapat perbedaan signifikan antara ai_original_draft dan "
                    "final_approved_content."
                ),
                extracted_rule="",
                style_guidelines=[],
            )

        normalized_kode = (kode_surat or "DEFAULT").strip().upper()
        user_prompt = MEMORY_DIFF_USER_TEMPLATE.format(
            kode_surat=normalized_kode,
            similarity_ratio=diff_meta["similarity_ratio"],
            ai_original_draft=diff_meta["normalized_original"],
            final_approved_content=diff_meta["normalized_final"],
            unified_diff_text=diff_meta["unified_diff"] or "(Perubahan struktur teks)",
        )

        if self._client is None and (not self.api_key or not self.api_key.strip()):
            if allow_heuristic_fallback:
                logger.info(
                    "GEMINI_API_KEY tidak tersedia; menggunakan evaluasi heuristik lokal "
                    "untuk komparasi memori pada kode_surat=%s.",
                    normalized_kode,
                )
                return self._build_heuristic_fallback_evaluation(diff_meta, normalized_kode)

        logger.info(
            "Menjalankan komparasi Agentic Memory untuk kode_surat=%s menggunakan model=%s "
            "(similarity=%.4f).",
            normalized_kode,
            self.model_name,
            diff_meta["similarity_ratio"],
        )
        evaluation = self._invoke_diff_llm(user_prompt=user_prompt)

        # Sanitasi PII/biodata pasca-LLM sebagai pengaman lapis kedua (Defense-in-Depth)
        # agar meskipun LLM tidak sengaja menyalin NIM/nama/telepon ke dalam aturan,
        # data privat mahasiswa tetap disensor sebelum masuk ke AgentFeedbackMemory.
        if evaluation.extracted_rule:
            sanitized_rule = self._sanitize_pii_from_text(evaluation.extracted_rule)
            if self._is_purely_biodata_or_pii_line(sanitized_rule):
                return MemoryDiffEvaluationSchema(
                    is_significant=False,
                    diff_summary="Perubahan terdeteksi hanya mencakup koreksi biodata spesifik pemohon.",
                    extracted_rule="",
                    style_guidelines=[],
                )
            evaluation.extracted_rule = sanitized_rule

        if evaluation.style_guidelines:
            evaluation.style_guidelines = [
                self._sanitize_pii_from_text(g)
                for g in evaluation.style_guidelines
                if g and not self._is_purely_biodata_or_pii_line(g)
            ]

        return evaluation

    def record_feedback_memory(
        self,
        surat_request: Any,
        ai_original_draft: Optional[str] = None,
        final_approved_content: Optional[str] = None,
        allow_heuristic_fallback: bool = True,
    ) -> Optional[Any]:
        """
        Mengevaluasi perbedaan antara `ai_original_draft` dan `final_approved_content`
        pada sebuah `SuratRequest`. Apabila ditemukan perbedaan signifikan, menyimpan
        aturan gaya bahasa baru ke tabel `AgentFeedbackMemory` dan mencatat log ke
        `SuratAuditLog`.
        """
        from surat.models import AgentFeedbackMemory, SuratAuditLog

        effective_original = (
            ai_original_draft
            if ai_original_draft is not None
            else getattr(surat_request, "ai_original_draft", "")
        )
        effective_final = (
            final_approved_content
            if final_approved_content is not None
            else getattr(surat_request, "final_approved_content", "")
        )

        surat_type_obj = getattr(surat_request, "kode_surat", None)
        kode_surat_str = getattr(surat_type_obj, "kode_surat", str(surat_type_obj or "DEFAULT"))

        evaluation = self.compare_drafts(
            ai_original_draft=effective_original,
            final_approved_content=effective_final,
            kode_surat=kode_surat_str,
            allow_heuristic_fallback=allow_heuristic_fallback,
        )

        if not evaluation.is_significant or not evaluation.extracted_rule.strip():
            logger.info(
                "Tidak ada perubahan gaya bahasa signifikan pada SuratRequest id=%s. "
                "Penyimpanan AgentFeedbackMemory dilewati.",
                getattr(surat_request, "id", None),
            )
            return None

        clean_rule = evaluation.extracted_rule.strip()
        existing_rule = AgentFeedbackMemory.objects.filter(
            kode_surat=surat_type_obj,
            is_active=True,
            extracted_rule__iexact=clean_rule,
        ).first()

        if existing_rule is not None:
            logger.info(
                "Aturan gaya bahasa serupa sudah tersimpan (id=%s) untuk kode_surat=%s. "
                "Penyimpanan duplikat dilewati.",
                existing_rule.id,
                kode_surat_str,
            )
            return existing_rule

        memory_record = AgentFeedbackMemory.objects.create(
            surat_request=surat_request,
            kode_surat=surat_type_obj,
            diff_summary=evaluation.diff_summary,
            extracted_rule=clean_rule,
            is_active=True,
        )

        SuratAuditLog.objects.create(
            surat_request=surat_request,
            action_id="MEM_01",
            action=f"STYLE_RULE_LEARNED: {evaluation.extracted_rule.strip()}"[:255],
        )

        logger.info(
            "Aturan gaya bahasa baru berhasil disimpan ke AgentFeedbackMemory (id=%s) "
            "untuk SuratRequest id=%s (kode_surat=%s).",
            memory_record.id,
            getattr(surat_request, "id", None),
            kode_surat_str,
        )
        return memory_record


# Alias kelas dan fungsi utilitas tingkat modul untuk kemudahan integrasi
SuratMemoryAgent = AgenticMemoryAgent


def compare_and_store_memory(
    surat_request: Any,
    ai_original_draft: Optional[str] = None,
    final_approved_content: Optional[str] = None,
    agent: Optional[AgenticMemoryAgent] = None,
    allow_heuristic_fallback: bool = True,
) -> Optional[Any]:
    """
    Fungsi fasad untuk membandingkan `ai_original_draft` dan `final_approved_content`
    serta menyimpan hasil pembelajarannya ke `AgentFeedbackMemory` apabila signifikan.
    """
    active_agent = agent if agent is not None else AgenticMemoryAgent()
    return active_agent.record_feedback_memory(
        surat_request=surat_request,
        ai_original_draft=ai_original_draft,
        final_approved_content=final_approved_content,
        allow_heuristic_fallback=allow_heuristic_fallback,
    )

