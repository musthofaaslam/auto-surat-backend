import json
import logging
from datetime import timedelta
from typing import Dict, Any, Optional

from django.core.cache import cache
from django.utils import timezone
from surat.models import ChatThread, ChatMessage
from .chat_workflow import handle_incoming_chat_with_redis

logger = logging.getLogger(__name__)

class AutoSuratSessionManager:
    TTL_SECONDS = 1800  # 30 Menit Sliding TTL

    @staticmethod
    def _get_redis_key(thread_id: str) -> str:
        return f"autosurat:session:{thread_id}"

    @classmethod
    def get_session(cls, thread_id: str) -> Dict[str, Any]:
        """
        Mengambil state aktif dari Redis, sekaligus verifikasi lazy-expiration database.
        Dilengkapi mekanisme graceful fallback ke database PostgreSQL jika Redis offline.
        """
        redis_key = cls._get_redis_key(thread_id)
        session_data = None
        redis_failed = False

        try:
            session_data = cache.get(redis_key)
        except Exception as cache_exc:
            logger.warning("Gagal mengakses Redis Cache: %s. Mengaktifkan fallback berbasis database.", cache_exc)
            redis_failed = True

        if session_data and isinstance(session_data, dict):
            return session_data

        # Fallback berbasis database PostgreSQL (ChatThread & ChatMessage)
        thread = ChatThread.objects.filter(id=thread_id).first()
        last_msg = (
            ChatMessage.objects.filter(thread=thread).order_by('-created_at').first()
            if thread else None
        )

        # Cek sliding TTL 30 menit berbasis timestamp database
        reference_time = (
            last_msg.created_at
            if last_msg
            else (thread.updated_at if thread else None)
        )
        is_expired = False
        if reference_time and (timezone.now() - reference_time > timedelta(seconds=cls.TTL_SECONDS)):
            is_expired = True

        if is_expired and thread and thread.status == ChatThread.ThreadStatus.ACTIVE:
            try:
                thread.status = ChatThread.ThreadStatus.EXPIRED
                thread.save(update_fields=['status', 'updated_at'])
            except Exception as db_exc:
                logger.error("Gagal memperbarui status expired pada database: %s", db_exc)

        # Ambil snapshot slot terakhir dari ChatMessage
        reconstructed_slots = getattr(last_msg, "slots_snapshot", {}) or {}

        # Tentukan status state
        if not thread:
            state = "ACTIVE"
            intent = None
        elif is_expired or thread.status == ChatThread.ThreadStatus.EXPIRED:
            state = "EXPIRED"
            intent = thread.document_type
        elif thread.status == ChatThread.ThreadStatus.CANCELLED:
            state = "CANCELLED"
            intent = thread.document_type
        elif thread.status == ChatThread.ThreadStatus.COMPLETED:
            state = "COMPLETED"
            intent = thread.document_type
        else:
            state = "ACTIVE"
            intent = thread.document_type

        fallback_session = {
            "state": state,
            "intent": intent,
            "pending_intent": None,
            "is_waiting_for_switch_confirmation": False,
            "slots": reconstructed_slots,
        }

        # Jika Redis dapat diakses kembali dan sesi masih aktif, sinkronkan balik ke Redis
        if not redis_failed and state == "ACTIVE":
            try:
                cache.set(redis_key, fallback_session, timeout=cls.TTL_SECONDS)
            except Exception as cache_exc:
                logger.warning("Gagal mengakses Redis Cache: %s. Mengaktifkan fallback berbasis database.", cache_exc)

        return fallback_session
    
    @classmethod
    def save_session(
        cls, 
        thread_id: str, 
        state: str, 
        intent: Optional[str] = None, 
        slots: Optional[Dict[str, Any]] = None, 
        missing_slots: Optional[list] = None,
        pending_intent: Optional[str] = None,
        is_waiting_for_switch_confirmation: Optional[bool] = None
    ):
        """
        Menyimpan atau memperbarui state ke Redis Cache dengan Sliding TTL 30 menit.
        Jika Redis offline, state dan slots dipersistensikan langsung ke PostgreSQL (ChatThread & ChatMessage).
        """
        redis_key = cls._get_redis_key(thread_id)
        existing = {}

        try:
            existing = cache.get(redis_key) or {}
        except Exception as cache_exc:
            logger.warning("Gagal mengakses Redis Cache: %s. Mengaktifkan fallback berbasis database.", cache_exc)
            existing = cls.get_session(thread_id)

        if not existing:
            existing = cls.get_session(thread_id)

        updated_data = {
            "state": state,
            "intent": intent if intent is not None else existing.get("intent"),
            "pending_intent": pending_intent if pending_intent is not None else existing.get("pending_intent"),
            "is_waiting_for_switch_confirmation": is_waiting_for_switch_confirmation if is_waiting_for_switch_confirmation is not None else existing.get("is_waiting_for_switch_confirmation", False),
            "slots": slots if slots is not None else existing.get("slots", {}),
            "missing_slots": missing_slots if missing_slots is not None else existing.get("missing_slots", [])
        }

        try:
            cache.set(redis_key, updated_data, timeout=cls.TTL_SECONDS)
        except Exception as cache_exc:
            logger.warning("Gagal mengakses Redis Cache: %s. Mengaktifkan fallback berbasis database.", cache_exc)

        # Persistensi Fallback ke Database PostgreSQL agar state dan slots tidak hilang
        try:
            thread = ChatThread.objects.filter(id=thread_id).first()
            if thread:
                fields_to_update = ['updated_at']
                target_intent = updated_data.get("intent")
                if target_intent and thread.document_type != target_intent:
                    thread.document_type = target_intent
                    fields_to_update.append('document_type')

                target_status = state.lower()
                if target_status in [ChatThread.ThreadStatus.ACTIVE, ChatThread.ThreadStatus.CANCELLED, ChatThread.ThreadStatus.EXPIRED, ChatThread.ThreadStatus.COMPLETED]:
                    if thread.status != target_status:
                        thread.status = target_status
                        fields_to_update.append('status')
                elif state in ("COLLECTING_SLOTS", "READY_TO_DRAFT") and thread.status != ChatThread.ThreadStatus.ACTIVE:
                    thread.status = ChatThread.ThreadStatus.ACTIVE
                    fields_to_update.append('status')

                thread.save(update_fields=fields_to_update)

                # Simpan update snapshot slot ke ChatMessage terakhir jika ada
                if updated_data.get("slots"):
                    last_msg = ChatMessage.objects.filter(thread=thread).order_by('-created_at').first()
                    if last_msg:
                        last_msg.slots_snapshot = updated_data["slots"]
                        last_msg.save(update_fields=['slots_snapshot'])
        except Exception as db_exc:
            logger.error("Gagal melakukan persistensi fallback ke database: %s", db_exc)

    @classmethod
    def clear_session(cls, thread_id: str, target_status: str = ChatThread.ThreadStatus.CANCELLED):
        """Menghapus cache Redis dan mensinkronisasi status akhir ke PostgreSQL."""
        redis_key = cls._get_redis_key(thread_id)
        try:
            cache.delete(redis_key)
        except Exception as cache_exc:
            logger.warning("Gagal mengakses Redis Cache: %s. Mengaktifkan fallback berbasis database.", cache_exc)

        try:
            ChatThread.objects.filter(id=thread_id).update(status=target_status)
        except Exception as db_exc:
            logger.error("Gagal memperbarui status ChatThread di database: %s", db_exc)

    @classmethod
    def handle_incoming_message(
        cls, 
        thread_id: str, 
        user_message: str, 
        user_obj,
        attachments: Optional[List[Any]] = None,
    ) -> str:
        """
        Handler utama di dalam kelas session manager:
        1. Mengecek keyword pembatalan global (Pilar 5).
        2. Mengambil state aktif dari Redis / DB Fallback (session_data).
        3. Mencatat riwayat pesan ke PostgreSQL (ChatMessage).
        4. Meneruskan ke orkestrator state & slot filling (termasuk berkas lampiran).
        5. Menyimpan sliding TTL ke cache dan database secara aman.
        """
        cleaned_msg = user_message.strip()
        cleaned_msg_lower = cleaned_msg.lower()

        # 1. Interceptor Keyword Pembatalan (Global di semua state)
        cancellation_keywords = ["batal", "reset", "cancel", "mulai ulang", "stop", "hentikan", "hapus"]
        if cleaned_msg_lower in cancellation_keywords:
            cls.clear_session(thread_id, target_status=ChatThread.ThreadStatus.CANCELLED)
            try:
                ChatThread.objects.filter(id=thread_id).update(
                    document_type=None, 
                    title="Permohonan Surat Dibatalkan"
                )
            except Exception as db_exc:
                logger.error("Gagal memperbarui ChatThread saat pembatalan: %s", db_exc)
            return "Sesi permohonan surat ini telah dibatalkan. Ketik jenis surat apa yang ingin kamu buat jika ingin mulai kembali."

        # 2. Ambil sesi aktif dari Redis atau Fallback Database
        session_data = cls.get_session(thread_id)
        if session_data.get("state") == "EXPIRED":
            return "Sesi Anda telah kedaluwarsa karena tidak ada aktivitas selama 30 menit. Silakan buat sesi/thread baru."

        # 3. Log pesan masuk ke PostgreSQL (ChatMessage history)
        thread = ChatThread.objects.filter(id=thread_id, user=user_obj).first()
        if thread:
            try:
                ChatMessage.objects.create(
                    thread=thread,
                    sender='user',
                    message=user_message,
                    slots_snapshot=session_data.get("slots", {})
                )
            except Exception as db_exc:
                logger.error("Gagal mencatat pesan pengguna ke ChatMessage: %s", db_exc)

        # 4. Teruskan ke orkestrator logika alur chat (di file chat_workflow_service.py)
        reply_message = handle_incoming_chat_with_redis(
            thread_id, 
            cleaned_msg, 
            session_data, 
            attachments=attachments
        )

        # 5. Catat juga balasan asisten ke PostgreSQL (ChatMessage history) agar riwayat obrolan utuh
        if thread and reply_message:
            try:
                ChatMessage.objects.create(
                    thread=thread,
                    sender='assistant',
                    message=reply_message,
                    slots_snapshot=session_data.get("slots", {})
                )
            except Exception as db_exc:
                logger.error("Gagal mencatat balasan asisten ke ChatMessage: %s", db_exc)

        # 6. Simpan kembali pembaruan state session_data ke Redis Cache (Sliding TTL) & Fallback DB
        try:
            cache.set(cls._get_redis_key(thread_id), session_data, timeout=cls.TTL_SECONDS)
        except Exception as cache_exc:
            logger.warning("Gagal mengakses Redis Cache: %s. Mengaktifkan fallback berbasis database.", cache_exc)

        return reply_message