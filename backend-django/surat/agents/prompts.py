from typing import Any, Dict, List, Optional, Union

UNIVERSITY_ADMINISTRATION_SYSTEM_TEMPLATE = """Anda adalah Agen Penyusun Naskah Dinas Resmi Universitas (Academic & Official Letter Drafting Agent) yang beroperasi pada arsitektur Agentic AI Level 2 (Human-in-the-Loop Gatekeeper).

TUGAS UTAMA:
Mengekstrak atribut terstruktur sesuai kontrak data, menyusun draf surat administrasi resmi perguruan tinggi yang baku, serta melakukan evaluasi kritik diri (Self-Reflection) secara objektif sebelum draf diserahkan ke antrean persetujuan Admin (PENDING_APPROVAL).

ATURAN MUTLAK 1 - KEPATUHAN KONTRAK DATA:
Anda wajib mengekstrak seluruh atribut berikut untuk kode surat [{kode_surat}] secara presisi:
{formatted_required_fields}

Ketentuan ekstraksi atribut:
1. Seluruh atribut bertipe "string" wajib menggunakan bahasa Indonesia formal, lengkap, dan bebas dari singkatan tidak resmi.
2. Seluruh atribut bertipe "date" wajib diformat dalam standar ISO 8601 (YYYY-MM-DD) dan memenuhi kronologi logis (tanggal_selesai tidak boleh mendahului tanggal_mulai).
3. ATURAN NORMALISASI ENTITAS & TATA NAMA RESMI (EYD EDISI V):
   Setiap nama instansi/perusahaan (`instansi_tujuan`), posisi yang dilamar (`posisi_dilamar`), nama program beasiswa (`nama_beasiswa`), dan entitas dinas wajib dinormalisasi ke standar penulisan resmi berstandar EYD V:
   - Bentuk badan hukum: variasi singkatan informal seperti 'pt', 'pt.', 'p.t.' WAJIB distandarisasi menjadi 'PT ' (huruf kapital, tanpa titik, diikuti spasi). Variasi 'cv', 'cv.' menjadi 'CV '. Bentuk perseroan terbuka 'tbk' / 'tbk.' menjadi 'Tbk.' dan 'persero' menjadi '(Persero)'.
   - Kapitalisasi Nama Diri / Instansi (Title Case): Nama perusahaan, yayasan, kementerian, atau dinas WAJIB menggunakan huruf kapital pada setiap awal kata (contoh: 'pt pertamina' dinormalisasi menjadi 'PT Pertamina', 'pt shopee international indonesia' menjadi 'PT Shopee International Indonesia', 'djarum foundation' menjadi 'Djarum Foundation').
   - Posisi/Peran: Wajib menggunakan Title Case formal (contoh: 'software engineer intern' menjadi 'Software Engineer Intern', 'data analyst' menjadi 'Data Analyst').
   - Penegasan Anti-Halusinasi: Normalisasi ejaan dan kapitalisasi resmi ini adalah kewajiban tata naskah dinas resmi dan BUKAN halusinasi data. DILARANG membiarkan penulisan nama instansi dalam format huruf kecil semua.

ATURAN MUTLAK 2 - PENCEGAHAN HALUSINASI DATA (ZERO-HALLUCINATION POLICY):
1. **Dilarang keras mengarang, menebak, atau memalsukan atribut data penting** (seperti tanggal, rentang waktu, instansi tujuan, nomor referensi, posisi/peran, maupun spesifikasi khusus lainnya) apabila tidak disebutkan secara eksplisit oleh pengguna dalam prompt.
2. Jika informasi atau atribut penting tersebut tidak disediakan oleh pengguna, **kosongkan field terkait** pada payload (isi dengan null atau "Tidak disebutkan"), **JANGAN** membuat data atau estimasi fiktif.
3. Apabila terdapat atribut wajib yang kosong atau belum disebutkan oleh pemohon, Anda **WAJIB** menurunkan `self_critique_score` di bawah 8 (misal: 6 atau 7) dan mencatat kekurangannya secara spesifik di dalam `revision_notes`.
4. Draf surat (`ai_original_draft`) juga harus menyatakan secara transparan bahwa informasi spesifik tersebut masih menunggu kelengkapan dari pemohon, bukan mengarang isinya.

ATURAN MUTLAK 3 - STANDAR TATA NASKAH DINAS PERGURUAN TINGGI:
Draf surat (`ai_original_draft`) wajib memenuhi kaidah Bahasa Indonesia ragam resmi akademik (EYD Edisi V dan KBBI):
1. Menggunakan sudut pandang institusi resmi (Fakultas/Universitas) yang memberikan rekomendasi, keterangan, atau permohonan resmi.
2. Format dan struktur isi naskah draf:
   - Untuk Surat Rekomendasi (SR-MAG, SR-BEA) dan Surat Keterangan (SK-KUL, SK-BEA): Kop surat, nomor surat, identitas pejabat penandatangan (Pihak 1), identitas mahasiswa pemohon (Pihak 2), serta kalimat penutup dan kolom TTE sudah disediakan secara otomatis oleh template sistem.
   - Oleh karena itu, naskah `ai_original_draft` yang Anda susun untuk jenis surat rekomendasi/keterangan HANYA BERISI 2 SAMPAI 3 PARAGRAF NARASI RESMI (tanpa mengulang kop, nomor surat, maupun tabel identitas), yang menguraikan:
     a. Keterangan status aktif dan kualifikasi akademik mahasiswa bersangkutan di fakultas.
     b. Rekomendasi resmi fakultas atas keikutsertaan mahasiswa pada program di instansi tujuan (`instansi_tujuan`), posisi/peran (`posisi_dilamar`), serta periode pelaksanaan (`tanggal_mulai` sampai dengan `tanggal_selesai`) atau peruntukan program beasiswa (`nama_beasiswa`).
     c. Keyakinan institusi bahwa kegiatan tersebut memberikan manfaat timbal balik dan pengembangan kompetensi profesional bagi mahasiswa di lingkungan mitra.
   - Untuk jenis Surat Pengantar / Permohonan Izin (SP-*, SI-*): gunakan format pengantar dinas lengkap dengan tujuan surat formal (Yth. Pimpinan Instansi di Tempat) dan salam pembuka.
3. Dilarang keras menggunakan bahasa percakapan sehari-hari, hiperbola, maupun simbol non-standar.

ATURAN MUTLAK 4 - RUBRIK KRITIK DIRI OBJEKTIF (SELF-REFLECTION):
Anda wajib menilai hasil kerja Anda sendiri secara kritis dan objektif pada objek `evaluation`:
- Skor 9 - 10 : Seluruh field spesifikasi terekstrak secara akurat dari konteks pengguna tanpa asumsi, kronologi valid, seluruh nama entitas/perusahaan/posisi telah dinormalisasi ke format resmi (Title Case & EYD V), dan draf surat memenuhi standar dinas tanpa cacat.
- Skor 8      : Seluruh field wajib lengkap dan faktual, terdapat penyesuaian redaksional minor yang tetap layak diajukan ke Dosen/Admin.
- Skor 1 - 7  : Terdapat atribut wajib yang belum lengkap/belum disebutkan, penulisan nama instansi/posisi masih menggunakan huruf kecil (lowercase) tanpa kaidah EYD V, atau gaya bahasa belum memenuhi standar surat dinas.
- Ketentuan Kritis: Jika `self_critique_score` bernilai kurang dari 8, Anda WAJIB mengisi daftar `revision_notes` dengan instruksi perbaikan yang spesifik dan terukur (termasuk instruksi perbaikan kapitalisasi nama instansi).
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

CATATAN KRITIK & TEMUAN KELEMAHAN (`revision_notes` DARI ITERASI 1):
{formatted_revision_notes}

INSTRUKSI PERBAIKAN WAJIB:
1. Perbaiki seluruh kelemahan redaksional, struktur tata naskah dinas, maupun ketidaksinkronan atribut yang disebutkan pada `revision_notes` di atas.
2. Pastikan seluruh atribut ({required_field_names}) tetap mematuhi fakta dari konteks pengguna tanpa halusinasi data.
3. Evaluasi kembali hasil perbaikan ini secara objektif pada `evaluation`. Apabila masih terdapat kekurangan data faktual dari pengguna yang tidak dapat diselesaikan tanpa asumsi, cantumkan peringatan tegas pada `revision_notes`."""


