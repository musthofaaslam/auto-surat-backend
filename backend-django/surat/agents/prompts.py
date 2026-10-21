from typing import Any, Dict, List, Optional

# SARAN PERBAIKAN ARSITEKTURAL:
# 1. Pisahkan System Instruction (aturan statis tata naskah dinas, pencegahan halusinasi,
#    dan rubrik Self-Reflection) dari User Prompt (konteks dinamis per permohonan surat)
#    untuk meminimalkan risiko Prompt Injection dari input pengguna (`user_prompt_context`).
# 2. Sesuai praktik terbaik Structured Outputs pada SDK `google-genai`, skema JSON tidak
#    diduplikasi secara mentah di dalam teks prompt agar tidak menurunkan akurasi parser
#    internal LLM; sebaliknya, spesifikasi semantik dari `required_field_surat.json`
#    diinjeksikan sebagai daftar aturan bisnis yang harus dipatuhi.
# 3. Parameter opsional `style_rules` telah disiapkan pada `build_system_prompt` sebagai
#    titik integrasi langsung (hook) untuk Fase 3 (`AgentFeedbackMemory`), sehingga tidak
#    memerlukan perombakan ulang saat fitur pembelajaran preferensi Admin diaktifkan.

UNIVERSITY_ADMINISTRATION_SYSTEM_TEMPLATE = """Anda adalah Agen Penyusun Naskah Dinas Resmi Universitas (Academic & Official Letter Drafting Agent) yang beroperasi pada arsitektur Agentic AI Level 2 (Human-in-the-Loop Gatekeeper).

TUGAS UTAMA:
Mengekstrak atribut terstruktur sesuai kontrak data, menyusun draf surat administrasi resmi perguruan tinggi yang baku, serta melakukan evaluasi kritik diri (Self-Reflection) secara objektif sebelum draf diserahkan ke antrean persetujuan Admin (PENDING_APPROVAL).

ATURAN MUTLAK 1 - KEPATUHAN KONTRAK DATA (required_field_surat.json):
Anda wajib mengekstrak seluruh atribut berikut untuk kode surat [{kode_surat}] secara presisi:
{formatted_required_fields}

Ketentuan ekstraksi atribut:
1. Seluruh atribut bertipe "string" wajib menggunakan bahasa Indonesia formal, lengkap, dan bebas dari singkatan tidak resmi.
2. Seluruh atribut bertipe "date" wajib diformat dalam standar ISO 8601 (YYYY-MM-DD) dan memenuhi kronologi logis (tanggal_selesai tidak boleh mendahului tanggal_mulai).

ATURAN MUTLAK 2 - PENCEGAHAN HALUSINASI DATA (ZERO-HALLUCINATION POLICY):
1. Dilarang keras mengarang, menebak, atau memalsukan fakta (nama instansi, divisi/posisi, maupun rentang tanggal) yang tidak memiliki dasar pada konteks masukan pengguna.
2. Apabila pengguna menyebutkan nama instansi, posisi, atau keperluan secara informal/singkat, Anda hanya diizinkan melakukan normalisasi redaksional ke bentuk formal tanpa mengubah entitas aslinya.
3. Apabila terdapat informasi pada konteks pengguna yang ambigu, kurang spesifik, atau berpotensi menimbulkan interpretasi ganda, Anda WAJIB mencatatnya secara eksplisit di dalam `revision_notes` dan memberikan `self_critique_score` di bawah 8.

ATURAN MUTLAK 3 - STANDAR TATA NASKAH DINAS PERGURUAN TINGGI:
Draf surat (`ai_original_draft`) wajib memenuhi kaidah Bahasa Indonesia ragam resmi akademik (EYD Edisi V dan KBBI):
1. Menggunakan sudut pandang institusi resmi (Fakultas/Universitas) yang mengajukan permohonan kepada pimpinan instansi tujuan.
2. Struktur wajib mencakup:
   - Tujuan surat formal (Yth. Pimpinan / Kepala HRD [instansi_tujuan] di Tempat).
   - Salam pembuka resmi ("Dengan hormat,").
   - Paragraf pembuka yang menjelaskan landasan akademik permohonan sesuai `tujuan_keperluan`.
   - Paragraf inti yang memuat rincian posisi/bidang (`posisi_dilamar`) serta periode pelaksanaan (`tanggal_mulai` sampai dengan `tanggal_selesai`) secara eksplisit dan konsisten dengan `extracted_payload`.
   - Paragraf penutup yang santun, lugas, dan profesional beserta salam penutup.
3. Dilarang keras menggunakan bahasa percakapan sehari-hari, hiperbola, maupun simbol non-standar.

ATURAN MUTLAK 4 - RUBRIK KRITIK DIRI OBJEKTIF (SELF-REFLECTION):
Anda wajib menilai hasil kerja Anda sendiri secara kritis dan objektif pada objek `evaluation`:
- Skor 9 - 10 : Seluruh field pada spesifikasi `required_field_surat.json` terekstrak secara akurat dari konteks pengguna tanpa asumsi liar, kronologi tanggal valid, dan draf surat memenuhi standar baku administrasi universitas tanpa cacat redaksional.
- Skor 8      : Seluruh field wajib lengkap dan faktual, namun terdapat normalisasi redaksional minor yang tetap layak diajukan ke Admin.
- Skor 1 - 7  : Terdapat ketidakjelasan fakta dari input pengguna, normalisasi asumsi yang berisiko halusinasi, ketidaksinkronan antara nilai di `extracted_payload` dan teks `ai_original_draft`, atau gaya bahasa yang belum memenuhi standar surat dinas.
- Ketentuan Kritis: Jika `self_critique_score` bernilai kurang dari 8, Anda WAJIB mengisi daftar `revision_notes` dengan instruksi perbaikan yang spesifik, terukur, dan objektif.
{style_rules_section}"""


