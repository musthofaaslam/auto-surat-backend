import logging
import os
from enum import Enum
from typing import List, Optional, Dict, Any
from django.conf import settings
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# 1. Definisikan Enum kaku berdasarkan daftar kode surat resmi di database
class SuratIntentEnum(str, Enum):
    SI_MAG = "SI-MAG"  # Surat Izin Magang
    SI_SUR = "SI-SUR"  # Surat Izin Survey dan Observasi
    SK_BEA = "SK-BEA"  # Surat Keterangan Tidak Menerima Beasiswa
    SK_KUL = "SK-KUL"  # Surat Keterangan Aktif Kuliah
    SP_MAG = "SP-MAG"  # Surat Pengantar Magang
    SP_SKC = "SP-SKC"  # Surat Pengantar SKCK
    SP_TAS = "SP-TAS"  # Surat Pengantar Riset Tugas Akhir
    SP_TRA = "SP-TRA"  # Surat Pengantar Transkip Nilai
    SR_BEA = "SR-BEA"  # Surat Rekomendasi Beasiswa
    SR_MAG = "SR-MAG"  # Surat Rekomendasi Magang


class IntentCategoryEnum(str, Enum):
    OFFICIAL_LETTER = "OFFICIAL_LETTER"            # Definitif menunjuk ke 1 jenis surat
    AMBIGUOUS = "AMBIGUOUS"                        # Relevan dengan persuratan/lampiran, namun memiliki 2+ alternatif surat
    OUT_OF_CONTEXT = "OUT_OF_CONTEXT"              # Tidak ada kaitannya dengan persuratan akademik (misal: trivia, pertanyaan umum)
    GREETING_OR_CHITCHAT = "GREETING_OR_CHITCHAT"  # Salam pembuka murni tanpa permohonan spesifik


# 2. Definisikan Struktur Output Pydantic
class IntentRouterOutput(BaseModel):
    category: IntentCategoryEnum = Field(
        description="Klasifikasi kategori maksud: OFFICIAL_LETTER, AMBIGUOUS, OUT_OF_CONTEXT, atau GREETING_OR_CHITCHAT."
    )
    kode_surat: Optional[SuratIntentEnum] = Field(
        default=None,
        description="Kode surat resmi definitif jika category == OFFICIAL_LETTER. Kosongkan jika AMBIGUOUS atau OUT_OF_CONTEXT."
    )
    candidate_kodes: List[SuratIntentEnum] = Field(
        default_factory=list,
        description="Daftar 2-3 kode surat kandidat jika category == AMBIGUOUS (misal: [SP-MAG, SR-MAG, SI-MAG])."
    )
    detected_document_summary: Optional[str] = Field(
        default=None,
        description="Ringkasan dokumen yang teridentifikasi dari lampiran jika ada (misal: 'Letter of Acceptance Magang PT Telekomunikasi Indonesia')."
    )
    explanation_or_response: str = Field(
        default="",
        description=(
            "Penjelasan atau respon langsung untuk pengguna: "
            "Jika OUT_OF_CONTEXT: jelaskan mengapa tidak relevan dan pandu ke layanan surat dinas. "
            "Jika AMBIGUOUS: sebutkan dokumen/konteks yang dipahami dan ajukan konfirmasi jenis surat yang dibutuhkan. "
            "Jika GREETING: sapaan ramah pengantar."
        )
    )
    extracted_parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Parameter surat yang terekstrak langsung dari berkas lampiran atau pesan (misal: instansi_tujuan, posisi_magang, tanggal_mulai, tanggal_selesai)."
    )


def _build_multimodal_contents(user_prompt: str, attachments: Optional[List[Any]] = None) -> Any:
    """
    Menyusun payload konten multimodal untuk Gemini Client SDK,
    mengubah byte dokumen/gambar menjadi types.Part.from_bytes.
    """
    if not attachments:
        return user_prompt

    parts: List[Any] = [user_prompt]
    for item in attachments:
        try:
            raw_bytes: Optional[bytes] = None
            mime_type = "application/pdf"
            filename = "attachment"

            if isinstance(item, dict):
                raw_bytes = item.get("bytes") or item.get("content") or item.get("data")
                mime_type = str(item.get("mime_type") or item.get("content_type") or "application/pdf")
                filename = str(item.get("name") or item.get("filename") or "attachment")
            elif hasattr(item, "read") and callable(item.read):
                if hasattr(item, "seek") and callable(item.seek):
                    try:
                        item.seek(0)
                    except Exception:
                        pass
                raw_bytes = item.read()
                if hasattr(item, "seek") and callable(item.seek):
                    try:
                        item.seek(0)
                    except Exception:
                        pass
                mime_type = str(getattr(item, "content_type", None) or "application/pdf")
                filename = str(getattr(item, "name", None) or "attachment")
            elif isinstance(item, (bytes, bytearray)):
                raw_bytes = bytes(item)

            if not raw_bytes:
                continue

            try:
                parts.append(types.Part.from_bytes(data=raw_bytes, mime_type=mime_type))
            except Exception:
                parts.append({
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": raw_bytes,
                    },
                    "filename": filename,
                })
        except Exception as exc:
            logger.warning("Gagal memproses berkas lampiran untuk intent router: %s", exc)

    return parts if len(parts) > 1 else user_prompt