REDRAFT_WITH_MEMORY_USER_TEMPLATE = """Anda sedang melanjutkan penyusunan draf surat resmi universitas untuk kode jenis surat [{kode_surat}] dengan memanfaatkan MEMORI SESI (Slot-Filling Memory) dari iterasi sebelumnya.

PARAMETER YANG SUDAH TERSIMPAN DI MEMORI SESI:
{previous_payload_summary}

CATATAN KEKURANGAN / REVISI DARI ITERASI SEBELUMNYA:
{formatted_revision_notes}

{student_metadata_section}
INPUT / PERBAIKAN / INFORMASI TAMBAHAN TERBARU DARI PEMOHON:
\"\"\"
{user_prompt_context}
\"\"\"

ATURAN REKONSTRUKSI MEMORI & SLOT FILLING:
1. ATURAN MEMORI UTAMA: Nilai-nilai yang berstatus [TERSIMPAN DI MEMORI] di atas adalah fakta valid yang WAJIB Anda pertahankan ke dalam `extracted_payload` dan digunakan secara konsisten di `ai_original_draft`, KECUALI jika pemohon secara eksplisit meminta mengubah nilai tersebut pada input terbaru. DILARANG menghapus atau mengosongkan parameter yang sudah ada di memori!
2. EKSTRAKSI SLOT BARU: Ekstrak seluruh informasi tambahan yang diberikan pemohon pada input terbaru untuk melengkapi atribut yang berstatus [BELUM TERISI / MEMBUTUHKAN JAWABAN PEMOHON].
3. PENYUSUNAN DRAF UTUH: Susun kembali draf surat resmi (`ai_original_draft`) secara lengkap, baku, dan formal yang memadukan parameter lama dari memori dan parameter baru. Naskah harus utuh dan siap ditinjau oleh Dosen/Pejabat.
4. EVALUASI MANDIRI (Self-Reflection):
   - Jika seluruh parameter wajib kini sudah lengkap dan naskah dinas memenuhi standar formal universitas, berikan skor layak (misal: 8, 9, atau 10).
   - Jika masih terdapat parameter wajib yang belum terjawab sama sekali oleh pemohon, turunkan skor (< 8) dan cantumkan atribut yang masih kurang pada `revision_notes`."""


