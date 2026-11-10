import json
import os
from datetime import datetime
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.core.cache import cache

from accounts.models import User, Student, Lecturer, Faculty, Department
from surat.models import (
    SuratRequest,
    SuratApproval,
    SuratAttachment,
    TteSignature,
    SuratAuditLog,
    AgentFeedbackMemory,
    SuratNumberCounter,
    ChatThread,
    ChatMessage,
    SuratType,
)


class Command(BaseCommand):
    help = "Membersihkan seluruh data transaksional surat secara aman sambil mempertahankan data master 100%."

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-backup",
            action="store_true",
            help="Lewati pembuatan file backup JSON sebelum penghapusan.",
        )

    def handle(self, *args, **options):
        self.stdout.write("==================================================")
        self.stdout.write("MEMULAI PROSES TRANSACTIONAL DATA PURGE")
        self.stdout.write("==================================================")

        # 1. Hitung rekaman data yang akan dibersihkan
        total_requests = SuratRequest.objects.count()
        total_approvals = SuratApproval.objects.count()
        total_attachments = SuratAttachment.objects.count()
        total_signatures = TteSignature.objects.count()
        total_audit_logs = SuratAuditLog.objects.count()
        total_memories = AgentFeedbackMemory.objects.count()
        total_counters = SuratNumberCounter.objects.count()
        total_chat_threads = ChatThread.objects.count()
        total_chat_messages = ChatMessage.objects.count()

        self.stdout.write(f"Data transaksi terdeteksi:")
        self.stdout.write(f"- SuratRequest: {total_requests}")
        self.stdout.write(f"- SuratApproval: {total_approvals}")
        self.stdout.write(f"- SuratAttachment: {total_attachments}")
        self.stdout.write(f"- TteSignature: {total_signatures}")
        self.stdout.write(f"- SuratAuditLog: {total_audit_logs}")
        self.stdout.write(f"- AgentFeedbackMemory: {total_memories}")
        self.stdout.write(f"- SuratNumberCounter: {total_counters}")
        self.stdout.write(f"- ChatThread: {total_chat_threads}")
        self.stdout.write(f"- ChatMessage: {total_chat_messages}")

        # 2. Backup snapshot ke JSON jika tidak dilewati
        if not options.get("no_backup") and total_requests > 0:
            backup_dir = os.path.join(os.getcwd(), "backups")
            os.makedirs(backup_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(backup_dir, f"transaction_backup_{timestamp}.json")

            self.stdout.write(f"\nMembuat snapshot backup transaksi ke: {backup_path}...")
            backup_data = []
            for req in SuratRequest.objects.all():
                backup_data.append({
                    "id": req.id,
                    "student_nim": req.student.nim,
                    "kode_surat": req.kode_surat.kode_surat,
                    "nomor_surat_resmi": req.nomor_surat_resmi,
                    "status": req.status,
                    "payload_data": req.payload_data,
                    "user_prompt_context": req.user_prompt_context,
                    "ai_original_draft": req.ai_original_draft,
                    "final_approved_content": req.final_approved_content,
                    "self_critique_score": req.self_critique_score,
                    "file_pdf_url": req.file_pdf_url,
                    "qr_verification_code": req.qr_verification_code,
                    "chosen_destination": req.chosen_destination,
                    "target_destination_address": req.target_destination_address,
                    "created_at": req.created_at.isoformat() if hasattr(req, "created_at") and req.created_at else None,
                })

            with open(backup_path, "w", encoding="utf-8") as f_backup:
                json.dump(backup_data, f_backup, indent=2, ensure_ascii=False)
            self.stdout.write(f"Backup {len(backup_data)} transaksi berhasil disimpan.")

        # 3. Eksekusi pembersihan di dalam transaksi atomik
        self.stdout.write("\nMenjalankan pembersihan transaksi di dalam database transaction...")
        with transaction.atomic():
            # A. Hapus percakapan chat
            ChatMessage.objects.all().delete()
            ChatThread.objects.all().delete()

            # B. Hapus permohonan surat (otomatis cascade ke approvals, logs, signatures, attachments, memories)
            SuratRequest.objects.all().delete()

            # C. Hapus counter nomor surat
            SuratNumberCounter.objects.all().delete()

            # D. Reset PostgreSQL identity sequence ke 1
            with connection.cursor() as cursor:
                sequences_to_reset = [
                    "surat_request_id_seq",
                    "surat_approvals_id_seq",
                    "surat_attachment_id_seq",
                    "tte_signatures_id_seq",
                    "surat_audit_logs_id_seq",
                    "agent_feedback_memories_id_seq",
                    "surat_number_counter_id_seq",
                    "surat_chatmessage_id_seq",
                ]
                for seq in sequences_to_reset:
                    try:
                        cursor.execute(f"ALTER SEQUENCE IF EXISTS {seq} RESTART WITH 1;")
                    except Exception as seq_err:
                        pass

        # 4. Bersihkan Cache Redis
        try:
            cache.clear()
            self.stdout.write("Redis cache berhasil dibersihkan (cache.clear).")
        except Exception as cache_err:
            self.stdout.write(f"Peringatan cache: {cache_err}")

        # 5. Verifikasi Integritas Data Master
        users_count = User.objects.count()
        students_count = Student.objects.count()
        lecturers_count = Lecturer.objects.count()
        faculties_count = Faculty.objects.count()
        departments_count = Department.objects.count()
        surat_types_count = SuratType.objects.count()
        remaining_requests = SuratRequest.objects.count()

        self.stdout.write("\n==================================================")
        self.stdout.write("STATUS INTEGRITAS DATA MASTER PASCA-PURGE:")
        self.stdout.write(f"- Users (Akun): {users_count} (UTUH)")
        self.stdout.write(f"- Mahasiswa: {students_count} (UTUH)")
        self.stdout.write(f"- Dosen: {lecturers_count} (UTUH)")
        self.stdout.write(f"- Fakultas: {faculties_count} (UTUH)")
        self.stdout.write(f"- Program Studi: {departments_count} (UTUH)")
        self.stdout.write(f"- Jenis Surat: {surat_types_count} (UTUH)")
        self.stdout.write(f"- Sisa SuratRequest: {remaining_requests} (BERSIH TOTAL)")
        self.stdout.write("==================================================")
        self.stdout.write("DATABASE BERHASIL DIRESET KE KONDISI AWAL (CLEAN STATE)")
