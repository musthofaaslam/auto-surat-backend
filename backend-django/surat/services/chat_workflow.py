import re
from typing import Dict, Any, Optional
from surat.models import SuratType, ChatThread
from .detect_intent import detect_intent_dynamically, STOP_WORDS, CATEGORY_WORDS
from .route_intent import route_intent_with_ai, IntentCategoryEnum, IntentRouterOutput
from surat.agents.letter_agent import SuratDraftingAgent
from surat.agents.prompts import (
    CHAT_GREETING_MESSAGE,
    format_state2_missing_parameters,
    format_state3_complete_summary,
    format_invalid_input_response,
    format_out_of_context_response,
    format_in_flight_out_of_context_response,
    format_ambiguous_intent_clarification,
)


MONTH_MAP = {
    "januari": 1, "jan": 1, "january": 1,
    "februari": 2, "feb": 2, "pebruari": 2, "february": 2,
    "maret": 3, "mar": 3, "march": 3,
    "april": 4, "apr": 4,
    "mei": 5, "may": 5,
    "juni": 6, "jun": 6, "june": 6,
    "juli": 7, "jul": 7, "july": 7,
    "agustus": 8, "agu": 8, "ags": 8, "aug": 8, "august": 8,
    "september": 9, "sep": 9, "sept": 9,
    "oktober": 10, "okt": 10, "oct": 10, "october": 10,
    "november": 11, "nov": 11, "nopember": 11,
    "desember": 12, "des": 12, "dec": 12, "december": 12,
}

DATE_ONLY_WORDS = set(MONTH_MAP.keys()) | {
    "tanggal", "tgl", "bulan", "bln", "tahun", "thn",
    "sampai", "sd", "hingga", "mulai", "selesai", "dari", "ke",
    "hari", "senin", "selasa", "rabu", "kamis", "jumat", "sabtu", "minggu",
}


def get_current_year() -> int:
    from datetime import date as dt_date
    from django.utils import timezone

    try:
        return timezone.localdate().year
    except Exception:
        return dt_date.today().year


def is_pure_date_expression(text: str) -> bool:
    """
    Mendeteksi apakah suatu teks murni merupakan ekspresi tanggal atau angka
    tanpa konteks nama instansi, keperluan, posisi, atau teks deskriptif lainnya.
    """
    if not text or not str(text).strip():
        return False
    cleaned = str(text).strip().lower()

    if re.match(r'^\d{1,4}[/-]\d{1,2}(?:[/-]\d{1,4})?$', cleaned):
        return True

    words = re.findall(r'[a-zA-Z]+', cleaned)
    digits = re.findall(r'\d+', cleaned)

    if len(words) == 0:
        return True

    if all(w in DATE_ONLY_WORDS for w in words) and (
        len(digits) > 0 or any(w in MONTH_MAP for w in words)
    ):
        return True

    return False


def is_out_of_context_message(user_message: str) -> bool:
    """
    Mendeteksi apakah pesan pengguna di tengah sesi jelas-jelas di luar konteks
    administrasi persuratan akademik (misal pertanyaan trivia, hewan, lelucon, dll).
    """
    msg_lower = (user_message or "").strip().lower()
    if not msg_lower:
        return False

    # Daftar kata pemicu topik non-akademik / trivia
    trivia_tokens = [
        "harimau", "singa", "kucing", "anjing", "hewan", "kaki berapa",
        "resep", "masak", "cuaca", "presiden", "ibukota", "siapa nama",
        "lagu", "film", "puisi", "lelucon", "cerita", "jokes", "tebak",
        "berapa kaki", "punya kaki", "kaki berapa", "kenapa langit", "warna langit"
    ]
    if any(tok in msg_lower for tok in trivia_tokens):
        return True

    academic_keywords = {
        "surat", "magang", "kampus", "dosen", "kuliah", "instansi", "perusahaan",
        "pt", "cv", "dinas", "jalan", "alamat", "tanggal", "bulan", "tahun", "tgl",
        "posisi", "keperluan", "skripsi", "tugas akhir", "beasiswa", "skck", "transkrip",
        "lanjut", "batal", "email", "telegram"
    }
    words = set(re.findall(r'\w+', msg_lower))
    if ("?" in user_message or any(w in words for w in ["siapa", "mengapa", "kenapa", "gimana", "berapa"])) and not words.intersection(academic_keywords):
        return True

    return False