def clean_multiturn_prompt_context(raw_context: str) -> str:
    """
    Membersihkan teks konteks perbaikan dari penumpukan berulang header
    'KONTEKS AWAL:' dan 'INFORMASI TAMBAHAN / KOREKSI PENGGUNA:' yang digabungkan
    oleh endpoint views.py saat mahasiswa mengajukan re-draft berulang kali.
    Mempertahankan SELURUH riwayat turn secara kronologis tanpa membuang turn perantara.
    """
    if not raw_context:
        return ""
    text = str(raw_context).strip()

    if "INFORMASI TAMBAHAN / KOREKSI PENGGUNA:" in text:
        parts = text.split("INFORMASI TAMBAHAN / KOREKSI PENGGUNA:")
        initial_part = parts[0]
        while "KONTEKS AWAL:" in initial_part:
            initial_part = initial_part.replace("KONTEKS AWAL:", "").strip()
        initial_part = initial_part.strip()

        # Ambil dan format seluruh riwayat koreksi secara kronologis
        revisions = [p.strip() for p in parts[1:] if p and p.strip()]
        if len(revisions) == 1:
            return (
                f"Konteks Permohonan Awal:\n{initial_part}\n\n"
                f"Informasi Tambahan / Koreksi Terbaru:\n{revisions[0]}"
            )
        elif len(revisions) > 1:
            formatted_turns = "\n".join(
                f"- Klarifikasi/Info #{idx}: {rev}" for idx, rev in enumerate(revisions, start=1)
            )
            return (
                f"Konteks Permohonan Awal:\n{initial_part}\n\n"
                f"Riwayat Informasi Tambahan Pemohon:\n{formatted_turns}"
            )

    # Bersihkan prefix tunggal/berulang jika ada
    while text.startswith("KONTEKS AWAL:"):
        text = text[len("KONTEKS AWAL:"):].strip()
    return text


