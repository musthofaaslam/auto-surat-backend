import json
import logging
from typing import Dict, Any, Optional
from django.core.cache import cache
from surat.models import ChatThread, ChatMessage

logger = logging.getLogger(__name__)

class AutoSuratSessionManager:
    TTL_SECONDS = 1800  # 30 Menit Sliding TTL

    @staticmethod
    def _get_redis_key(thread_id: str) -> str:
        return f"autosurat:session:{thread_id}"

    @classmethod
    def get_session(cls, thread_id: str) -> Dict[str, Any]:
        """Mengambil state aktif dari Redis, sekaligus verifikasi lazy-expiration database."""
        redis_key = cls._get_redis_key(thread_id)
        session_data = cache.get(redis_key)

        if not session_data:
            # Jika cache Redis habis/expired, sinkronisasi status thread di PostgreSQL
            thread = ChatThread.objects.filter(id=thread_id, status=ChatThread.ThreadStatus.ACTIVE).first()
            if thread:
                thread.status = ChatThread.ThreadStatus.EXPIRED
                thread.save(update_fields=['status', 'updated_at'])
            
            return {
                "state": "EXPIRED",
                "intent": None,
                "slots": {},
                "missing_slots": []
            }

        return session_data

    @classmethod
    def save_session(
        cls, 
        thread_id: str, 
        state: str, 
        intent: Optional[str] = None, 
        slots: Optional[Dict[str, Any]] = None, 
        missing_slots: Optional[list] = None
    ):
        """Menyimpan state ke Redis Hash dengan Sliding TTL 30 menit."""
        redis_key = cls._get_redis_key(thread_id)
        
        # Ambil data lama jika ada, lalu timpa dengan pembaruan
        existing = cache.get(redis_key) or {}
        
        updated_data = {
            "state": state,
            "intent": intent if intent is not None else existing.get("intent"),
            "slots": slots if slots is not None else existing.get("slots", {}),
            "missing_slots": missing_slots if missing_slots is not None else existing.get("missing_slots", [])
        }

        # Simpan ke Redis Cache dengan timeout 1800 detik (Sliding TTL)
        cache.set(redis_key, updated_data, timeout=cls.TTL_SECONDS)

    @classmethod
    def handle_incoming_message(cls, thread_id: str, user_message: str, user_obj) -> dict:
        """Handler utama untuk memproses pesan masuk dengan Guardrail 'batal'."""
        cleaned_msg = user_message.strip().lower()

        # 1. Pilar 5: Interceptor Keyword Pembatalan (Global di semua state)
        cancellation_keywords = ["batal", "reset", "cancel", "mulai ulang", "stop", "hentikan", "hapus"]
        if cleaned_msg in cancellation_keywords:
            cls.clear_session(thread_id, target_status=ChatThread.ThreadStatus.CANCELLED)
            return {
                "reply": "Sesi permohonan surat ini telah dibatalkan. Ketik jenis surat apa yang ingin kamu buat jika ingin mulai kembali.",
                "state": "CANCELLED"
            }

        # 2. Ambil sesi aktif dari Redis
        session = cls.get_session(thread_id)
        current_state = session["state"]

        if current_state == "EXPIRED":
            return {
                "reply": "Sesi Anda telah kedaluwarsa karena tidak ada aktivitas selama 30 menit. Silakan buat sesi/thread baru.",
                "state": "EXPIRED"
            }

        # 3. Log pesan masuk ke PostgreSQL (ChatMessage history)
        thread = ChatThread.objects.filter(id=thread_id, user=user_obj).first()
        if thread:
            ChatMessage.objects.create(
                thread=thread,
                sender='user',
                message=user_message,
                slots_snapshot=session.get("slots", {})
            )

        # Return state saat ini untuk diteruskan ke proses Agent / LLM Slot Filling selanjutnya
        return {
            "reply": None, # Akan diisi oleh Agent LLM
            "state": current_state,
            "intent": session["intent"],
            "slots": session["slots"],
            "missing_slots": session["missing_slots"]
        }

    @classmethod
    def clear_session(cls, thread_id: str, target_status: str = ChatThread.ThreadStatus.CANCELLED):
        """Menghapus cache Redis dan mensinkronisasi status akhir ke PostgreSQL."""
        redis_key = cls._get_redis_key(thread_id)
        cache.delete(redis_key)

        ChatThread.objects.filter(id=thread_id).update(status=target_status)