def normalize_and_validate_date_slot(
    raw_value: Any,
    user_message: str,
    has_attachments: bool = False,
) -> Optional[str]:
    """
    Memvalidasi dan menormalisasi nilai slot bertipe tanggal ke format YYYY-MM-DD.
    Apabila pengguna tidak menyebutkan tahun 4-digit pada pesannya, tahun otomatis
    mengikuti tahun berjalan saat ini (misal 2026) agar LLM tidak mengarang tahun.
    """
    from datetime import date as dt_date

    if raw_value is None:
        return None
    text = str(raw_value).strip()
    if not text:
        return None

    msg_lower = (user_message or "").lower()
    if not has_attachments:
        has_digit = bool(re.search(r'\d', msg_lower))
        has_month_word = any(w in MONTH_MAP for w in re.findall(r'[a-zA-Z]+', msg_lower))
        if not has_digit and not has_month_word:
            return None

    explicit_years = re.findall(r'\b((?:19|20)\d{2})\b', user_message or "")
    user_specified_year = len(explicit_years) > 0 or has_attachments
    current_year = get_current_year()

    # 1. Format ISO YYYY-MM-DD
    m_iso = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})$', text)
    if m_iso:
        year, month, day = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
        if not user_specified_year:
            year = current_year
        try:
            dt_date(year, month, day)
            return f"{year:04d}-{month:02d}-{day:02d}"
        except ValueError:
            return None

    # 2. Format tanggal dengan nama bulan (contoh: "10 November" atau "10 November 2026")
    m_named = re.search(r'\b(\d{1,2})\s+([a-zA-Z]+)(?:\s+(\d{4}))?\b', text)
    if m_named and m_named.group(2).lower() in MONTH_MAP:
        day = int(m_named.group(1))
        month = MONTH_MAP[m_named.group(2).lower()]
        year = int(m_named.group(3)) if (m_named.group(3) and user_specified_year) else current_year
        try:
            dt_date(year, month, day)
            return f"{year:04d}-{month:02d}-{day:02d}"
        except ValueError:
            return None

    # 3. Format numerik DD/MM/YYYY atau DD-MM-YYYY atau DD/MM
    m_num = re.search(r'\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b', text)
    if m_num:
        day = int(m_num.group(1))
        month = int(m_num.group(2))
        if m_num.group(3) and user_specified_year:
            year = int(m_num.group(3))
            if year < 100:
                year += 2000
        else:
            year = current_year
        try:
            dt_date(year, month, day)
            return f"{year:04d}-{month:02d}-{day:02d}"
        except ValueError:
            return None

    return None


def validate_and_normalize_slot(
    field_def: Dict[str, Any],
    raw_value: Any,
    user_message: str,
    has_attachments: bool = False,
) -> Optional[str]:
    """
    Memvalidasi kesesuaian tipe antara definisi parameter (date vs string)
    dengan nilai yang diekstrak serta menormalisasi tahun pada tanggal.
    """
    if raw_value is None:
        return None
    field_name = str(field_def.get("field") or "").strip()
    field_type = str(field_def.get("type") or "string").strip().lower()

    cleaned_val = sanitize_extracted_slot(field_name, raw_value)
    if not isinstance(cleaned_val, str):
        cleaned_val = str(cleaned_val).strip()
    else:
        cleaned_val = cleaned_val.strip()

    if not cleaned_val or cleaned_val.lower() in ("null", "none", "tidak disebutkan", "-"):
        return None

    is_date_field = field_type == "date" or field_name.startswith("tanggal_")
    if is_date_field:
        return normalize_and_validate_date_slot(
            cleaned_val,
            user_message=user_message,
            has_attachments=has_attachments,
        )

    if is_pure_date_expression(cleaned_val):
        return None
    if not has_attachments and is_pure_date_expression(user_message):
        return None
    if len(cleaned_val) < 2:
        return None

    return cleaned_val