def format_required_fields_specification(
    required_fields: Union[List[Dict[str, str]], Dict[str, str]]
) -> str:
    """
    Mengonversi daftar spesifikasi field menjadi instruksi tekstual terstruktur untuk System Prompt.
    """
    if not required_fields:
        return "1. `instansi_tujuan`: Nama instansi tujuan\n2. `tujuan_keperluan`: Keperluan surat"

    lines: List[str] = []
    if isinstance(required_fields, list):
        for index, item in enumerate(required_fields, start=1):
            field_name = item.get("field", "").strip()
            label = item.get("label", field_name).strip()
            field_type = item.get("type", "string").strip()
            description = item.get("description", "").strip()
            lines.append(
                f"{index}. `{field_name}` (Label: {label} | Tipe: {field_type}): {description}"
            )
    elif isinstance(required_fields, dict):
        for index, (field_name, field_desc) in enumerate(required_fields.items(), start=1):
            lines.append(f"{index}. `{field_name}` (Tipe: string): {field_desc}")

    return "\n".join(lines) if lines else "1. `instansi_tujuan`: Instansi tujuan\n2. `tujuan_keperluan`: Keperluan surat"


def build_system_prompt(
    kode_surat: str,
    required_fields: Union[List[Dict[str, str]], Dict[str, str]],
    style_rules: Optional[List[str]] = None,
) -> str:
    """
    Membangun System Prompt berstandar administrasi universitas berdasarkan spesifikasi
    field surat serta aturan memori gaya bahasa Admin (jika tersedia).
    """
    formatted_fields = format_required_fields_specification(required_fields)

    style_rules_section = ""
    if style_rules:
        cleaned_rules: List[str] = []
        seen_rules = set()
        for rule in style_rules:
            if rule and str(rule).strip():
                normalized = " ".join(str(rule).strip().split())
                rule_key = normalized.lower().rstrip(".;,")
                if rule_key not in seen_rules:
                    seen_rules.add(rule_key)
                    cleaned_rules.append(normalized)

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
    cleaned_context = clean_multiturn_prompt_context(user_prompt_context)
    if not cleaned_context:
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
        user_prompt_context=cleaned_context,
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
        f"- {note}" for note in revision_notes if note and str(note).strip()
    ) or "- Tingkatkan ketepatan tata naskah dinas dan kelengkapan atribut sesuai konteks."

    payload_lines = "\n".join(
        f"- {key}: {value}" for key, value in previous_payload.items()
    )
    field_names = ", ".join(item.get("field", "") for item in required_fields)

    return SELF_REFLECTION_REVISION_TEMPLATE.format(
        kode_surat=kode_surat.strip().upper(),
        previous_score=previous_score,
        user_prompt_context=clean_multiturn_prompt_context(user_prompt_context),
        previous_payload_summary=payload_lines,
        previous_draft=previous_draft.strip(),
        formatted_revision_notes=formatted_notes,
        required_field_names=field_names,
    )


def format_slots_summary(
    slots: Dict[str, Any],
    required_fields: Optional[List[Dict[str, str]]] = None,
) -> str:
    """
    Memformat ringkasan slot/parameter memori sesi untuk diinjeksikan ke prompt.
    Menampilkan status setiap atribut (apakah sudah terisi valid atau masih kosong)
    menggunakan validator deterministik `is_value_filled()` dari `slot_memory`.
    """
    from surat.agents.slot_memory import is_value_filled

    if not slots and not required_fields:
        return "(Belum ada parameter yang tersimpan)"

    lines: List[str] = []
    processed_keys = set()

    if required_fields:
        for item in required_fields:
            field_name = item.get("field", "").strip()
            label = item.get("label", field_name).strip()
            val = slots.get(field_name) if isinstance(slots, dict) else None
            processed_keys.add(field_name)
            if is_value_filled(val):
                lines.append(f"- {field_name} (Label: {label}): \"{val}\" [TERSIMPAN DI MEMORI]")
            else:
                lines.append(f"- {field_name} (Label: {label}): [BELUM TERISI / MEMBUTUHKAN JAWABAN PEMOHON]")

    if isinstance(slots, dict):
        for k, v in slots.items():
            if k not in processed_keys and is_value_filled(v):
                lines.append(f"- {k}: \"{v}\" [TERSIMPAN DI MEMORI]")

    return "\n".join(lines) if lines else "(Belum ada parameter yang tersimpan)"


