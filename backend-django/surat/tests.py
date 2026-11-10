from django.test import TestCase
from unittest.mock import patch, MagicMock
from rest_framework.test import APIRequestFactory, force_authenticate
from accounts.models import User, Faculty, Department, Lecturer, Student
from surat.models import SuratType, SuratRequest, SuratApproval, SuratAuditLog, SuratStatus, ChatThread, ChatMessage
from surat.serializers import SuratRequestDetailSerializer
from surat.agents.execution_tools import SuratExecutionTools, ExecutionPipelineResult
from surat.services.workflow_service import _execute_final_issuance_worker
from surat.views import ChatSessionMessageAPIView
from surat.services.session_manager import AutoSuratSessionManager


class SuratArchitecturalFixesTestCase(TestCase):
    """
    Test suite komprehensif untuk memvalidasi implementasi perbaikan temuan 4, 5, dan 6:
    - Temuan 4: Field chosen_destination & target_destination_address pada SuratRequestDetailSerializer
    - Temuan 5: Delegasi eksekusi pasca-approval ke SuratExecutionTools (eliminasi duplikasi logika)
    - Temuan 6: Resolusi template_path dinamis tanpa penimpaan hardcoded
    """

    def setUp(self):
        # 1. Setup User & Organisasi
        self.user_lec = User.objects.create(
            id="u-lec-test",
            nama="Dr. Budi Santoso, M.Kom.",
            nip_nim="198001012005011001",
            role="LECTURER",
            password="password123",
        )
        self.user_mhs = User.objects.create(
            id="u-mhs-test",
            nama="Ahmad Bintang",
            nip_nim="210001001",
            role="STUDENT",
            password="password123",
        )

        self.fakultas = Faculty.objects.create(
            id="FT-TEST",
            nama_fakultas="Fakultas Teknik",
        )
        self.prodi = Department.objects.create(
            id="INF-TEST",
            fakultas=self.fakultas,
            nama_prodi="Informatika",
        )

        self.lecturer = Lecturer.objects.create(
            id="l-test-01",
            user=self.user_lec,
            fakultas=self.fakultas,
            prodi=self.prodi,
            jabatan_struktural=["Dekan Fakultas Teknik"],
        )
        self.fakultas.dekan = self.lecturer
        self.fakultas.save()

        self.student = Student.objects.create(
            nim="210001001",
            user=self.user_mhs,
            fakultas=self.fakultas,
            prodi=self.prodi,
            semester_aktif=7,
            tahun_akademik="2026/2027",
            tahun_masuk=2021,
        )

        # 2. Setup SuratType
        self.surat_type_custom = SuratType.objects.create(
            kode_surat="SR-MAG",
            nama_surat="Surat Rekomendasi Magang",
            kategori="Rekomendasi",
            is_auto_approval=False,
            template_path="surat/sr.mag.html",
        )

        self.surat_type_empty = SuratType.objects.create(
            kode_surat="SK-KUL",
            nama_surat="Surat Keterangan Aktif Kuliah",
            kategori="Keterangan",
            is_auto_approval=True,
            template_path="",
        )

        # 3. Setup SuratRequest
        self.surat_req = SuratRequest.objects.create(
            student=self.student,
            kode_surat=self.surat_type_custom,
            status=SuratStatus.PENDING_APPROVAL,
            chosen_destination="email",
            target_destination_address="bintang@student.ac.id",
            payload_data={
                "instansi_tujuan": "PT Telkom Indonesia",
                "posisi_dilamar": "Backend Engineer",
            },
            ai_original_draft="Draf awal permohonan magang mahasiswa.",
            final_approved_content="Naskah surat rekomendasi magang yang disetujui dosen.",
        )

    # =========================================================================
    # TEMUAN 4: Field Pengiriman pada SuratRequestDetailSerializer
    # =========================================================================
    def test_temuan4_serializer_exposes_chosen_destination_and_address(self):
        """
        Validasi Temuan 4:
        SuratRequestDetailSerializer wajib menyertakan 'chosen_destination'
        dan 'target_destination_address' pada output JSON ke frontend.
        """
        serializer = SuratRequestDetailSerializer(self.surat_req)
        data = serializer.data

        self.assertIn("chosen_destination", data)
        self.assertIn("target_destination_address", data)
        self.assertEqual(data["chosen_destination"], "email")
        self.assertEqual(data["target_destination_address"], "bintang@student.ac.id")

    # =========================================================================
    # TEMUAN 6: Resolusi Template Path Dinamis Tanpa Hardcoding
    # =========================================================================
    def test_temuan6_resolve_template_path_existing_template(self):
        """
        Validasi Temuan 6:
        Template khusus yang ada di disk ('surat/sr.mag.html') dipertahankan.
        """
        tools = SuratExecutionTools()
        resolved = tools.resolve_template_path(self.surat_req)
        self.assertEqual(resolved, "surat/sr.mag.html")

    def test_temuan6_resolve_template_path_with_templates_prefix(self):
        """
        Validasi Temuan 6:
        Prefiks 'templates/' yang tercatat di database otomatis dibersihkan.
        """
        self.surat_type_custom.template_path = "templates/surat/sr.mag.html"
        self.surat_type_custom.save()
        self.surat_req.refresh_from_db()

        tools = SuratExecutionTools()
        resolved = tools.resolve_template_path(self.surat_req)
        self.assertEqual(resolved, "surat/sr.mag.html")

    def test_temuan6_resolve_template_path_fallback_when_empty_or_missing(self):
        """
        Validasi Temuan 6:
        Jika template_path kosong atau merujuk berkas yang tidak ada,
        otomatis dialihkan ke 'kerangka-surat/base_surat.html'.
        """
        tools = SuratExecutionTools()

        # Kasus 1: template_path kosong
        self.surat_req.kode_surat = self.surat_type_empty
        resolved_empty = tools.resolve_template_path(self.surat_req)
        self.assertEqual(resolved_empty, "kerangka-surat/base_surat.html")

        # Kasus 2: template_path tidak ada di disk
        self.surat_type_empty.template_path = "surat/file_tidak_ada.html"
        self.surat_req.kode_surat = self.surat_type_empty
        resolved_missing = tools.resolve_template_path(self.surat_req)
        self.assertEqual(resolved_missing, "kerangka-surat/base_surat.html")

    # =========================================================================
    # TEMUAN 5 & 6: Delegasi Eksekusi Pasca-Approval pada Workflow Service
    # =========================================================================
    @patch("surat.services.workflow_service.close_old_connections")
    @patch("surat.services.workflow_service._execute_distribution_worker")
    @patch.object(SuratExecutionTools, "execute_approval_pipeline")
    def test_temuan5_workflow_worker_delegates_to_execution_tools(
        self,
        mock_pipeline,
        mock_distribution,
        mock_close_conns,
    ):
        """
        Validasi Temuan 5 & 6:
        _execute_final_issuance_worker mendelegasikan eksekusi penerbitan
        dokumen ke SuratExecutionTools.execute_approval_pipeline tanpa menduplikasi
        logika WeasyPrint/Cloudinary dan TANPA menimpa kode_surat.template_path.
        """
        mock_pipeline.return_value = ExecutionPipelineResult(
            surat_request_id=self.surat_req.id,
            nomor_surat_resmi="001/UN.1/FT/2026",
            file_pdf_url="https://res.cloudinary.com/demo/image/upload/v1/surat.pdf",
            qr_code_url="https://auto-surat-backend.onrender.com/surat/verify/token-123/",
            tte_token="token-123",
            hash_document="hash-sha256-abc",
            final_status="SENT",
            final_approved_content=self.surat_req.final_approved_content,
        )

        original_template_path = self.surat_req.kode_surat.template_path

        _execute_final_issuance_worker(
            surat_request_id=self.surat_req.id,
            signer_lecturer_id=self.lecturer.id,
            final_status="SENT",
        )

        # 1. Pastikan execute_approval_pipeline dipanggil sekali dengan parameter yang tepat
        mock_pipeline.assert_called_once()
        call_kwargs = mock_pipeline.call_args.kwargs
        self.assertEqual(call_kwargs["surat_request"].id, self.surat_req.id)
        self.assertEqual(call_kwargs["signer"].id, self.lecturer.id)
        self.assertEqual(call_kwargs["final_status"], "SENT")
        self.assertEqual(
            call_kwargs["final_approved_content"],
            self.surat_req.final_approved_content,
        )

        # 2. Pastikan template_path pada model kode_surat TIDAK DITIMPA menjadi 'base_surat.html'
        self.surat_req.kode_surat.refresh_from_db()
        self.assertEqual(self.surat_req.kode_surat.template_path, original_template_path)

        # 3. Pastikan _execute_distribution_worker dipanggil
        mock_distribution.assert_called_once_with(self.surat_req.id)

    # =========================================================================
    # INTEGRASI: Eksekusi Pipeline Nyata & Context Rendering
    # =========================================================================
    @patch("surat.agents.execution_tools._resolve_pdf_fn")
    @patch("surat.agents.execution_tools._resolve_tte_fn")
    @patch("surat.agents.execution_tools._resolve_number_fn")
    def test_pipeline_execution_real_integration(
        self,
        mock_number_fn,
        mock_tte_fn,
        mock_pdf_fn,
    ):
        """
        Validasi alur integrasi end-to-end execute_approval_pipeline:
        - Pembuatan nomor surat resmi
        - Pembuatan TTE & QR Code
        - Render context (approvals, QR base64, signer)
        - Pembaruan status SuratRequest menjadi SENT
        - Pencatatan SuratAuditLog FIN_01
        """
        mock_number_fn.return_value = lambda *args, **kwargs: "B/100/FT/2026"
        mock_tte_fn.return_value = lambda *args, **kwargs: {
            "token": "token-test-xyz",
            "hash_document": "hash-sha256-xyz",
            "qr_code_url": "https://auto-surat.test/verify/xyz/",
        }
        mock_pdf_fn.return_value = lambda tmpl, ctx: "https://cloudinary.test/surat_resmi.pdf"

        # Buat riwayat SuratApproval
        SuratApproval.objects.create(
            surat_request=self.surat_req,
            approver=self.lecturer,
            step_order=1,
            status="APPROVED",
            catatan="Disetujui Dekan",
        )

        tools = SuratExecutionTools()
        result = tools.execute_approval_pipeline(
            surat_request=self.surat_req,
            signer=self.lecturer,
            final_approved_content="Naskah Surat Resmi Terverifikasi",
            final_status="SENT",
        )

        self.assertEqual(result.nomor_surat_resmi, "B/100/FT/2026")
        self.assertEqual(result.file_pdf_url, "https://cloudinary.test/surat_resmi.pdf")
        self.assertEqual(result.final_status, "SENT")

        # Verifikasi data tersimpan di database
        self.surat_req.refresh_from_db()
        self.assertEqual(self.surat_req.nomor_surat_resmi, "B/100/FT/2026")
        self.assertEqual(self.surat_req.file_pdf_url, "https://cloudinary.test/surat_resmi.pdf")
        self.assertEqual(self.surat_req.status, "SENT")
        self.assertEqual(self.surat_req.final_approved_content, "Naskah Surat Resmi Terverifikasi")

        # Verifikasi SuratAuditLog FIN_01 tercatat
        audit_log = SuratAuditLog.objects.filter(
            surat_request=self.surat_req,
            action_id="FIN_01",
        ).first()
        self.assertIsNotNone(audit_log)
        self.assertIn("SENT", audit_log.action)

    def test_pdf_context_has_base64_qr_and_approvals(self):
        """
        Validasi pembentukan context data untuk template HTML:
        - qr_code_url memuat data-uri base64 PNG yang valid
        - qr_verification_code memuat tautan publik verifikasi
        - approvals memuat daftar terstruktur
        - tanggal_terbit dan tanggal_surat tersedia
        """
        tools = SuratExecutionTools()
        context = tools.build_pdf_template_context(
            surat_request=self.surat_req,
            nomor_surat="B/101/FT/2026",
            qr_code_url="https://auto-surat.test/verify/token-abc/",
            final_approved_content="Isi naskah resmi",
            signer=self.lecturer,
        )

        self.assertIn("qr_code_url", context)
        self.assertTrue(context["qr_code_url"].startswith("data:image/png;base64,"))
        self.assertEqual(context["qr_verification_code"], "https://auto-surat.test/verify/token-abc/")
        self.assertIn("approvals", context)
        self.assertIsInstance(context["approvals"], list)
        self.assertGreaterEqual(len(context["approvals"]), 1)
        self.assertIn("tanggal_terbit", context)
        self.assertIn("tanggal_surat", context)
        self.assertEqual(context["nomor_surat"], "B/101/FT/2026")