def get_effective_required_fields(surat_type) -> list:
    """
    Mengambil daftar required_fields dari kolom `SuratType.required_payload_fields` di DB.
    Apabila kosong di DB, otomatis mengambil dari kamus `required_field_surat.json`
    melalui `SuratDraftingAgent.get_required_fields_for_kode()` agar slot filling tidak pernah kosong.
    """
    db_fields = getattr(surat_type, "required_payload_fields", None)
    if isinstance(db_fields, list) and len(db_fields) > 0:
        return db_fields
    try:
        agent = SuratDraftingAgent()
        return agent.get_required_fields_for_kode(surat_type.kode_surat)
    except Exception:
        return []


def handle_incoming_chat_with_redis(
    thread_id: str, 
    user_message: str, 
    session_data: dict,
    attachments: Optional[list] = None
) -> str:
    """
    Menangani alur chat menggunakan state di Redis Cache 
    dan mensinkronikannya dengan model ChatThread di PostgreSQL.
    Mendukung deteksi intent multimodal (teks + gambar/dokumen LoA),
    resolusi ambiguitas dengan kandidat tombol, out-of-context guard,
    dan preservasi parameter dokumen tanpa pengulangan.
    """
    cleaned_msg = user_message.strip()
    
    active_intent = session_data.get("intent")
    waiting_confirmation = session_data.get("is_waiting_for_switch_confirmation", False)
    waiting_clarification = session_data.get("is_waiting_for_intent_clarification", False)

    # Ambil instance ChatThread di database untuk update field document_type jika perlu
    thread_obj = ChatThread.objects.filter(id=thread_id).first()

    # 1. Cek apakah sedang menunggu konfirmasi switch intent
    if waiting_confirmation:
        return handle_switch_confirmation_redis(cleaned_msg, thread_id, session_data, thread_obj)

    # 2. Cek apakah sedang menunggu klarifikasi jenis surat (Ambiguity Resolution)
    if waiting_clarification:
        return handle_intent_clarification_choice(cleaned_msg, thread_id, session_data, thread_obj, attachments=attachments)

    # 3. Deteksi intent dari pesan user (Lapis 1 Keyword)
    detected_kode_surat = detect_intent_dynamically(cleaned_msg)

    # 4. KASUS A: Belum ada intent yang terkunci (Sesi baru)
    if not active_intent:
        if detected_kode_surat:
            surat_obj = SuratType.objects.get(kode_surat=detected_kode_surat)
            session_data["intent"] = detected_kode_surat
            if thread_obj:
                thread_obj.document_type = detected_kode_surat
                thread_obj.title = f"Permohonan {surat_obj.nama_surat}"
                thread_obj.save(update_fields=['document_type', 'title', 'updated_at'])
            return process_slot_filling_redis(cleaned_msg, session_data, is_initial_turn=True, attachments=attachments)

        # Lapis 2: AI Multimodal Intent Router (menganalisis teks & lampiran berkas LoA/TOR/PDF)
        router_result = route_intent_with_ai(cleaned_msg, attachments=attachments)

        if router_result.category == IntentCategoryEnum.OFFICIAL_LETTER and router_result.kode_surat:
            final_kode = router_result.kode_surat.value
            try:
                surat_obj = SuratType.objects.get(kode_surat=final_kode)
                nama_surat = surat_obj.nama_surat
            except SuratType.DoesNotExist:
                nama_surat = final_kode

            session_data["intent"] = final_kode
            if router_result.extracted_parameters:
                cur = session_data.get("slots", {})
                cur.update(router_result.extracted_parameters)
                session_data["slots"] = cur

            if thread_obj:
                thread_obj.document_type = final_kode
                thread_obj.title = f"Permohonan {nama_surat}"
                thread_obj.save(update_fields=['document_type', 'title', 'updated_at'])

            return process_slot_filling_redis(cleaned_msg, session_data, is_initial_turn=True, attachments=attachments)

        elif router_result.category == IntentCategoryEnum.AMBIGUOUS:
            cand_kodes = [k.value for k in router_result.candidate_kodes]
            session_data["is_waiting_for_intent_clarification"] = True
            session_data["candidate_intents"] = cand_kodes
            session_data["staged_slots"] = router_result.extracted_parameters
            session_data["staged_document_summary"] = router_result.detected_document_summary

            candidate_labels = []
            for c in cand_kodes:
                try:
                    st = SuratType.objects.get(kode_surat=c)
                    candidate_labels.append(f"{st.nama_surat} ({c})")
                except Exception:
                    candidate_labels.append(c)

            if router_result.explanation_or_response and len(router_result.explanation_or_response) > 15:
                return router_result.explanation_or_response
            return format_ambiguous_intent_clarification(router_result.detected_document_summary, candidate_labels)

        elif router_result.category == IntentCategoryEnum.OUT_OF_CONTEXT:
            if router_result.explanation_or_response and len(router_result.explanation_or_response) > 15:
                return router_result.explanation_or_response
            return format_out_of_context_response(cleaned_msg)

        elif router_result.category == IntentCategoryEnum.GREETING_OR_CHITCHAT:
            return CHAT_GREETING_MESSAGE

        return format_out_of_context_response(cleaned_msg)

    # 5. KASUS B: Intent sudah terkunci, tapi user mendadak menyebutkan intent BARU
    if detected_kode_surat and detected_kode_surat != active_intent:
        old_surat = SuratType.objects.get(kode_surat=active_intent)
        new_surat = SuratType.objects.get(kode_surat=detected_kode_surat)
        
        session_data["pending_intent"] = detected_kode_surat
        session_data["pending_user_message"] = cleaned_msg
        session_data["is_waiting_for_switch_confirmation"] = True
        
        return (
            f"Perhatian: Sesi saat ini sedang memproses **{old_surat.nama_surat}**. "
            f"Apakah Anda ingin membatalkan draf tersebut dan beralih membuat **{new_surat.nama_surat}**?\n\n"
            f"Silakan pilih salah satu opsi di bawah ini:"
        )

    # 6. KASUS C: Lanjutkan proses Slot Filling
    return process_slot_filling_redis(cleaned_msg, session_data, attachments=attachments)


