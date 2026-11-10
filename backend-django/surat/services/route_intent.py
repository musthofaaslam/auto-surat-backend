import logging
import os
from enum import Enum
from django.conf import settings
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# 1. Definisikan Enum kaku berdasarkan daftar kode surat resmi di database
class SuratIntentEnum(str, Enum):
    SI_MAG = "SI-MAG"
    SI_SUR = "SI-SUR"
    SK_BEA = "SK-BEA"
    SK_KUL = "SK-KUL"
    SP_MAG = "SP-MAG"
    SP_SKC = "SP-SKC"
    SP_TAS = "SP-TAS"
    SP_TRA = "SP-TRA"
    SR_BEA = "SR-BEA"
    SR_MAG = "SR-MAG"

# 2. Definisikan Struktur Output Pydantic
class IntentRouterOutput(BaseModel):
    kode_surat: SuratIntentEnum | None = Field(
        description="Kode surat resmi yang paling sesuai dengan maksud pengguna. Jika sama sekali tidak jelas, kembalikan null."
    )
    alasan: str = Field(description="Alasan singkat mengapa kode surat tersebut dipilih.")

def route_intent_with_ai(user_message: str) -> str | None:
    """
    Lapis kedua: Menggunakan AI dengan Pydantic Structured Outputs 
    ketika keyword matching gagal (mengembalikan None).
    """
    api_key = getattr(settings, "GEMINI_API_KEY", None) or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        logger.warning("GEMINI_API_KEY belum dikonfigurasi untuk AI Intent Router.")
        return None

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
        http_options=types.HttpOptions(timeout=int(timeout_sec * 1000)),
    )
    model_name = getattr(settings, "GEMINI_MODEL_NAME", "gemini-2.5-flash")
    
    prompt = f"""
    Anda adalah sistem klasifikasi permohonan surat dinas akademik perguruan tinggi.
    Tugas Anda adalah menganalisis pesan dari mahasiswa dan menentukan kode surat dinas resmi yang paling relevan.

    Daftar Katalog Resmi Jenis Surat yang Tersedia:
    {catalog_text}

    Pesan Mahasiswa:
    "{user_message}"

    Instruksi:
    1. Pilih HANYA SATU kode_surat dari daftar katalog resmi di atas yang paling tepat mencerminkan maksud permohonan mahasiswa.
    2. Perhatikan konteks semantik:
       - Survei, observasi, atau pengambilan data lapangan non-magang -> SI-SUR
       - Magang kerja industri yang memerlukan izin -> SI-MAG
       - Rekomendasi beasiswa -> SR-BEA
       - Riset skripsi / tugas akhir di laboratorium atau instansi -> SP-TAS
    3. Jika kalimat user sama sekali tidak berkaitan dengan permohonan surat atau terlalu ambigu, kembalikan null pada kode_surat.
    """

    try:
        # Memanggil LLM dengan paksaan struktur Pydantic (Structured Outputs)
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config={
                'response_mime_type': 'application/json',
                'response_schema': IntentRouterOutput,
                'temperature': 0.0,  # Set 0 agar deterministik dan tidak berhalusinasi
            },
        )
        
        # Parse hasil JSON dari AI ke model Pydantic
        result = IntentRouterOutput.model_validate_json(response.text)
        return result.kode_surat.value if result.kode_surat else None

    except Exception as e:
        # Jaring pengaman jika AI error (misal: timeout atau format meleset)
        logger.warning("AI Router Error: %s", e)
        return None