class ChatSessionContractAndPersistenceTestCase(TestCase):
    """
    Test suite untuk memvalidasi kontrak API dan persistensi sesi chat:
    1. ChatMessage tersimpan ke PostgreSQL tanpa galat konstrain sender_type
    2. Endpoint POST /api/surat/chat/<thread_id>/ mengembalikan is_ready_to_draft: True dan intent saat slot lengkap
    3. Endpoint GET /api/surat/chat/<thread_id>/ mengembalikan riwayat pesan dan snapshot sesi yang utuh
    """

    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create(
            id="u-std-contract-test",
            nama="Julian Sanchez",
            nip_nim="INF24001",
            role="STUDENT",
            password="password123",
        )
        self.user.is_authenticated = True
        self.surat_type = SuratType.objects.create(
            kode_surat="SR-MAG",
            nama_surat="Surat Rekomendasi Magang",
            required_payload_fields=[
                {"field": "instansi_tujuan", "label": "Instansi Tujuan"},
                {"field": "posisi_dilamar", "label": "Posisi Dilamar"},
            ],
        )
        self.thread = ChatThread.objects.create(
            user=self.user,
            title="Sesi Permohonan Surat Magang",
            document_type="SR-MAG",
            status=ChatThread.ThreadStatus.ACTIVE,
        )

    def test_chat_message_persistence_without_constraint_error(self):
        """Memastikan pesan chat dapat disimpan ke PostgreSQL tanpa galat pada kolom sender_type."""
        msg = ChatMessage.objects.create(
            thread=self.thread,
            sender="user",
            message="Saya ingin magang di PT Telekomunikasi.",
            slots_snapshot={"instansi_tujuan": "PT Telekomunikasi"},
        )
        self.assertIsNotNone(msg.id)
        saved = ChatMessage.objects.get(id=msg.id)
        self.assertEqual(saved.message, "Saya ingin magang di PT Telekomunikasi.")
        self.assertEqual(saved.sender, "user")

    def test_chat_message_api_view_post_ready_to_draft_contract(self):
        """
        Memastikan endpoint POST mengembalikan is_ready_to_draft: True, 
        intent, kode_surat, dan status ready_to_draft ketika seluruh slot wajib terpenuhi.
        """
        # Set session data di Redis / Manager dengan slot lengkap
        AutoSuratSessionManager.save_session(
            thread_id=str(self.thread.id),
            state="COLLECTING_SLOTS",
            intent="SR-MAG",
            slots={
                "instansi_tujuan": "PT Pertamina",
                "posisi_dilamar": "Full-Stack Developer",
                "chosen_destination": "email",
                "target_destination_address": "julian@pertamina.test",
            },
            missing_slots=[],
        )

        view = ChatSessionMessageAPIView.as_view()
        request = self.factory.post(
            f"/api/surat/chat/{self.thread.id}/",
            {"message": "lanjut"},
            format="json",
        )
        force_authenticate(request, user=self.user)

        with patch.object(AutoSuratSessionManager, "handle_incoming_message", return_value="Data lengkap."):
            response = view(request, thread_id=str(self.thread.id))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get("status"), "ready_to_draft")
        self.assertEqual(response.data.get("state"), "READY_TO_DRAFT")
        self.assertTrue(response.data.get("is_ready_to_draft"))
        self.assertEqual(response.data.get("intent"), "SR-MAG")
        self.assertEqual(response.data.get("kode_surat"), "SR-MAG")
        self.assertEqual(response.data.get("collected_slots", {}).get("instansi_tujuan"), "PT Pertamina")

    def test_chat_session_api_view_get_endpoint(self):
        """Memastikan endpoint GET /api/surat/chat/<thread_id>/ mengembalikan riwayat pesan dan snapshot sesi."""
        ChatMessage.objects.create(
            thread=self.thread,
            sender="user",
            message="Permohonan magang di PT Pertamina.",
        )
        ChatMessage.objects.create(
            thread=self.thread,
            sender="assistant",
            message="Siap, data posisi sudah dicatat.",
        )

        AutoSuratSessionManager.save_session(
            thread_id=str(self.thread.id),
            state="COLLECTING_SLOTS",
            intent="SR-MAG",
            slots={"instansi_tujuan": "PT Pertamina"},
            missing_slots=["posisi_dilamar"],
        )

        view = ChatSessionMessageAPIView.as_view()
        request = self.factory.get(f"/api/surat/chat/{self.thread.id}/")
        force_authenticate(request, user=self.user)

        response = view(request, thread_id=str(self.thread.id))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get("thread_id"), str(self.thread.id))
        self.assertEqual(response.data.get("intent"), "SR-MAG")
        self.assertFalse(response.data.get("is_ready_to_draft"))
        messages = response.data.get("messages", [])
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["sender"], "user")
        self.assertEqual(messages[1]["sender"], "assistant")