def route_intent_with_ai(
    user_message: str, 
    attachments: Optional[List[Any]] = None
) -> IntentRouterOutput:
    """
    Lapis kedua: Menggunakan AI Multimodal dengan Pydantic Structured Outputs 
    untuk mengklasifikasikan pesan dan berkas lampiran pengguna (LoA, TOR, beasiswa).
    Mendukung deteksi intent definitif, kasus ambigu dengan kandidat, out-of-context, dan sapaan.
    """
    cleaned_msg = (user_message or "").strip()
    api_key = getattr(settings, "GEMINI_API_KEY", None) or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        logger.warning("GEMINI_API_KEY belum dikonfigurasi untuk AI Intent Router.")
        # Fallback lokal jika API KEY belum diset
        return _fallback_local_route(cleaned_msg, attachments)

    # Ambil katalog resmi dari database (SuratType) agar prompt AI memiliki konteks lengkap
    from surat.models import SuratType
    try:
        surat_types = list(SuratType.objects.all())
        if surat_types:
            catalog_lines = [f"- {s.kode_surat}: {s.nama_surat}" for s in surat_types]
            catalog_text = "\n".join(catalog_lines)
        else:
            raise ValueError("SuratType kosong di DB")
    except Exception:
        catalog_text = (
            "- SK-KUL: surat keterangan aktif kuliah\n"
            "- SK-BEA: surat keterangan tidak Menerima beasiswa\n"
            "- SP-TRA: surat pengantar transkip nilai\n"
            "- SP-SKC: surat pengantar skck\n"
            "- SP-MAG: surat pengantar magang\n"
            "- SP-TAS: surat pengantar riset tugas akhir\n"
            "- SR-BEA: surat rekomendasi beasiswa\n"
            "- SR-MAG: surat rekomendasi magang\n"
            "- SI-MAG: surat izin magang\n"
            "- SI-SUR: surat izin survey dan observasi"
        )

    timeout_sec = float(getattr(settings, "AGENT_TIMEOUT_SECONDS", 15.0))
    client = genai.Client(
        api_key=str(api_key).strip(),
        http_options=types.HttpOptions(api_version="v1beta", timeout=int(timeout_sec * 1000)),
    )
    model_name = getattr(settings, "GEMINI_MODEL_NAME", "gemini-3.5-flash-lite")
    
    prompt = f"""
    Anda adalah sistem klasifikasi cerdas permohonan surat dinas akademik perguruan tinggi.
    Tugas Anda adalah menganalisis pesan mahasiswa beserta berkas lampiran pendukung yang disertakan (seperti Letter of Acceptance / LoA, bukti penerimaan magang, pengumuman beasiswa, proposal riset skripsi, dll).

    Daftar Katalog Resmi 10 Jenis Surat yang Tersedia:
    {catalog_text}

    Pesan Mahasiswa:
    "{cleaned_msg}"

    Instruksi Klasifikasi (WAJIB DIIKUTI SECARA KETAT):
    1. KATEGORI "OFFICIAL_LETTER":
       - Pilih kategori ini jika pesan atau dokumen lampiran secara pasti dan spesifik merujuk pada SATU jenis surat dinas dari katalog di atas.
       - Tentukan field `kode_surat` sesuai katalog resmi (misal: "SP-MAG", "SK-KUL", "SP-TAS").
       - Ekstrak parameter yang tercantum pada dokumen atau pesan ke dalam `extracted_parameters` (misal instansi_tujuan, posisi_magang, tanggal_mulai, tanggal_selesai).

    2. KATEGORI "AMBIGUOUS":
       - Pilih kategori ini jika dokumen lampiran atau pesan mahasiswa secara jelas berkaitan dengan aktivitas kampus/administrasi (misal: pengajuan magang dari dokumen LoA, atau permohonan beasiswa), namun terdapat LEBIH DARI SATU jenis surat resmi yang mungkin dibutuhkan pemohon:
         * Kegiatan magang (LoA magang / kerja praktek) -> candidate_kodes: ["SP-MAG", "SR-MAG", "SI-MAG"]
         * Pengajuan beasiswa -> candidate_kodes: ["SR-BEA", "SK-BEA"]
         * Kegiatan penelitian / observasi mata kuliah -> candidate_kodes: ["SP-TAS", "SI-SUR"]
       - Isi `candidate_kodes` dengan daftar kode surat yang relevan.
       - Tuliskan ringkasan berkas di `detected_document_summary` (contoh: "Letter of Acceptance Magang dari PT Telekomunikasi Indonesia").
       - Ekstrak seluruh parameter yang sudah dapat dipastikan dari dokumen (instansi_tujuan, posisi_magang, tanggal_mulai, tanggal_selesai) ke dalam `extracted_parameters`.
       - Susun `explanation_or_response` yang menjelaskan bahwa dokumen/permohonan telah teridentifikasi dan tanyakan jenis surat mana yang diinginkan mahasiswa.

    3. KATEGORI "OUT_OF_CONTEXT":
       - Pilih kategori ini jika pesan mahasiswa sama sekali TIDAK BERKAITAN dengan permohonan surat resmi akademik, administrasi kampus, ataupun berkas lampiran (contoh pertanyaan umum, trivia, hewan/alam, resep makanan, lelucon, atau teks acak seperti "harimau punya kaki berapa?").
       - Set `kode_surat` ke null dan `candidate_kodes` kosong.
       - Tuliskan `explanation_or_response` secara santun dan tegas yang menjelaskan bahwa pertanyaan berada di luar konteks layanan persuratan dinas perguruan tinggi dan arahkan pemohon untuk mengajukan jenis surat yang valid.

    4. KATEGORI "GREETING_OR_CHITCHAT":
       - Pilih kategori ini jika pesan hanya berupa salam pembuka murni ("halo", "hai", "selamat pagi", "assalamu'alaikum") tanpa ada berkas lampiran dan tanpa menyebutkan maksud permohonan.
    """

    contents_payload = _build_multimodal_contents(prompt, attachments=attachments)

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=contents_payload,
            config={
                'response_mime_type': 'application/json',
                'response_schema': IntentRouterOutput,
                'temperature': 0.0,
            },
        )
        
        result = IntentRouterOutput.model_validate_json(response.text)
        return result

    except Exception as e:
        logger.warning("AI Multimodal Router Error: %s", e)
        return _fallback_local_route(cleaned_msg, attachments)