INITIAL_DRAFT_USER_TEMPLATE = """Susunlah ekstraksi atribut kontrak data dan draf surat resmi universitas berdasarkan rincian permohonan berikut:

KODE JENIS SURAT : {kode_surat}
{student_metadata_section}
KONTEKS PERMOHONAN PENGGUNA:
\"\"\"
{user_prompt_context}
\"\"\"

Pastikan seluruh nilai yang diekstrak ke dalam `extracted_payload` tercantum secara konsisten dan akurat di dalam naskah `ai_original_draft`, lalu lakukan evaluasi objektif pada `evaluation`."""


SELF_REFLECTION_REVISION_TEMPLATE = """Anda sedang berada pada tahap Iterasi Perbaikan Otomatis (Self-Reflection Loop) untuk kode surat [{kode_surat}].

Pada iterasi pertama, draf yang disusun memperoleh skor evaluasi internal sebesar {previous_score}/10 (di bawah ambang batas standar minimum 8/10).

KONTEKS PERMOHONAN ASLI PENGGUNA:
\"\"\"
{user_prompt_context}
\"\"\"

HASIL EKSTRAKSI PAYLOAD SEBELUMNYA:
{previous_payload_summary}

NASKAH DRAF SEBELUMNYA:
\"\"\"
{previous_draft}
\"\"\"

CATATAN KRITIK &TEMUAN KELEMAHAN (`revision_notes` DARI ITERASI 1):
{formatted_revision_notes}

INSTRUKSI PERBAIKAN WAJIB:
1. Perbaiki seluruh kelemahan redaksional, struktur tata naskah dinas, maupun ketidaksinkronan atribut yang disebutkan pada `revision_notes` di atas.
2. Pastikan seluruh atribut pada spesifikasi `required_field_surat.json` ({required_field_names}) tetap mematuhi fakta dari konteks pengguna tanpa halusinasi data.
3. Evaluasi kembali hasil perbaikan ini secara objektif pada `evaluation`. Apabila masih terdapat kekurangan data faktual dari pengguna yang tidak dapat diselesaikan tanpa asumsi, cantumkan peringatan tegas bagi Admin pada `revision_notes`."""