def handle_intent_clarification_choice(
    user_message: str,
    thread_id: str,
    session_data: dict,
    thread_obj: Optional[ChatThread],
    attachments: Optional[list] = None,
) -> str:
    """
    Menangani pemilihan jenis surat ketika sesi dalam status AMBIGUOUS / menunggu klarifikasi.
    Secara otomatis memasukkan parameter yang sudah tersimpan di staged_slots (dari LoA/lampiran)
    sehingga mahasiswa tidak perlu menginput ulang data yang ada di dokumen.
    """
    cleaned = user_message.strip()
    cleaned_lower = cleaned.lower()
    candidate_intents = session_data.get("candidate_intents", [])

    chosen_code = None

    # 1. Cek kecocokan langsung kode surat (misal "SP-MAG", "SR-MAG", "SI-MAG")
    for cand in candidate_intents:
        if cleaned.upper() == cand or cand.lower() in cleaned_lower:
            chosen_code = cand
            break

    # 2. Cek kecocokan berdasarkan kata kunci spesifik
    if not chosen_code:
        for cand in candidate_intents:
            try:
                st = SuratType.objects.get(kode_surat=cand)
                st_name_lower = st.nama_surat.lower()
                if "pengantar" in cleaned_lower and "pengantar" in st_name_lower:
                    chosen_code = cand
                    break
                elif "rekomendasi" in cleaned_lower and "rekomendasi" in st_name_lower:
                    chosen_code = cand
                    break
                elif "izin" in cleaned_lower and "izin" in st_name_lower:
                    chosen_code = cand
                    break
                elif "aktif" in cleaned_lower and "aktif" in st_name_lower:
                    chosen_code = cand
                    break
                elif "tidak menerima" in cleaned_lower and "tidak menerima" in st_name_lower:
                    chosen_code = cand
                    break
            except Exception:
                pass

    # 3. Cek pemilihan berdasarkan nomor urut (1, 2, 3)
    if not chosen_code and cleaned.isdigit():
        idx = int(cleaned) - 1
        if 0 <= idx < len(candidate_intents):
            chosen_code = candidate_intents[idx]

    if not chosen_code:
        # Jika user mengetik pembatalan
        if cleaned_lower in ["batal", "cancel", "stop", "reset"]:
            session_data["is_waiting_for_intent_clarification"] = False
            session_data["candidate_intents"] = []
            session_data["staged_slots"] = {}
            return "Permohonan surat telah dibatalkan. Silakan sampaikan jenis surat dinas yang Anda butuhkan jika ingin memulai kembali."

        # Ulangi pertanyaan klarifikasi jika pilihan belum jelas
        candidate_labels = []
        for c in candidate_intents:
            try:
                st = SuratType.objects.get(kode_surat=c)
                candidate_labels.append(f"{st.nama_surat} ({c})")
            except Exception:
                candidate_labels.append(c)
        doc_summary = session_data.get("staged_document_summary")
        return format_ambiguous_intent_clarification(doc_summary, candidate_labels)

    # 4. Kunci intent terpilih dan pindahkan staged_slots ke memori aktif
    session_data["is_waiting_for_intent_clarification"] = False
    session_data["intent"] = chosen_code
    session_data["candidate_intents"] = []

    staged_slots = session_data.pop("staged_slots", {}) or {}
    current_slots = session_data.get("slots", {}) or {}
    for k, v in staged_slots.items():
        if v and not current_slots.get(k):
            current_slots[k] = v
    session_data["slots"] = current_slots

    try:
        surat_obj = SuratType.objects.get(kode_surat=chosen_code)
        nama_surat = surat_obj.nama_surat
    except Exception:
        nama_surat = chosen_code

    if thread_obj:
        thread_obj.document_type = chosen_code
        thread_obj.title = f"Permohonan {nama_surat}"
        thread_obj.save(update_fields=['document_type', 'title', 'updated_at'])

    # Jalankan slot filling dengan memori yang sudah di-stage dari LoA/lampiran
    slot_reply = process_slot_filling_redis(
        user_message="",
        session_data=session_data,
        is_initial_turn=True,
        attachments=attachments,
    )
    return f"Jenis surat dikonfirmasi: **{nama_surat} ({chosen_code})**.\n\n{slot_reply}"