class IntentDetectionPipelineTestCase(TestCase):
    """
    Test suite untuk memvalidasi akurasi deteksi niat (Intent Detection):
    1. Memastikan input survey/observasi terklasifikasi sebagai SI-SUR (bukan SI-MAG)
    2. Memastikan surat izin magang terklasifikasi sebagai SI-MAG
    3. Memastikan surat rekomendasi magang terklasifikasi sebagai SR-MAG
    4. Memastikan surat keterangan aktif kuliah terklasifikasi sebagai SK-KUL
    5. Memastikan surat pengantar skck terklasifikasi sebagai SP-SKC
    """

    def setUp(self):
        SuratType.objects.get_or_create(kode_surat="SI-SUR", defaults={"nama_surat": "surat izin survey dan observasi"})
        SuratType.objects.get_or_create(kode_surat="SI-MAG", defaults={"nama_surat": "surat izin magang"})
        SuratType.objects.get_or_create(kode_surat="SR-MAG", defaults={"nama_surat": "surat rekomendasi magang"})
        SuratType.objects.get_or_create(kode_surat="SK-KUL", defaults={"nama_surat": "surat keterangan aktif kuliah"})
        SuratType.objects.get_or_create(kode_surat="SP-SKC", defaults={"nama_surat": "surat pengantar skck"})
        SuratType.objects.get_or_create(kode_surat="SP-TRA", defaults={"nama_surat": "surat pengantar transkip nilai"})
        SuratType.objects.get_or_create(kode_surat="SP-TAS", defaults={"nama_surat": "surat pengantar riset tugas akhir"})

    def test_detect_survey_observasi_resolves_to_si_sur(self):
        """Memastikan 'buatkan saya izin survey dan observasi' terdeteksi sebagai SI-SUR."""
        from surat.services.detect_intent import detect_intent_dynamically
        result = detect_intent_dynamically("buatkan saya izin survey dan observasi")
        self.assertEqual(result, "SI-SUR")

    def test_detect_izin_magang_resolves_to_si_mag(self):
        """Memastikan 'saya mau buat surat izin magang' terdeteksi sebagai SI-MAG."""
        from surat.services.detect_intent import detect_intent_dynamically
        result = detect_intent_dynamically("saya mau buat surat izin magang")
        self.assertEqual(result, "SI-MAG")

    def test_detect_rekomendasi_magang_resolves_to_sr_mag(self):
        """Memastikan 'rekomendasi magang' terdeteksi sebagai SR-MAG."""
        from surat.services.detect_intent import detect_intent_dynamically
        result = detect_intent_dynamically("rekomendasi magang pertamina")
        self.assertEqual(result, "SR-MAG")

    def test_detect_aktif_kuliah_resolves_to_sk_kul(self):
        """Memastikan 'surat keterangan aktif kuliah' terdeteksi sebagai SK-KUL."""
        from surat.services.detect_intent import detect_intent_dynamically
        result = detect_intent_dynamically("surat keterangan aktif kuliah untuk beasiswa")
        self.assertEqual(result, "SK-KUL")

    def test_detect_skck_resolves_to_sp_skc(self):
        """Memastikan 'pengantar skck' terdeteksi sebagai SP-SKC."""
        from surat.services.detect_intent import detect_intent_dynamically
        result = detect_intent_dynamically("pengantar skck kepolisian")
        self.assertEqual(result, "SP-SKC")
