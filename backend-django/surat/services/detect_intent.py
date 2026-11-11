import re
from typing import Optional
from surat.models import SuratType

STOP_WORDS = {
    "surat", "dan", "yang", "untuk", "saya", "buatkan", "bikin", 
    "mohon", "minta", "tolong", "pengajuan", "permohonan", "keperluan",
    "mau", "ingin", "butuh", "adalah", "di", "ke", "dari", "ini", "itu"
}

CATEGORY_WORDS = {
    "izin", "ijin", "keterangan", "pengantar", "rekomendasi"
}

# Kamus frasa spesifik berkekuatan tinggi 
EXPLICIT_PHRASE_MAPPINGS = [
    # Survey / Observasi
    (r'\b(survey|survei|observasi)\b', 'SI-SUR'),
    # SKCK
    (r'\b(skck)\b', 'SP-SKC'),
    # Transkrip
    (r'\b(transkrip|transkip)\b', 'SP-TRA'),
    # Riset / Tugas Akhir / Skripsi
    (r'\b(tugas\s+akhir|riset|skripsi|penelitian\s+akhir)\b', 'SP-TAS'),
    # Aktif Kuliah
    (r'\b(aktif\s+kuliah|kuliah\s+aktif|keterangan\s+aktif)\b', 'SK-KUL'),
    # Tidak Menerima Beasiswa
    (r'\b(tidak\s+menerima\s+beasiswa|beasiswa\s+tidak\s+menerima|bebas\s+beasiswa)\b', 'SK-BEA'),
    # Beasiswa umum / Rekomendasi Beasiswa
    (r'\b(rekomendasi\s+beasiswa|beasiswa\s+rekomendasi)\b', 'SR-BEA'),
    # Magang spesifik berdasarkan kategori
    (r'\b(izin\s+magang|ijin\s+magang|magang\s+izin|magang\s+ijin)\b', 'SI-MAG'),
    (r'\b(rekomendasi\s+magang|magang\s+rekomendasi)\b', 'SR-MAG'),
    (r'\b(pengantar\s+magang|magang\s+pengantar)\b', 'SP-MAG'),
]


def detect_intent_dynamically(user_message: str) -> Optional[str]:
    """
    Melakukan pre-filtering / lapis pertama secara deterministik berbasis:
    1. Pencocokan kode surat eksplisit (misal: "SI-SUR", "SR-MAG")
    2. Pencocokan frasa spesifik (frasa komposit dengan presisi tinggi)
    3. Weighted Token Overlap Scoring terhadap katalog master SuratType
    """
    if not user_message:
        return None

    message_lower = user_message.lower().strip()

    # Ambil jenis surat dari database
    surat_types = list(SuratType.objects.all())

    # 1. Cek langsung berdasarkan kode surat jika user mengetiknya secara spesifik (misal: "SI-SUR")
    for surat in surat_types:
        if re.search(r'\b' + re.escape(surat.kode_surat.lower()) + r'\b', message_lower):
            return surat.kode_surat

    # 2. Cek kamus frasa spesifik berkekuatan tinggi
    for pattern, kode in EXPLICIT_PHRASE_MAPPINGS:
        if re.search(pattern, message_lower):
            if any(s.kode_surat == kode for s in surat_types):
                return kode

    # 3. Weighted Token Overlap Scoring
    user_tokens = set(re.findall(r'\b\w+\b', message_lower))

    best_surat = None
    best_score = 0
    second_best_score = 0

    for surat in surat_types:
        nama_tokens = [
            tk for tk in re.findall(r'\w+', surat.nama_surat.lower()) 
            if tk not in STOP_WORDS and len(tk) > 1
        ]
        
        score = 0
        specific_matched = 0

        for tk in nama_tokens:
            if tk in user_tokens:
                if tk in CATEGORY_WORDS:
                    score += 1
                else:
                    score += 3
                    specific_matched += 1

        # Syarat minimal kelulusan Lapis 1:
        # Minimal harus ada 1 token spesifik yang cocok (bukan sekadar kata generik seperti 'surat' atau 'izin')
        if specific_matched >= 1:
            if score > best_score:
                second_best_score = best_score
                best_score = score
                best_surat = surat.kode_surat
            elif score == best_score:
                second_best_score = score

    # Jika skor tertinggi tunggal dan unggul dari skor kedua, kembalikan pemenang
    if best_score > 0 and best_score > second_best_score:
        return best_surat

    # Jika tidak ada kecocokan yang meyakinkan, serahkan ke Lapis 2 AI Router
    return None