def handle_switch_confirmation_redis(user_message: str, thread_id: str, session_data: dict, thread_obj) -> str:
    message_lower = user_message.strip().lower()
    
    is_confirm_yes = (
        message_lower in ["ya", "y", "beralih", "lanjutkan", "setuju", "ya, beralih surat", "ganti", "ya, ganti surat"]
        or message_lower.startswith("ya")
    )

    if is_confirm_yes:
        old_code = session_data.get("intent")
        new_code = session_data.get("pending_intent")
        pending_msg = session_data.get("pending_user_message") or ""
        
        # Pindahkan intent, reset slot, matikan flag konfirmasi
        session_data["intent"] = new_code
        session_data["pending_intent"] = None
        session_data["pending_user_message"] = None
        session_data["is_waiting_for_switch_confirmation"] = False
        session_data["slots"] = {}  # Reset bersih cicilan data lama
        
        try:
            new_surat_obj = SuratType.objects.get(kode_surat=new_code)
            nama_surat = new_surat_obj.nama_surat
        except SuratType.DoesNotExist:
            nama_surat = new_code or "Surat Baru"
            new_surat_obj = None
        
        # Perbarui juga di tabel ChatThread PostgreSQL
        if thread_obj and new_surat_obj:
            thread_obj.document_type = new_code
            thread_obj.title = f"Permohonan {nama_surat}"
            thread_obj.save(update_fields=['document_type', 'title', 'updated_at'])
            
        slot_reply = process_slot_filling_redis(pending_msg, session_data, is_initial_turn=True)
        return (
            f"Draf sebelumnya ({old_code}) telah dibatalkan. Berhasil beralih ke **{nama_surat}**.\n\n"
            f"{slot_reply}"
        )
    
    else:
        session_data["pending_intent"] = None
        session_data["pending_user_message"] = None
        session_data["is_waiting_for_switch_confirmation"] = False
        
        active_code = session_data.get("intent")
        try:
            active_surat_obj = SuratType.objects.get(kode_surat=active_code)
            nama_surat = active_surat_obj.nama_surat
        except SuratType.DoesNotExist:
            nama_surat = active_code or "Surat Aktif"
            
        slot_reply = process_slot_filling_redis("", session_data, is_initial_turn=False)
        return (
            f"Baik, peralihan dibatalkan. Kita tetap melanjutkan pengisian untuk **{nama_surat}**.\n\n"
            f"{slot_reply}"
        )