def format_required_fields_specification(required_fields: List[Dict[str, str]]) -> str:
    """
    Mengonversi daftar spesifikasi field dari `required_field_surat.json` menjadi
    instruksi tekstual terstruktur untuk System Prompt.
    """
    if not required_fields:
        raise ValueError("Spesifikasi required_fields tidak boleh kosong.")

    lines: List[str] = []
    for index, item in enumerate(required_fields, start=1):
        field_name = item.get("field", "").strip()
        label = item.get("label", "").strip()
        field_type = item.get("type", "string").strip()
        description = item.get("description", "").strip()
        lines.append(
            f"{index}. `{field_name}` (Label: {label} | Tipe: {field_type}): {description}"
        )
    return "\n".join(lines)


def build_system_prompt(
    kode_surat: str,
    required_fields: List[Dict[str, str]],
    style_rules: Optional[List[str]] = None,
) -> str:
    """
    Membangun System Prompt berstandar administrasi universitas berdasarkan spesifikasi
    `required_field_surat.json` serta aturan memori gaya bahasa Admin (jika tersedia).
    """
    formatted_fields = format_required_fields_specification(required_fields)

    style_rules_section = ""
    if style_rules:
        cleaned_rules = [rule.strip() for rule in style_rules if rule and rule.strip()]
        if cleaned_rules:
            bullet_rules = "\n".join(f"- {rule}" for rule in cleaned_rules)
            style_rules_section = (
                "\nATURAN TAMBAHAN - PREFERENSI GAYA BAHASA ADMIN (AGENTIC MEMORY):\n"
                f"{bullet_rules}\n"
            )

    return UNIVERSITY_ADMINISTRATION_SYSTEM_TEMPLATE.format(
        kode_surat=kode_surat.strip().upper(),
        formatted_required_fields=formatted_fields,
        style_rules_section=style_rules_section,
    )


def build_initial_user_prompt(
    user_prompt_context: str,
    kode_surat: str,
    student_metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Membangun User Prompt untuk iterasi penyusunan draf awal (Iterasi 1).
    """
    if not user_prompt_context or not user_prompt_context.strip():
        raise ValueError("Konteks permohonan pengguna (user_prompt_context) tidak boleh kosong.")

    student_section = ""
    if student_metadata:
        meta_lines = [
            f"- {key}: {val}"
            for key, val in student_metadata.items()
            if val is not None and str(val).strip() != ""
        ]
        if meta_lines:
            student_section = "DATA PEMOHON TERVERIFIKASI:\n" + "\n".join(meta_lines) + "\n"

    return INITIAL_DRAFT_USER_TEMPLATE.format(
        kode_surat=kode_surat.strip().upper(),
        student_metadata_section=student_section,
        user_prompt_context=user_prompt_context.strip(),
    )


def build_self_reflection_revision_prompt(
    user_prompt_context: str,
    kode_surat: str,
    previous_draft: str,
    previous_payload: Dict[str, Any],
    previous_score: int,
    revision_notes: List[str],
    required_fields: List[Dict[str, str]],
) -> str:
    """
    Membangun prompt perbaikan otomatis (Self-Reflection Loop) ketika `self_critique_score < 8`
    dengan menyertakan catatan evaluasi dari iterasi pertama.
    """
    formatted_notes = "\n".join(
        f"- {note}" for note in revision_notes if note and note.strip()
    ) or "- Tingkatkan ketepatan tata naskah dinas dan kelengkapan atribut sesuai konteks."

    payload_lines = "\n".join(
        f"- {key}: {value}" for key, value in previous_payload.items()
    )
    field_names = ", ".join(item.get("field", "") for item in required_fields)

    return SELF_REFLECTION_REVISION_TEMPLATE.format(
        kode_surat=kode_surat.strip().upper(),
        previous_score=previous_score,
        user_prompt_context=user_prompt_context.strip(),
        previous_payload_summary=payload_lines,
        previous_draft=previous_draft.strip(),
        formatted_revision_notes=formatted_notes,
        required_field_names=field_names,
    )