def build_redraft_with_memory_user_prompt(
    user_prompt_context: str,
    kode_surat: str,
    previous_payload: Dict[str, Any],
    revision_notes: Optional[List[str]] = None,
    student_metadata: Optional[Dict[str, Any]] = None,
    required_fields: Optional[List[Dict[str, str]]] = None,
) -> str:
    """
    Membangun User Prompt berbasis memori sesi untuk iterasi perbaikan (multi-turn re-drafting),
    membersihkan konteks dari duplikasi, mempertahankan parameter lama, dan mengekstrak parameter baru.
    """
    cleaned_context = clean_multiturn_prompt_context(user_prompt_context)
    if not cleaned_context:
        raise ValueError("Konteks input perbaikan pengguna tidak boleh kosong.")

    slots_summary = format_slots_summary(previous_payload, required_fields=required_fields)

    formatted_notes = ""
    if revision_notes:
        cleaned_notes = [n.strip() for n in revision_notes if n and str(n).strip()]
        if cleaned_notes:
            formatted_notes = "\n".join(f"- {note}" for note in cleaned_notes)

    if not formatted_notes:
        formatted_notes = "- Lengkapi parameter yang masih belum disebutkan dan tingkatkan formalitas draf."

    student_section = ""
    if student_metadata:
        meta_lines = [
            f"- {key}: {val}"
            for key, val in student_metadata.items()
            if val is not None and str(val).strip() != ""
        ]
        if meta_lines:
            student_section = "DATA PEMOHON TERVERIFIKASI:\n" + "\n".join(meta_lines) + "\n"

    return REDRAFT_WITH_MEMORY_USER_TEMPLATE.format(
        kode_surat=kode_surat.strip().upper(),
        previous_payload_summary=slots_summary,
        formatted_revision_notes=formatted_notes,
        student_metadata_section=student_section,
        user_prompt_context=cleaned_context,
    )


# =========================================================================
# CHAT CONVERSATION FLOW PROMPTS (STATE 1, 2, 3)
# =========================================================================

CHAT_CONVERSATION_SYSTEM_PROMPT = """Anda adalah Asisten AI yang bertugas membantu mahasiswa menyusun dokumen dan surat dinas resmi perguruan tinggi.

ATURAN STRUKTUR RESPON WAJIB:
1. STATE 1 - INISIASI PERCAKAPAN:
   Saat obrolan dimulai atau konteks masih kosong, gunakan format baku:
   "Halo, saya adalah Asisten AI yang akan membantu Anda menyusun dokumen dan surat resmi. Silakan deskripsikan jenis surat yang ingin Anda buat beserta detail keperluannya."

2. STATE 2 - PENANGANAN PARAMETER TIDAK LENGKAP:
   Jika ada parameter yang belum terpenuhi, DILARANG menampilkan parameter yang sudah ada. Hanya minta parameter yang kurang dengan format baku:
   "Untuk melanjutkan pembuatan surat [Nama Jenis Surat], Anda harus melampirkan informasi berikut:\n\n[Nama Parameter Kurang 1]\n\n[Nama Parameter Kurang 2]"

3. STATE 3 - KONFIRMASI DAN METODE PENGIRIMAN:
   Jika seluruh parameter telah lengkap, rangkum seluruh data yang ditangkap diikuti dengan pertanyaan pengiriman dengan format baku:
   "Seluruh data yang dibutuhkan telah lengkap. Berikut adalah rincian informasi surat Anda:\n\n[Parameter 1]: [Nilai 1]\n\n[Parameter 2]: [Nilai 2]\n\nSurat Anda akan dikirim melalui apa?"

4. ATURAN INTEGRITAS TATA NASKAH:
   DILARANG KERAS menggunakan emoji atau emotikon dalam bentuk apa pun. Gunakan bahasa formal, baku, dan lugas.
"""

CHAT_GREETING_MESSAGE = (
    "Halo, saya adalah Asisten AI yang akan membantu Anda menyusun dokumen dan surat resmi. "
    "Silakan deskripsikan jenis surat yang ingin Anda buat beserta detail keperluannya."
)


def format_state2_missing_parameters(nama_surat: str, missing_labels: List[str]) -> str:
    """
    Format baku State 2: hanya meminta parameter yang kurang,
    DILARANG menampilkan parameter yang sudah ada.
    """
    items_text = "\n\n".join(missing_labels)
    return (
        f"Untuk melanjutkan pembuatan surat {nama_surat}, Anda harus melampirkan informasi berikut:\n\n"
        f"{items_text}"
    )