def process_slot_filling_redis(
    user_message: str, 
    session_data: dict, 
    is_initial_turn: bool = False,
    attachments: Optional[list] = None
) -> str:
    """
    Mengelola slot filling secara fleksibel (mendukung input acak/terbalik serta berkas lampiran)
    serta membersihkan slot menggunakan fungsi sanitizer.
    """
    try:
        surat_type = SuratType.objects.get(kode_surat=session_data.get("intent"))
    except SuratType.DoesNotExist:
        return "Terjadi kesalahan sistem: Jenis surat tidak ditemukan."

    required_fields = get_effective_required_fields(surat_type)
    current_slots = session_data.get("slots", {})
    
    main_slots_complete = bool(required_fields) and all(
        item.get("field") in current_slots and bool(current_slots[item.get("field")])
        for item in required_fields
    )

    if main_slots_complete:
        # Jika slot utama sudah lengkap, cek apakah user sedang menjawab pilihan destinasi
        msg_lower = user_message.lower()
        if not current_slots.get("chosen_destination"):
            if "email" in msg_lower:
                current_slots["chosen_destination"] = "email"
                email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', user_message)
                if email_match:
                    current_slots["target_destination_address"] = email_match.group(0)
                    session_data["slots"] = current_slots
                    return (
                        f"Preferensi pengiriman disimpan (Email: {current_slots['target_destination_address']}).\n\n"
                        f"Semua data telah lengkap dan tervalidasi. Silakan klik tombol 'Lanjutkan & Simpan Draf Permohonan' di bawah "
                        f"atau ketik 'Lanjut' untuk memproses draf surat ke sistem."
                    )
                session_data["slots"] = current_slots
                return "Pengiriman dipilih melalui Email. Mohon masukkan alamat email tujuan pengiriman:"
            elif "telegram" in msg_lower:
                current_slots["chosen_destination"] = "telegram"
                telegram_match = re.search(r'(@?\w{5,}|\d{6,})', user_message.replace("telegram", "").strip())
                if telegram_match:
                    current_slots["target_destination_address"] = telegram_match.group(0)
                    session_data["slots"] = current_slots
                    return (
                        f"Preferensi pengiriman disimpan (Telegram: {current_slots['target_destination_address']}).\n\n"
                        f"Semua data telah lengkap dan tervalidasi. Silakan klik tombol 'Lanjutkan & Simpan Draf Permohonan' di bawah "
                        f"atau ketik 'Lanjut' untuk memproses draf surat ke sistem."
                    )
                session_data["slots"] = current_slots
                return "Pengiriman dipilih melalui Telegram. Mohon masukkan nomor Chat ID atau username Telegram tujuan pengiriman:"
            else:
                # STATE 3 FORMAT: Rangkuman lengkap dan pertanyaan pengiriman
                slots_summary = [
                    {
                        "label": str(item.get("label") or item.get("field")).strip(),
                        "value": str(current_slots.get(item.get("field"), "-")).strip()
                    }
                    for item in required_fields
                ]
                return format_state3_complete_summary(slots_summary)
        
        # Jika chosen_destination sudah ada tapi target tujuannya belum terisi
        if current_slots.get("chosen_destination") and not current_slots.get("target_destination_address"):
            current_slots["target_destination_address"] = user_message.strip()
            session_data["slots"] = current_slots
            return (
                f"Preferensi pengiriman disimpan ({current_slots['chosen_destination']}: {current_slots['target_destination_address']}).\n\n"
                f"Semua data telah lengkap dan tervalidasi. Silakan klik tombol 'Lanjutkan & Simpan Draf Permohonan' di bawah "
                f"atau ketik 'Lanjut' untuk memproses draf surat ke sistem."
            )

        return (
            f"Seluruh data permohonan {surat_type.nama_surat} dan preferensi pengiriman "
            f"({current_slots.get('chosen_destination')}: {current_slots.get('target_destination_address')}) "
            f"telah lengkap dan siap dibuatkan draf surat!\n\n"
            f"Silakan klik tombol 'Lanjutkan & Simpan Draf Permohonan' di bawah atau ketik 'Lanjut' untuk memproses permohonan."
        )

    # 1. GUNAKAN AI / EXTRACTOR UNTUK MENANGKAP SLOT DARI PESAN BEBAS USER & BERKAS LAMPIRAN
    # Menggunakan SuratDraftingAgent atau fungsi helper ekstraksi slot berstandar LLM
    intent_noise_words = (
        STOP_WORDS
        | CATEGORY_WORDS
        | set(re.findall(r'\w+', surat_type.nama_surat.lower()))
        | {surat_type.kode_surat.lower(), "survei", "survey", "transkip", "transkrip", "skripsi", "riset"}
    )
    extra_tokens = [
        tk for tk in re.findall(r'\w+', user_message.lower())
        if tk not in intent_noise_words
    ]
    is_pure_intent_declaration = is_initial_turn and not attachments and len(extra_tokens) == 0

    if is_pure_intent_declaration:
        extracted_data = {}
    else:
        try:
            agent = SuratDraftingAgent()
            # Meminta AI mengekstrak data apa saja yang relevan dari pesan bebas user dan dokumen lampiran saat ini
            extraction_result = agent.extract_slots_from_text(
                user_prompt_context=user_message,
                kode_surat=surat_type.kode_surat,
                required_fields=required_fields,
                current_slots=None if is_initial_turn else current_slots,
                attachments=attachments,
            )
            extracted_data = getattr(extraction_result, "extracted_slots", {}) or {}
            # Pada giliran pertama (saat user baru menyebutkan jenis surat saja seperti "Saya mau buat surat magang"),
            # cegah fallback darurat memasukkan kalimat pembuka ke dalam slot pertama jika bukan nilai faktual
            if is_initial_turn and len(extracted_data) == 1 and not attachments:
                only_val = str(next(iter(extracted_data.values()))).strip()
                if only_val.lower() == user_message.strip().lower():
                    extracted_data = {}
        except Exception:
            extracted_data = {}
            if not is_initial_turn and not attachments:
                # Fallback darurat jika ekstraksi AI gagal pada giliran tanya-jawab slot
                for item in required_fields:
                    fk = item.get("field")
                    if fk not in current_slots or not current_slots[fk]:
                        extracted_data[fk] = user_message
                        break

    # 2. TERAPKAN VALIDASI, SANITASI & AKUMULASI KE REDIS SLOTS (Accumulative Merge)
    field_map = {
        str(item.get("field")): item
        for item in required_fields
        if isinstance(item, dict) and item.get("field")
    }
    missing_fields_before = {
        str(item.get("field"))
        for item in required_fields
        if not (item.get("field") in current_slots and bool(current_slots[item.get("field")]))
    }

    has_attachments = bool(attachments and len(attachments) > 0)
    newly_filled_missing_count = 0
    candidate_updates: Dict[str, str] = {}

    for field_key, raw_val in extracted_data.items():
        if field_key in field_map and raw_val:
            validated_val = validate_and_normalize_slot(
                field_def=field_map[field_key],
                raw_value=raw_val,
                user_message=user_message,
                has_attachments=has_attachments,
            )
            if validated_val:
                candidate_updates[field_key] = validated_val
                if field_key in missing_fields_before:
                    newly_filled_missing_count += 1

    if is_initial_turn or newly_filled_missing_count > 0:
        for fk, val in candidate_updates.items():
            if fk in missing_fields_before or not current_slots.get(fk):
                current_slots[fk] = val

    session_data["slots"] = current_slots

    # 3. Evaluasi kelengkapan parameter (State 2 vs State 3)
    missing_items = [
        item for item in required_fields
        if not (item.get("field") in current_slots and bool(current_slots[item.get("field")]))
    ]

    if missing_items:
        missing_labels = [
            str(item.get("label") or item.get("field")).strip()
            for item in missing_items
        ]
        if not is_initial_turn and newly_filled_missing_count == 0:
            if is_out_of_context_message(user_message):
                return format_in_flight_out_of_context_response(surat_type.nama_surat, missing_labels, user_message)
            return format_invalid_input_response(surat_type.nama_surat, missing_labels)

        # STATE 2: Penanganan Parameter Tidak Lengkap (Missing Entities)
        # LLM DILARANG menampilkan parameter yang sudah ada.
        # LLM hanya boleh meminta parameter yang kurang dengan format baku:
        return format_state2_missing_parameters(surat_type.nama_surat, missing_labels)

    # STATE 3: Jika seluruh parameter di skema telah terpenuhi
    slots_summary = [
        {
            "label": str(item.get("label") or item.get("field")).strip(),
            "value": str(current_slots.get(item.get("field"), "-")).strip()
        }
        for item in required_fields
    ]
    return format_state3_complete_summary(slots_summary)

def sanitize_extracted_slot(field_name: str, raw_value: Any) -> Any:
    """
    Membersihkan slot dari sisa kata depan atau kalimat percakapan 
    yang tidak sengaja ikut terekstrak.
    """
    if not isinstance(raw_value, str) or not raw_value.strip():
        return raw_value

    text = raw_value.strip()

    # Sanitasi khusus instansi tujuan (buang kata depan/pembuka)
    if field_name == "instansi_tujuan":
        patterns_to_remove = [
            r'^(untuk|ke|pada|kepada|di)\s+',
            r'^(tolong buatkan surat( rekomendasi)?( beasiswa)?( untuk)?)\s+',
            r'^(ditujukan ke|ditujukan kepada)\s+'
        ]
        for pattern in patterns_to_remove:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE).strip()

    # Sanitasi khusus keperluan / alasan
    elif field_name in ["tujuan_keperluan", "alasan_pengajuan"]:
        patterns_to_remove = [
            r'^(untuk|guna|rangka|dalam rangka)\s+',
            r'^(keperluan)\s+'
        ]
        for pattern in patterns_to_remove:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE).strip()

    return text