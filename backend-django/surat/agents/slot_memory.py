import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

EMPTY_OR_UNSPECIFIED_MARKERS = {
    "",
    "null",
    "none",
    "-",
    "tidak disebutkan",
    "belum disebutkan",
    "belum ada",
    "tidak ada",
    "n/a",
    "unknown",
}

FILLER_UNSPECIFIED_PATTERN = re.compile(
    r"^(?:(?:informasi|data|atribut|parameter)(?:\s+\w+)?\s+)?(?:tidak|belum)\s+(?:disebutkan|ada|diketahui)(?:\s+(?:dalam|oleh|pada)\s+(?:permohonan|prompt|pengguna|pemohon|konteks|teks))?[.]?$",
    re.IGNORECASE,
)


def is_value_filled(val: Any) -> bool:
    """
    Memeriksa apakah sebuah nilai slot/parameter valid dan terisi bermakna.
    Mengembalikan False jika bernilai None, string kosong, atau penanda tidak disebutkan dari LLM.
    Mencegah false-negative pada kalimat penjelasan mahasiswa yang memuat kata serupa.
    """
    if val is None:
        return False
    str_val = " ".join(str(val).strip().split())
    lower_val = str_val.lower()
    if not str_val or lower_val in EMPTY_OR_UNSPECIFIED_MARKERS:
        return False

    # Jika pemohon menjelaskan kalimat langsung (misal: 'Saya belum disebutkan...')
    if lower_val.startswith(("saya ", "kami ", "aku ")):
        return True

    # Cocokkan dengan pola filler standar dari LLM
    if FILLER_UNSPECIFIED_PATTERN.match(lower_val):
        return False

    # Jika teks filler singkat (<= 25 karakter) dan secara eksplisit menyatakan ketiadaan info
    if len(lower_val) <= 25 and (
        "tidak disebutkan" in lower_val
        or "belum disebutkan" in lower_val
        or lower_val.startswith("tidak ada")
        or lower_val.startswith("belum ada")
    ):
        return False

    return True


class SlotMemoryManager:
    """
    Pengelola Memori Sesi Slot-Filling untuk Agentic AI Level 2.
    Bertanggung jawab untuk:
    1. Mengakumulasi dan mempertahankan parameter yang sudah didapatkan dari turn sebelumnya.
    2. Melakukan penggabungan deterministik (Deterministic Merge) sehingga data lama tidak hilang.
    3. Mendeteksi atribut apa saja yang masih kurang sesuai kontrak `required_field_surat.json`.
    4. Menyusun ringkasan memori yang siap diinjeksikan ke System/User Prompt LLM.
    """

    def __init__(
        self,
        kode_surat: str,
        required_fields: Optional[List[Dict[str, str]]] = None,
        initial_slots: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.kode_surat: str = (kode_surat or "").strip().upper()
        self.required_fields: List[Dict[str, str]] = list(required_fields or [])
        self.accumulated_slots: Dict[str, Any] = {}
        if initial_slots and isinstance(initial_slots, dict):
            self.merge_new_slots(initial_slots)

    @classmethod
    def merge_slots(
        cls,
        previous_slots: Optional[Dict[str, Any]],
        new_slots: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Menggabungkan parameter dari memori sesi sebelumnya dengan parameter baru secara deterministik.
        
        Aturan Penggabungan:
        1. Nilai valid non-kosong dari `new_slots` akan memperbarui atau menambah nilai di `previous_slots`.
        2. Nilai lama yang valid pada `previous_slots` TIDAK AKAN terhapus/ditimpa jika pada `new_slots`
           bernilai None, string kosong, atau 'tidak disebutkan'.
        3. Jika pemohon tidak menyebutkan nilai lama pada turn baru, nilai lama tetap UTUH di memori.
        """
        merged: Dict[str, Any] = {}

        # 1. Salin seluruh nilai yang valid dari previous_slots
        if previous_slots and isinstance(previous_slots, dict):
            for k, v in previous_slots.items():
                if is_value_filled(v):
                    merged[k] = v

        # 2. Timpa atau tambahkan dari new_slots hanya jika nilai barunya valid
        if new_slots and isinstance(new_slots, dict):
            for k, v in new_slots.items():
                if is_value_filled(v):
                    merged[k] = v
                elif k not in merged:
                    # Pertahankan key dengan None jika memang belum pernah terisi sama sekali
                    merged[k] = None

        return merged

    def merge_new_slots(self, new_slots: Dict[str, Any]) -> Dict[str, Any]:
        """
        Memperbarui memori internal instance dengan slot baru secara deterministik.
        """
        self.accumulated_slots = self.merge_slots(self.accumulated_slots, new_slots)
        return self.accumulated_slots

    def get_missing_fields(
        self,
        current_slots: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, str]]:
        """
        Memeriksa atribut mana saja dari `required_fields` yang masih belum terisi atau masih None.
        """
        slots_to_check = (
            current_slots if current_slots is not None else self.accumulated_slots
        )
        missing: List[Dict[str, str]] = []

        for item in self.required_fields:
            field_name = item.get("field", "").strip()
            if not field_name:
                continue
            val = slots_to_check.get(field_name)
            if not is_value_filled(val):
                missing.append(item)

        return missing

    def is_complete(self, current_slots: Optional[Dict[str, Any]] = None) -> bool:
        """
        Mengembalikan True jika seluruh field wajib dari required_fields sudah terisi valid.
        """
        return len(self.get_missing_fields(current_slots)) == 0

    def format_slots_summary(
        self,
        current_slots: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Menyusun ringkasan status memori slot dalam bentuk teks terstruktur
        untuk diinjeksikan langsung ke prompt Gemini LLM.
        """
        slots_to_format = (
            current_slots if current_slots is not None else self.accumulated_slots
        )
        if not slots_to_format and not self.required_fields:
            return "(Belum ada parameter yang tersimpan)"

        lines: List[str] = []
        processed_fields = set()

        # Format berdasarkan daftar spesifikasi resmi required_fields
        for item in self.required_fields:
            field_name = item.get("field", "").strip()
            label = item.get("label", field_name).strip()
            field_type = item.get("type", "string").strip()
            processed_fields.add(field_name)

            val = slots_to_format.get(field_name)
            if is_value_filled(val):
                lines.append(
                    f"- {field_name} (Label: {label} | Tipe: {field_type}): \"{val}\" [TERSIMPAN DI MEMORI]"
                )
            else:
                lines.append(
                    f"- {field_name} (Label: {label} | Tipe: {field_type}): [BELUM TERISI / MEMBUTUHKAN JAWABAN PEMOHON]"
                )

        # Format parameter tambahan di luar required_fields jika ada
        if isinstance(slots_to_format, dict):
            for k, v in slots_to_format.items():
                if k not in processed_fields and is_value_filled(v):
                    lines.append(f"- {k}: \"{v}\" [TERSIMPAN DI MEMORI]")

        return "\n".join(lines) if lines else "(Belum ada parameter yang tersimpan)"

    def generate_clarification_notes(
        self,
        current_slots: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """
        Menghasilkan daftar catatan kekurangan atribut yang spesifik dan objektif
        untuk ditinjau pemohon atau disematkan ke `revision_notes`.
        """
        missing = self.get_missing_fields(current_slots)
        if not missing:
            return []

        notes = []
        for item in missing:
            field_name = item.get("field", "")
            label = item.get("label", field_name)
            desc = item.get("description", "")
            note_str = f"Atribut '{label}' ({field_name}) belum disebutkan."
            if desc:
                note_str += f" Keterangan: {desc}."
            notes.append(note_str)
        return notes