def _fallback_local_route(user_message: str, attachments: Optional[List[Any]] = None) -> IntentRouterOutput:
    """
    Fallback deterministik jika LLM gagal atau jaringan bermasalah.
    """
    msg_lower = (user_message or "").lower()
    has_attachment = bool(attachments and len(attachments) > 0)

    # Cek apakah salam murni
    greetings = ["halo", "hai", "hello", "selamat pagi", "selamat siang", "selamat sore", "assalamu'alaikum", "assalamualaikum"]
    if not has_attachment and any(msg_lower == g or msg_lower.startswith(g + " ") for g in greetings) and len(msg_lower.split()) <= 3:
        return IntentRouterOutput(
            category=IntentCategoryEnum.GREETING_OR_CHITCHAT,
            explanation_or_response="Halo, saya adalah Asisten AI yang akan membantu Anda menyusun dokumen dan surat resmi. Silakan deskripsikan jenis surat yang ingin Anda buat beserta detail keperluannya."
        )

    # Jika ada lampiran dan teks menyebut surat sesuai lampiran atau kata magang/loa
    if has_attachment or "loa" in msg_lower or "magang" in msg_lower or "internship" in msg_lower:
        return IntentRouterOutput(
            category=IntentCategoryEnum.AMBIGUOUS,
            candidate_kodes=[SuratIntentEnum.SP_MAG, SuratIntentEnum.SR_MAG, SuratIntentEnum.SI_MAG],
            detected_document_summary="Berkas Lampiran Pengajuan Magang",
            explanation_or_response="Berdasarkan berkas lampiran yang Anda sertakan, permohonan ini teridentifikasi berkaitan dengan kegiatan magang. Silakan tentukan jenis surat dinas magang yang Anda perlukan melalui pilihan berikut:"
        )

    # Cek kata kunci surat beasiswa
    if "beasiswa" in msg_lower:
        return IntentRouterOutput(
            category=IntentCategoryEnum.AMBIGUOUS,
            candidate_kodes=[SuratIntentEnum.SR_BEA, SuratIntentEnum.SK_BEA],
            explanation_or_response="Permohonan Anda berkaitan dengan beasiswa. Silakan pilih apakah Anda membutuhkan Surat Rekomendasi Beasiswa atau Surat Keterangan Tidak Menerima Beasiswa:"
        )

    # Deteksi out-of-context umum (seperti harimau, resep, cuaca, dll)
    out_of_context_tokens = ["harimau", "kaki", "hewan", "resep", "masak", "presiden", "cuaca", "lagu", "film", "siapa", "mengapa"]
    if any(tok in msg_lower for tok in out_of_context_tokens):
        return IntentRouterOutput(
            category=IntentCategoryEnum.OUT_OF_CONTEXT,
            explanation_or_response=f"Pesan yang Anda kirimkan ('{user_message}') berada di luar konteks layanan persuratan akademik. Asisten AI ini dikhususkan untuk melayani pembuatan 10 jenis surat dinas resmi di lingkungan perguruan tinggi."
        )

    return IntentRouterOutput(
        category=IntentCategoryEnum.OUT_OF_CONTEXT,
        explanation_or_response="Pesan atau berkas yang Anda kirimkan belum dapat diidentifikasi sebagai permohonan surat dinas akademik resmi. Silakan sampaikan jenis surat yang ingin Anda ajukan (seperti surat magang, aktif kuliah, riset tugas akhir, atau rekomendasi beasiswa)."
    )