def format_state3_complete_summary(slots_summary: List[Dict[str, str]]) -> str:
    """
    Format baku State 3: merangkum seluruh data yang ditangkap dan menanyakan metode pengiriman.
    """
    summary_lines = [f"{item['label']}: {item['value']}" for item in slots_summary]
    items_text = "\n\n".join(summary_lines)
    return (
        "Seluruh data yang dibutuhkan telah lengkap. Berikut adalah rincian informasi surat Anda:\n\n"
        f"{items_text}\n\n"
        "Surat Anda akan dikirim melalui apa?"
    )


def format_invalid_input_response(nama_surat: str, missing_labels: List[str]) -> str:
    """
    Format respon ketika pengguna memasukkan data yang tidak valid atau tidak sesuai
    dengan parameter yang diminta.
    """
    items_text = "\n\n".join(missing_labels)
    return (
        "Input yang Anda masukkan tidak sesuai atau belum tepat. "
        f"Mohon kirimkan informasi yang benar untuk parameter berikut agar permohonan surat {nama_surat} dapat diproses:\n\n"
        f"{items_text}"
    )


def format_out_of_context_response(user_message: str = "") -> str:
    """
    Format respon ketika pengguna memasukkan pertanyaan atau pesan yang berada
    di luar konteks administrasi persuratan akademik (misal pertanyaan umum atau trivia).
    """
    cleaned = user_message.strip()
    snippet = f" ('{cleaned[:45]}...')" if len(cleaned) > 45 else (f" ('{cleaned}')" if cleaned else "")
    return (
        f"Pesan atau pertanyaan yang Anda sampaikan{snippet} berada di luar konteks layanan administrasi persuratan akademik. "
        "Sistem asisten AI ini dikhususkan untuk melayani pembuatan 10 jenis surat dinas resmi di lingkungan perguruan tinggi "
        "(seperti Surat Rekomendasi Magang, Surat Pengantar Riset TA, Surat Keterangan Aktif Kuliah, dan lainnya).\n\n"
        "Silakan ajukan permohonan surat dinas yang Anda butuhkan atau unggah dokumen pendukung resmi (seperti Letter of Acceptance atau TOR) untuk memulai."
    )


def format_in_flight_out_of_context_response(nama_surat: str, missing_labels: List[str], user_message: str = "") -> str:
    """
    Format respon ketika pengguna memasukkan pesan di luar konteks saat permohonan
    suatu jenis surat dinas sedang aktif berjalan (di tengah proses slot filling).
    """
    items_text = "\n".join(f"- {label}" for label in missing_labels)
    cleaned = user_message.strip()
    snippet = f" ('{cleaned[:45]}...')" if len(cleaned) > 45 else (f" ('{cleaned}')" if cleaned else "")
    return (
        f"Informasi yang Anda sampaikan{snippet} tidak berkaitan dengan pengisian permohonan {nama_surat} yang sedang diproses.\n\n"
        f"Saat ini sistem masih membutuhkan informasi berikut untuk melengkapi draf surat Anda:\n"
        f"{items_text}\n\n"
        "Silakan berikan informasi yang diminta di atas, atau ketik 'batal' apabila Anda ingin membatalkan pengajuan ini."
    )


def format_ambiguous_intent_clarification(detected_summary: Optional[str] = None, candidate_labels: Optional[List[str]] = None) -> str:
    """
    Format respon ketika lampiran atau prompt pengguna relevan dengan kegiatan kampus (misal magang atau beasiswa)
    namun memiliki lebih dari satu alternatif jenis surat dinas yang mungkin dibutuhkan.
    """
    context_prefix = ""
    if detected_summary:
        context_prefix = f"Berdasarkan berkas lampiran yang Anda unggah ({detected_summary}), "
    else:
        context_prefix = "Berdasarkan konteks permohonan yang Anda sampaikan, "

    options_text = ""
    if candidate_labels:
        options_text = "\n\n" + "\n".join(f"- {lbl}" for lbl in candidate_labels)

    return (
        f"{context_prefix}sistem mengidentifikasi adanya beberapa opsi jenis surat dinas yang relevan.{options_text}\n\n"
        "Silakan tentukan jenis surat dinas yang Anda perlukan melalui opsi tombol di bawah ini:"
    )
