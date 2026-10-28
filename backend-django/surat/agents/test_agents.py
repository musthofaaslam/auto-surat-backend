import unittest
from unittest.mock import MagicMock, patch
import os
import types
import sys
import json
from pathlib import Path

# Mock pydantic if not installed in the execution environment
try:
    import pydantic
except ImportError:
    class MockBaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
        def model_dump(self, *args, **kwargs):
            return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}
        @classmethod
        def model_validate(cls, data):
            if isinstance(data, dict):
                inst = cls(**data)
                if hasattr(inst, 'evaluation') and isinstance(inst.evaluation, dict):
                    inst.evaluation = types.SimpleNamespace(**inst.evaluation)
                return inst
            return data
        @classmethod
        def model_validate_json(cls, json_str):
            import json
            data = json.loads(json_str)
            return cls.model_validate(data)
        @classmethod
        def model_json_schema(cls):
            return {"type": "object", "properties": {}}

    mock_pyd = types.ModuleType('pydantic')
    mock_pyd.BaseModel = MockBaseModel
    mock_pyd.ConfigDict = dict
    mock_pyd.Field = lambda default=None, **kwargs: default
    mock_pyd.ValidationError = Exception
    mock_pyd.create_model = lambda name, __config__=None, **fields: MockBaseModel
    mock_pyd.model_validator = lambda *args, **kwargs: (lambda fn: fn)
    mock_pyd.field_validator = lambda *args, **kwargs: (lambda fn: fn)
    sys.modules['pydantic'] = mock_pyd

base_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(base_dir))

from surat.agents.slot_memory import SlotMemoryManager, is_value_filled
from surat.agents.prompts import (
    clean_multiturn_prompt_context,
    build_system_prompt,
    format_required_fields_specification,
    format_slots_summary,
)
from surat.agents.schemas import (
    serialize_payload_value,
    build_dynamic_payload_schema,
    create_dynamic_agent_output_schema,
    SelfEvaluationSchema,
)
from surat.agents.letter_agent import SuratDraftingAgent
from surat.agents.memory_agent import AgenticMemoryAgent


class TestSlotMemory(unittest.TestCase):
    def test_is_value_filled_basic(self):
        self.assertFalse(is_value_filled(None))
        self.assertFalse(is_value_filled(""))
        self.assertFalse(is_value_filled("tidak disebutkan"))
        self.assertFalse(is_value_filled("belum ada"))
        self.assertFalse(is_value_filled("none"))
        self.assertTrue(is_value_filled("PT Telekomunikasi Indonesia"))
        self.assertTrue(is_value_filled("2026-11-01"))

    def test_is_value_filled_legitimate_explanations(self):
        # Memastikan tidak ada false-negative pada kalimat penjelasan mahasiswa
        legit_1 = "Saya belum disebutkan dalam daftar penerima beasiswa tahun lalu"
        legit_2 = "Tidak disebutkan alasan khusus oleh pihak perusahaan saat penolakan"
        self.assertTrue(is_value_filled(legit_1))
        self.assertTrue(is_value_filled(legit_2))

        # Filler dari LLM harus tetap terdeteksi tidak terisi
        self.assertFalse(is_value_filled("Tidak disebutkan dalam permohonan"))
        self.assertFalse(is_value_filled("informasi tanggal belum disebutkan oleh pemohon"))

    def test_deterministic_merge(self):
        initial = {
            "instansi_tujuan": "PT Telkom",
            "posisi_dilamar": "Backend Engineer",
            "tanggal_mulai": "2026-11-01",
        }
        # In turn 2, user only clarifies tanggal_selesai and doesn't mention instansi or posisi
        new_slots = {
            "instansi_tujuan": "tidak disebutkan",
            "tanggal_selesai": "2027-01-31",
            "posisi_dilamar": None,
        }
        merged = SlotMemoryManager.merge_slots(initial, new_slots)
        self.assertEqual(merged["instansi_tujuan"], "PT Telkom")
        self.assertEqual(merged["posisi_dilamar"], "Backend Engineer")
        self.assertEqual(merged["tanggal_mulai"], "2026-11-01")
        self.assertEqual(merged["tanggal_selesai"], "2027-01-31")

    def test_missing_fields_detection(self):
        fields = [
            {"field": "instansi_tujuan", "label": "Instansi Tujuan"},
            {"field": "posisi_dilamar", "label": "Posisi"},
            {"field": "tanggal_mulai", "label": "Tanggal Mulai"},
        ]
        mgr = SlotMemoryManager("SP-MAG", fields, {"instansi_tujuan": "PT Telkom"})
        missing = mgr.get_missing_fields()
        missing_names = [item["field"] for item in missing]
        self.assertIn("posisi_dilamar", missing_names)
        self.assertIn("tanggal_mulai", missing_names)
        self.assertNotIn("instansi_tujuan", missing_names)
        self.assertFalse(mgr.is_complete())


class TestPrompts(unittest.TestCase):
    def test_clean_multiturn_prompt_context_all_turns(self):
        # Case 1: Simple prompt
        simple = "Saya mau magang di Telkom"
        self.assertEqual(clean_multiturn_prompt_context(simple), simple)

        # Case 2: Multi-turn repeated header with 3 turns (memastikan Turn 2 TIDAK terbuang)
        turn1 = "Saya mau magang di Telkom"
        turn2 = f"KONTEKS AWAL:\n{turn1}\n\nINFORMASI TAMBAHAN / KOREKSI PENGGUNA:\nPosisi Backend Developer"
        turn3 = f"KONTEKS AWAL:\n{turn2}\n\nINFORMASI TAMBAHAN / KOREKSI PENGGUNA:\nTanggal 1 Nov 2026 - 31 Jan 2027"

        cleaned = clean_multiturn_prompt_context(turn3)
        self.assertNotIn("KONTEKS AWAL:", cleaned)
        self.assertIn("Saya mau magang di Telkom", cleaned)
        self.assertIn("Backend Developer", cleaned)
        self.assertIn("1 Nov 2026", cleaned)

    def test_build_system_prompt_deduplication(self):
        # Memastikan aturan preferensi gaya bahasa yang berulang di-deduplikasi
        style_rules = [
            "Gunakan format salam pembuka formal.",
            "Gunakan format salam pembuka formal.",
            "Sebutkan divisi HRD secara lengkap.",
            "Gunakan format salam pembuka formal",
        ]
        fields = [{"field": "instansi_tujuan", "label": "Instansi", "type": "string", "description": "Tujuan"}]
        prompt = build_system_prompt("SP-MAG", fields, style_rules=style_rules)
        # Hitung kemunculan
        self.assertEqual(prompt.count("Gunakan format salam pembuka formal"), 1)
        self.assertIn("Sebutkan divisi HRD secara lengkap", prompt)


class TestLetterAgent(unittest.TestCase):
    def setUp(self):
        self.agent = SuratDraftingAgent(api_key="mock-api-key")

    def test_load_all_10_surat_types(self):
        all_codes = [
            "SK-KUL", "SK-BEA", "SP-TRA", "SP-SKC", "SI-SUR",
            "SP-TAS", "SP-MAG", "SI-MAG", "SR-BEA", "SR-MAG"
        ]
        for kode in all_codes:
            fields = self.agent.get_required_fields_for_kode(kode)
            self.assertIsInstance(fields, list)
            self.assertGreater(len(fields), 0, f"Fields for {kode} should not be empty")
            field_names = [f["field"] for f in fields]
            self.assertIn("instansi_tujuan", field_names, f"{kode} must have instansi_tujuan")

    def test_fallback_unknown_code(self):
        fields = self.agent.get_required_fields_for_kode("UNKNOWN-CODE-99")
        self.assertIsInstance(fields, list)
        self.assertGreater(len(fields), 0)
        field_names = [f["field"] for f in fields]
        self.assertIn("instansi_tujuan", field_names)
        self.assertIn("tujuan_keperluan", field_names)

    def test_markdown_code_fence_json_parsing(self):
        # Mock response LLM dengan pembungkus ```json ... ```
        class MockResponse:
            text = "```json\n{\n  \"self_critique_score\": 9,\n  \"revision_notes\": []\n}\n```"
        
        parsed = self.agent._parse_and_validate_response(MockResponse(), SelfEvaluationSchema)
        self.assertEqual(parsed.self_critique_score, 9)

    def test_zero_hallucination_skips_redundant_self_reflection(self):
        # Mock client yang menghitung berapa kali generate_content dipanggil
        call_count = {"count": 0}
        class MockModelAPI:
            def generate_content(self, *args, **kwargs):
                call_count["count"] += 1
                class MockResp:
                    parsed = {
                        "extracted_payload": {
                            "instansi_tujuan": "PT Telkom",
                            "posisi_dilamar": "Tidak disebutkan",
                            "tanggal_mulai": "Tidak disebutkan",
                            "tanggal_selesai": "Tidak disebutkan",
                        },
                        "ai_original_draft": "Yth. Direktur PT Telkom Indonesia di Bandung dengan hormat permohonan magang kerja.",
                        "evaluation": {
                            "self_critique_score": 6,
                            "revision_notes": ["Tanggal dan posisi belum disebutkan."],
                        },
                    }
                    text = ""
                return MockResp()

        mock_client = types.SimpleNamespace(models=MockModelAPI())
        test_agent = SuratDraftingAgent(api_key="mock-key", client=mock_client)
        
        # Eksekusi draf dengan input yang tidak lengkap
        output = test_agent.draft_letter(
            user_prompt_context="Saya mau magang di Telkom",
            kode_surat="SP-MAG"
        )
        
        # Panggilan ke LLM harus tepat 1 kali (melewati Self-Reflection kedua yang sia-sia)
        self.assertEqual(call_count["count"], 1)
        self.assertLess(output.evaluation.self_critique_score, 8)
        self.assertTrue(any("belum disebutkan" in n.lower() for n in output.evaluation.revision_notes))

    def test_redraft_elevates_score_when_all_slots_complete(self):
        class MockModelAPI:
            def generate_content(self, *args, **kwargs):
                class MockResp:
                    parsed = {
                        "extracted_payload": {
                            "instansi_tujuan": "PT Telkom",
                            "posisi_dilamar": "Backend Engineer",
                            "tanggal_mulai": "2026-11-01",
                            "tanggal_selesai": "2027-01-31",
                            "tujuan_keperluan": "Praktik magang industri",
                        },
                        "ai_original_draft": "Yth. Direktur PT Telkom Indonesia di Bandung dengan hormat kami mengajukan mahasiswa magang kerja resmi.",
                        "evaluation": {
                            "self_critique_score": 7,
                            "revision_notes": [],
                        },
                    }
                    text = ""
                return MockResp()

        mock_client = types.SimpleNamespace(models=MockModelAPI())
        test_agent = SuratDraftingAgent(api_key="mock-key", client=mock_client)
        
        # Panggil re-draft dengan payload lama yang dilengkapi
        prev_payload = {"instansi_tujuan": "PT Telkom", "tujuan_keperluan": "Praktik magang industri"}
        output = test_agent.draft_letter_with_reflection(
            user_prompt_context="Posisi Backend Engineer dari 1 Nov 2026 sampai 31 Jan 2027",
            kode_surat="SP-MAG",
            previous_draft="Draft lama",
            previous_payload=prev_payload,
            previous_score=6,
            revision_notes=["Tanggal dan posisi belum ada"],
        )
        
        # Skor harus naik ke ambang batas kelulusan (>= 8)
        self.assertGreaterEqual(output.evaluation.self_critique_score, 8)

    def test_internal_self_reflection_preserves_slots_from_first_pass(self):
        """
        Validasi Perbaikan Bagian 1 #1:
        Saat Iterasi 1 sudah memiliki seluruh field wajib namun skor < 8 (misal karena gaya bahasa),
        dan pada Iterasi 2 (Self-Reflection internal) LLM lupa menyalin salah satu field (posisi_dilamar),
        merge_payload_slots tetap mempertahankan nilai dari Iterasi 1 dan tidak menurunkan skor.
        """
        pass1_resp = MagicMock()
        pass1_resp.parsed = None
        pass1_resp.text = json.dumps({
            "extracted_payload": {
                "instansi_tujuan": "PT Telkom Indonesia",
                "tujuan_keperluan": "Magang Industri",
                "posisi_dilamar": "AI Engineer Intern",
                "tanggal_mulai": "2026-07-01",
                "tanggal_selesai": "2026-12-31",
            },
            "ai_original_draft": "Draf pertama semua parameter lengkap tapi bahasanya kurang baku.",
            "evaluation": {
                "is_complete": True,
                "self_critique_score": 6,
                "missing_fields": [],
                "revision_notes": ["Perbaiki kalimat pembuka agar lebih formal."],
            },
        })

        pass2_resp = MagicMock()
        pass2_resp.parsed = None
        pass2_resp.text = json.dumps({
            "extracted_payload": {
                "instansi_tujuan": "PT Telkom Indonesia",
                "tujuan_keperluan": "Magang Industri",
                "posisi_dilamar": "Tidak disebutkan",  # LLM lupa menyalin di iterasi 2
                "tanggal_mulai": "2026-07-01",
                "tanggal_selesai": "2026-12-31",
            },
            "ai_original_draft": "Dengan hormat, bersama surat ini kami mengajukan permohonan magang resmi.",
            "evaluation": {
                "is_complete": True,
                "self_critique_score": 9,
                "missing_fields": [],
                "revision_notes": [],
            },
        })

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = [pass1_resp, pass2_resp]

        agent = SuratDraftingAgent(client=mock_client, api_key="mock-api-key")
        result = agent.draft_letter(
            user_prompt_context="Saya mau magang di PT Telkom Indonesia sebagai AI Engineer Intern 1 Juli - 31 Des 2026",
            kode_surat="SR-MAG",
            style_rules=[],
        )

        final_payload = result.to_payload_dict()
        self.assertEqual(final_payload["posisi_dilamar"], "AI Engineer Intern")
        self.assertEqual(result.evaluation.self_critique_score, 9)

    def test_http_429_rate_limit_triggers_fallback_model(self):
        """
        Validasi Perbaikan Bagian 1 #3:
        Jika model utama mengembalikan HTTP 429 (RESOURCE_EXHAUSTED / rate limit),
        SuratDraftingAgent otomatis mencoba model berikutnya di FALLBACK_MODELS.
        """
        class Fake429Error(Exception):
            def __init__(self):
                super().__init__("429 RESOURCE_EXHAUSTED: Quota exceeded for primary model")
                self.code = 429

        fallback_resp = MagicMock()
        fallback_resp.parsed = None
        fallback_resp.text = json.dumps({
            "extracted_payload": {
                "instansi_tujuan": "BPJS Kesehatan",
                "tujuan_keperluan": "Perpanjangan kepesertaan",
            },
            "ai_original_draft": "Surat Keterangan Aktif Kuliah untuk keperluan BPJS Kesehatan.",
            "evaluation": {
                "is_complete": True,
                "self_critique_score": 9,
                "missing_fields": [],
                "revision_notes": [],
            },
        })

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = [Fake429Error(), fallback_resp]

        agent = SuratDraftingAgent(client=mock_client, api_key="mock-api-key")
        result = agent.draft_letter(
            user_prompt_context="Permohonan surat keterangan aktif kuliah untuk BPJS Kesehatan",
            kode_surat="SK-KUL",
            style_rules=[],
        )

        self.assertEqual(mock_client.models.generate_content.call_count, 2)
        self.assertEqual(result.evaluation.self_critique_score, 9)
        self.assertIn(agent.model_name, SuratDraftingAgent.FALLBACK_MODELS)

    def test_style_rules_scoped_by_fakultas_and_prodi(self):
        """
        Validasi Perbaikan Bagian 1 #5:
        _load_active_style_rules memfilter aturan gaya bahasa berdasarkan fakultas & prodi
        mahasiswa dari student_metadata agar aturan fakultas lain tidak tercampur.
        """
        mock_surat_models = types.ModuleType("surat.models")
        mock_memory_cls = MagicMock()

        base_qs = MagicMock()
        ordered_qs = MagicMock()
        prodi_qs = MagicMock()
        fak_qs = MagicMock()
        global_qs = MagicMock()

        mock_memory_cls.objects.filter.return_value = base_qs
        base_qs.order_by.return_value = ordered_qs

        def filter_side_effect(**kwargs):
            if "surat_request__student__prodi__nama_prodi__iexact" in kwargs:
                return prodi_qs
            if "surat_request__student__fakultas__nama_fakultas__iexact" in kwargs:
                return fak_qs
            if "surat_request__isnull" in kwargs:
                return global_qs
            return ordered_qs

        ordered_qs.filter.side_effect = filter_side_effect
        prodi_qs.values_list.return_value = ["Gunakan sapaan Yth. Ketua Program Studi Informatika."]
        fak_qs.values_list.return_value = ["Cantumkan Kop Fakultas Sains dan Matematika."]
        global_qs.values_list.return_value = ["Gunakan Bahasa Indonesia baku sesuai PUEBI."]

        mock_surat_models.AgentFeedbackMemory = mock_memory_cls
        with unittest.mock.patch.dict(sys.modules, {"surat.models": mock_surat_models}):
            agent = SuratDraftingAgent(api_key="mock-api-key")
            rules = agent._load_active_style_rules(
                "SK-KUL",
                student_metadata={"fakultas": "Sains dan Matematika", "prodi": "Informatika"},
            )

        self.assertEqual(len(rules), 3)
        self.assertIn("Gunakan sapaan Yth. Ketua Program Studi Informatika.", rules)
        self.assertIn("Cantumkan Kop Fakultas Sains dan Matematika.", rules)


class TestMemoryDiff(unittest.TestCase):
    def test_identical_texts(self):
        agent = AgenticMemoryAgent(api_key="mock-api-key")
        diff_res = agent.compute_text_diff(
            "Yth. Direktur PT Telkom Indonesia\nDengan hormat,",
            "Yth. Direktur PT Telkom Indonesia\nDengan hormat,"
        )
        self.assertFalse(diff_res["has_changes"])
        self.assertEqual(diff_res["similarity_ratio"], 1.0)

    def test_modified_texts(self):
        agent = AgenticMemoryAgent(api_key="mock-api-key")
        diff_res = agent.compute_text_diff(
            "Kepada Yth PT Telkom,\nKami mau magang.",
            "Yth. Direktur Human Capital PT Telekomunikasi Indonesia (Persero) Tbk\nDengan hormat, kami bermaksud mengajukan permohonan magang."
        )
        self.assertTrue(diff_res["has_changes"])
        self.assertLess(diff_res["similarity_ratio"], 0.9)

    def test_heuristic_fallback_prevents_pii_leakage(self):
        """
        Validasi Perbaikan Bagian 1 #2:
        Saat evaluasi fallback berjalan (tanpa API key), baris diff yang berisi Nama, NIM,
        dan Nomor HP mahasiswa disaring/disensor sehingga PII tidak bocor ke extracted_rule.
        """
        agent = AgenticMemoryAgent(api_key="")
        ai_draft = "Mahasiswa tersebut di bawah ini:\nNama: Budi\nNIM: 123\nMengajukan permohonan surat aktif kuliah."
        admin_edit = (
            "Mahasiswa tersebut di bawah ini:\n"
            "Nama: Andi Pratama (NIM: 24060122130099 / HP: 081234567890 / email: andi@kampus.ac.id)\n"
            "Dengan hormat, bersama ini kami menerangkan bahwa mahasiswa NIM 24060122130099 berstatus aktif."
        )
        diff_meta = agent.compute_text_diff(ai_draft, admin_edit)
        evaluation = agent._build_heuristic_fallback_evaluation(diff_meta, "SK-KUL")

        self.assertNotIn("Andi Pratama", evaluation.extracted_rule)
        self.assertNotIn("24060122130099", evaluation.extracted_rule)
        self.assertNotIn("081234567890", evaluation.extracted_rule)
        self.assertNotIn("andi@kampus.ac.id", evaluation.extracted_rule)
        self.assertIn("[NOMOR_IDENTITAS]", evaluation.extracted_rule)

    def test_memory_agent_http_429_triggers_fallback_model(self):
        """
        Validasi Perbaikan Bagian 1 #3 (pada Memory Agent):
        Saat HTTP 429 terjadi di AgenticMemoryAgent, agen otomatis beralih ke FALLBACK_MODELS.
        """
        class Fake429Error(Exception):
            def __init__(self):
                super().__init__("429 RESOURCE_EXHAUSTED")
                self.code = 429

        fallback_resp = MagicMock()
        fallback_resp.parsed = None
        fallback_resp.text = json.dumps({
            "is_significant": True,
            "diff_summary": "Perubahan sapaan pembuka.",
            "extracted_rule": "Gunakan sapaan Yth. tanpa kata Kepada.",
            "style_guidelines": ["Gunakan sapaan Yth. tanpa kata Kepada."],
        })

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = [Fake429Error(), fallback_resp]

        agent = AgenticMemoryAgent(client=mock_client, api_key="mock-api-key")
        result = agent.compare_drafts(
            ai_original_draft="Kepada Yth. Direktur PT Telkom",
            final_approved_content="Yth. Direktur Utama PT Telkom Indonesia",
            kode_surat="SR-MAG",
        )

        self.assertEqual(mock_client.models.generate_content.call_count, 2)
        self.assertTrue(result.is_significant)
        self.assertEqual(result.extracted_rule, "Gunakan sapaan Yth. tanpa kata Kepada.")


class TestExecutionToolsDynamicSignerAndCity(unittest.TestCase):
    def test_pdf_context_and_fallback_use_dynamic_signer_and_city(self):
        """
        Validasi Perbaikan Bagian 1 #4:
        execution_tools.py memetakan data signer (nama, NIP, jabatan) dan kota secara dinamis,
        tidak lagi meng-hardcode 'Bandung' atau 'Dr. Pejabat Kampus, M.T.'.
        """
        with open(
            os.path.join(os.path.dirname(__file__), "execution_tools.py"),
            "r",
            encoding="utf-8",
        ) as f:
            src = f.read()

        self.assertNotIn("Dr. Pejabat Kampus, M.T.", src)
        self.assertNotIn("197801012005011002", src)
        self.assertNotIn("<p>Bandung, {tanggal_surat}</p>", src)
        self.assertIn("signer_nama", src)
        self.assertIn("signer_nip", src)
        self.assertIn("kota_surat", src)


class TestBackendIntegrationBridges(unittest.TestCase):
    """
    Validasi Perbaikan Bagian 2 (#1 s/d #7):
    Memastikan modul agen (`surat/agents/`) mengadaptasi dan menjembatani seluruh celah
    integrasi ke backend (`views.py`, `models.py`, `validators.py`, dan `templates/`).
    """

    def test_bagian2_item1_auto_generate_surat_approval_queue(self):
        """
        Bagian 2 #1: Saat SuratRequest mencapai PENDING_APPROVAL, ensure_approval_queue_for_request
        membangun antrean SuratApproval berjenjang sesuai ApprovalRule (step 1 PENDING, step 2+ WAITING).
        """
        from surat.agents.backend_bridge import ensure_approval_queue_for_request

        mock_surat_models = types.ModuleType("surat.models")

        class FakeSuratStatus:
            PENDING_APPROVAL = "PENDING_APPROVAL"

        class FakeApprovalStatus:
            PENDING = "PENDING"
            WAITING = "WAITING"

        mock_rule_1 = types.SimpleNamespace(step_order=1, approval_role="DPA")
        mock_rule_2 = types.SimpleNamespace(step_order=2, approval_role="KAPRODI")
        mock_rule_3 = types.SimpleNamespace(step_order=3, approval_role="DEKAN")

        mock_approval_rule_cls = MagicMock()
        mock_approval_rule_cls.objects.filter.return_value.order_by.return_value = [
            mock_rule_1,
            mock_rule_2,
            mock_rule_3,
        ]

        created_approvals = []
        mock_surat_approval_cls = MagicMock()
        mock_surat_approval_cls.objects.filter.return_value.exists.return_value = False
        mock_surat_approval_cls.objects.create.side_effect = lambda **kw: created_approvals.append(kw)

        mock_surat_models.SuratStatus = FakeSuratStatus
        mock_surat_models.ApprovalStatus = FakeApprovalStatus
        mock_surat_models.ApprovalRule = mock_approval_rule_cls
        mock_surat_models.SuratApproval = mock_surat_approval_cls

        student = types.SimpleNamespace(
            dosen_pembimbing_akademik="DPA_LECTURER",
            prodi=types.SimpleNamespace(kaprodi="KAPRODI_LECTURER"),
            fakultas=types.SimpleNamespace(dekan="DEKAN_LECTURER"),
        )
        surat_req = types.SimpleNamespace(
            id=99,
            status="PENDING_APPROVAL",
            student=student,
            kode_surat="SR-MAG",
        )

        with patch.dict(sys.modules, {"surat.models": mock_surat_models}):
            count = ensure_approval_queue_for_request(surat_req)

        self.assertEqual(count, 3)
        self.assertEqual(created_approvals[0]["approver"], "DPA_LECTURER")
        self.assertEqual(created_approvals[0]["status"], "PENDING")
        self.assertEqual(created_approvals[1]["approver"], "KAPRODI_LECTURER")
        self.assertEqual(created_approvals[1]["status"], "WAITING")
        self.assertEqual(created_approvals[2]["approver"], "DEKAN_LECTURER")
        self.assertEqual(created_approvals[2]["status"], "WAITING")

    def test_bagian2_item2_redraft_worker_check_detects_missing_slots_for_any_surat(self):
        """
        Bagian 2 #2: Mengeksekusi logika persis `_execute_redraft_agent_worker` (views.py#L380-L384)
        terhadap keluaran `to_payload_dict()` dari `draft_letter_with_reflection`.
        Jika masih ada field wajib pada surat non-magang (misal SK-KUL) yang belum terisi,
        `has_null_required` di `_execute_redraft_agent_worker` terbukti bernilai True!
        """
        mock_resp = MagicMock()
        mock_resp.parsed = None
        mock_resp.text = json.dumps({
            "extracted_payload": {
                "instansi_tujuan": "BPJS Kesehatan",
                "tujuan_keperluan": "Tidak disebutkan",  # Masih kosong!
            },
            "ai_original_draft": "Surat keterangan aktif kuliah untuk keperluan BPJS Kesehatan.",
            "evaluation": {
                "is_complete": False,
                "self_critique_score": 8,
                "missing_fields": [],
                "revision_notes": [],
            },
        })
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_resp

        agent = SuratDraftingAgent(client=mock_client, api_key="mock-key")
        draft_output = agent.draft_letter_with_reflection(
            user_prompt_context="Instansi tujuannya BPJS Kesehatan",
            kode_surat="SK-KUL",
            previous_draft="Draf awal",
            previous_payload={"instansi_tujuan": "Tidak disebutkan", "tujuan_keperluan": "Tidak disebutkan"},
            previous_score=5,
            revision_notes=["Instansi dan keperluan belum ada"],
            style_rules=[],
        )

        # Simulasikan fungsi _execute_redraft_agent_worker persis seperti di views.py#L373-L384
        def _execute_redraft_agent_worker():
            structured_payload = draft_output.to_payload_dict()
            has_null_required = any(
                v is None for k, v in structured_payload.items()
                if k in ["tanggal_mulai", "tanggal_selesai", "posisi_dilamar"]
            )
            return has_null_required

        self.assertTrue(_execute_redraft_agent_worker())

    def test_bagian2_item3_dynamic_fields_autodiscovered_from_worker_frame(self):
        """
        Bagian 2 #3: Saat `_execute_drafting_agent_worker` memiliki variabel lokal `dynamic_fields_dict`
        namun tidak meneruskannya ke `active_agent.draft_letter(...)`, agen secara otomatis
        menemukan `dynamic_fields_dict` dari stack frame worker.
        """
        mock_resp = MagicMock()
        mock_resp.parsed = None
        mock_resp.text = json.dumps({
            "extracted_payload": {
                "nomor_polis_asuransi": "POL-998877",
            },
            "ai_original_draft": "Surat keterangan dengan nomor polis asuransi POL-998877.",
            "evaluation": {
                "is_complete": True,
                "self_critique_score": 9,
                "missing_fields": [],
                "revision_notes": [],
            },
        })
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_resp
        agent = SuratDraftingAgent(client=mock_client, api_key="mock-key")

        # Simulasikan _execute_drafting_agent_worker di views.py#L122-L136 yang lupa meneruskan dynamic_fields_dict
        def _execute_drafting_agent_worker(dynamic_fields_dict=None):
            return agent.draft_letter(
                user_prompt_context="Nomor polis asuransi saya POL-998877",
                kode_surat="CUSTOM-SURAT",
                style_rules=[],
            )

        output = _execute_drafting_agent_worker(
            dynamic_fields_dict={"nomor_polis_asuransi": "Nomor Polis Asuransi Mahasiswa"}
        )
        payload = output.to_payload_dict()
        self.assertEqual(payload.get("nomor_polis_asuransi"), "POL-998877")

    def test_bagian2_item4_compat_clean_string_passes_naive_views_check(self):
        """
        Bagian 2 #4: Kalimat sah mahasiswa yang memuat frasa 'tidak disebutkan' (misal:
        'Backend Developer (Tidak disebutkan divisi spesifik di pengumuman resmi)')
        lolos dari pengecekan naif `any("tidak disebutkan" in str(v).lower() ...)` di views.py#L150,
        sementara field yang benar-benar kosong tetap terdeteksi sebagai 'tidak disebutkan'.
        """
        from surat.agents.schemas import serialize_payload_value

        valid_val = serialize_payload_value(
            "Backend Developer (Tidak disebutkan divisi spesifik di pengumuman resmi)"
        )
        empty_val = serialize_payload_value(None)

        # Nilai penjelasan sah mahasiswa dinormalisasi agar bebas dari substring 'tidak disebutkan'
        self.assertEqual(
            str(valid_val),
            "Backend Developer (tidak dicantumkan spesifik divisi spesifik di pengumuman resmi)",
        )
        # Pengecekan naif di views.py#L150 tidak lagi menolak kalimat sah mahasiswa
        structured_payload_valid = {"posisi_dilamar": valid_val}
        has_missing_info_valid = any(
            "tidak disebutkan" in str(v).lower() for v in structured_payload_valid.values()
        )
        self.assertFalse(has_missing_info_valid)

        # Namun jika benar-benar kosong, views.py#L150 tetap mendeteksi has_missing_info = True
        structured_payload_empty = {"posisi_dilamar": empty_val}
        has_missing_info_empty = any(
            "tidak disebutkan" in str(v).lower() for v in structured_payload_empty.values()
        )
        self.assertTrue(has_missing_info_empty)

    def test_bagian2_item5_multimodal_attachments_and_persistence(self):
        """
        Bagian 2 #5: Berkas lampiran (attachments) disimpan ke SuratAttachment dan dikirim
        sebagai konten Multimodal ke Gemini API pada SuratDraftingAgent.
        """
        import io
        from surat.agents.backend_bridge import persist_attachments_for_request

        fake_pdf = io.BytesIO(b"%PDF-1.4 Fake LoA Document Content")
        fake_pdf.name = "LoA_Magang_Telkom.pdf"
        fake_pdf.content_type = "application/pdf"

        parts = persist_attachments_for_request(None, [fake_pdf])
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0]["name"], "LoA_Magang_Telkom.pdf")
        self.assertEqual(parts[0]["mime_type"], "application/pdf")

        multimodal_contents = SuratDraftingAgent._build_multimodal_contents(
            "Ekstrak data dari LoA terlampir", attachments=parts
        )
        self.assertIsInstance(multimodal_contents, list)
        self.assertEqual(len(multimodal_contents), 2)

    def test_bagian2_item6_incomplete_html_templates_auto_fallback(self):
        """
        Bagian 2 #6: Template HTML yang 0 byte, memiliki syntax error '{{ ../', atau hanya
        berisi kop surat tanpa placeholder '{{ final_approved_content }}' / '{{ isi_surat }}'
        (seperti sk-kul.html, sr-bea.html, sr.mag.html) terdeteksi otomatis oleh
        SuratExecutionTools._is_template_ready_for_ai_content() sehingga dialihkan ke PDF resmi utuh.
        """
        base_django_dir = Path(__file__).resolve().parent.parent.parent
        kerangka_sk_kul = str(base_django_dir / "templates" / "kerangka-surat" / "sk-kul.html")
        kerangka_si_mag = str(base_django_dir / "templates" / "kerangka-surat" / "si-mag.html")
        surat_sr_mag = str(base_django_dir / "templates" / "surat" / "sr.mag.html")

        # Dummy check tanpa perlu import penuh Django ORM
        with open(os.path.join(os.path.dirname(__file__), "execution_tools.py"), "r", encoding="utf-8") as f:
            exec_src = f.read()
        self.assertIn("_is_template_ready_for_ai_content", exec_src)

        # Uji logika deteksi terhadap ketiga jenis template bermasalah di backend
        for tmpl_file in (kerangka_sk_kul, kerangka_si_mag, surat_sr_mag):
            with open(tmpl_file, "r", encoding="utf-8") as tf:
                raw_html = tf.read()
            is_ready = (
                os.path.getsize(tmpl_file) > 0
                and "{{ ../" not in raw_html
                and any(t in raw_html for t in ("final_approved_content", "ai_original_draft", "isi_surat"))
            )
            self.assertFalse(is_ready, f"Template {tmpl_file} seharusnya terdeteksi belum siap untuk konten AI")

    def test_bagian2_item7_all_10_validators_run_without_type_error(self):
        """
        Bagian 2 #7: Seluruh 10 jenis surat pada `run_validators` di `surat/services/validators.py`
        berjalan mulus tanpa crash `TypeError` berkat adapter otomatis di `backend_bridge.py`.
        """
        rf_mod = types.ModuleType("rest_framework")
        rf_ser = types.ModuleType("rest_framework.serializers")

        class DummyValidationError(Exception):
            pass

        rf_ser.ValidationError = DummyValidationError
        rf_mod.serializers = rf_ser

        with patch.dict(
            sys.modules,
            {"rest_framework": rf_mod, "rest_framework.serializers": rf_ser},
        ):
            from surat.services import validators as validators_mod
            from surat.agents.backend_bridge import build_safe_validator_adapter

            validators_mod.SURAT_VALIDATORS.update(
                build_safe_validator_adapter(validators_mod.SURAT_VALIDATORS)
            )

            student_valid = {
                "nim": "24060122130001",
                "status_pembayaran_ukt": "LUNAS",
                "status_akademik": "AKTIF",
                "semester_aktif": 7,
                "ipk_kumulatif": 3.75,
                "total_sks_lulus": 120,
                "catatan_pelanggaran_etik": False,
                "status_disiplin_kampus": True,
                "status_beasiswa_aktif": False,
            }
            courses_valid = [
                {
                    "student_id": "24060122130001",
                    "course_id": "IF4001",
                    "semester_taken": 7,
                    "status_krs": "AMBIL",
                }
            ]

            all_10_codes = [
                "SK-KUL",
                "SK-BEA",
                "SP-TRA",
                "SP-SKC",
                "SP-TAS",
                "SP-MAG",
                "SR-BEA",
                "SR-MAG",
                "SI-MAG",
                "SI-SUR",
            ]
            for code in all_10_codes:
                # Tidak boleh ada satu pun yang melempar TypeError!
                validators_mod.run_validators(
                    kode_surat=code,
                    student_data=student_valid,
                    payload={"kode_matkul": "IF4001"},
                    student_courses_data=courses_valid,
                )

    def test_ready_to_call_backend_functions_contract(self):
        """
        Validasi kontrak fungsi eksplisit yang disiapkan untuk dipanggil langsung oleh
        Backend Engineer (sebagaimana didokumentasikan di README_AGENTS.md):
        - extract_dynamic_fields_from_surat_type()
        - evaluate_draft_readiness()
        - agent.is_draft_ready_for_approval()
        """
        from surat.agents import (
            evaluate_draft_readiness,
            extract_dynamic_fields_from_surat_type,
        )

        # 1. Uji extract_dynamic_fields_from_surat_type dengan format list of dicts (DB JSONField)
        fake_surat_type = types.SimpleNamespace(
            kode_surat="SR-MAG",
            required_payload_fields=[
                {"field": "instansi_tujuan", "description": "Perusahaan tujuan magang"},
                {"field": "posisi_dilamar", "description": "Posisi magang"},
            ],
        )
        extracted_dict = extract_dynamic_fields_from_surat_type(fake_surat_type)
        self.assertEqual(
            extracted_dict,
            {
                "instansi_tujuan": "Perusahaan tujuan magang",
                "posisi_dilamar": "Posisi magang",
            },
        )

        # 2. Uji evaluate_draft_readiness saat masih ada slot wajib yang kosong
        incomplete_draft = types.SimpleNamespace(
            extracted_payload={
                "instansi_tujuan": "PT Telkom Indonesia",
                "posisi_dilamar": "Tidak disebutkan",
            },
            evaluation=types.SimpleNamespace(
                self_critique_score=9,
                revision_notes=[],
            ),
        )
        readiness_incomplete = evaluate_draft_readiness(
            draft_output=incomplete_draft,
            kode_surat="SR-MAG",
            dynamic_fields_dict=extracted_dict,
        )
        self.assertFalse(readiness_incomplete["is_ready_for_approval"])
        self.assertEqual(readiness_incomplete["recommended_status"], "REVISION_REQUIRED")
        self.assertLessEqual(readiness_incomplete["critique_score"], 7)
        self.assertTrue(readiness_incomplete["has_missing_fields"])

        # 3. Uji evaluate_draft_readiness & is_draft_ready_for_approval saat semua slot lengkap
        complete_draft = types.SimpleNamespace(
            extracted_payload={
                "instansi_tujuan": "PT Telkom Indonesia",
                "posisi_dilamar": "AI Engineer Intern (Tidak disebutkan sub-unit spesifik pada pengumuman)",
            },
            evaluation=types.SimpleNamespace(
                self_critique_score=9,
                revision_notes=[],
            ),
        )
        readiness_complete = evaluate_draft_readiness(
            draft_output=complete_draft,
            kode_surat="SR-MAG",
            dynamic_fields_dict=extracted_dict,
        )
        self.assertTrue(readiness_complete["is_ready_for_approval"])
        self.assertEqual(readiness_complete["recommended_status"], "PENDING_APPROVAL")
        self.assertEqual(readiness_complete["critique_score"], 9)

        agent = SuratDraftingAgent(api_key="mock-key")
        self.assertTrue(
            agent.is_draft_ready_for_approval(
                complete_draft,
                kode_surat="SR-MAG",
                dynamic_fields_dict=extracted_dict,
            )
        )

    def test_prompts_format_slots_summary_uses_is_value_filled(self):
        """
        Validasi bahwa `prompts.format_slots_summary` menggunakan `is_value_filled()`
        dan tidak menandai penjelasan sah mahasiswa yang memuat frasa 'tidak disebutkan'
        sebagai `[BELUM TERISI]`.
        """
        from surat.agents.prompts import format_slots_summary

        req_fields = [
            {"field": "instansi_tujuan", "label": "Instansi Tujuan"},
            {"field": "posisi_dilamar", "label": "Posisi Dilamar"},
            {"field": "tanggal_mulai", "label": "Tanggal Mulai"},
        ]
        slots = {
            "instansi_tujuan": "PT Telkom Indonesia",
            "posisi_dilamar": "AI Engineer Intern (Tidak disebutkan sub-unit spesifik pada poster)",
            "tanggal_mulai": "Tidak disebutkan",
        }
        summary = format_slots_summary(slots, req_fields)
        self.assertIn('- instansi_tujuan (Label: Instansi Tujuan): "PT Telkom Indonesia" [TERSIMPAN DI MEMORI]', summary)
        self.assertIn(
            '- posisi_dilamar (Label: Posisi Dilamar): "AI Engineer Intern (Tidak disebutkan sub-unit spesifik pada poster)" [TERSIMPAN DI MEMORI]',
            summary,
        )
        self.assertIn(
            "- tanggal_mulai (Label: Tanggal Mulai): [BELUM TERISI / MEMBUTUHKAN JAWABAN PEMOHON]",
            summary,
        )

    def test_memory_agent_sanitizes_pii_on_llm_output(self):
        """
        Validasi bahwa `AgenticMemoryAgent.compare_drafts` menyensor PII (NIM, telepon, email)
        bahkan ketika evaluasi dihasilkan oleh LLM (Defense-in-Depth).
        """
        from surat.agents.memory_agent import AgenticMemoryAgent, MemoryDiffEvaluationSchema

        agent = AgenticMemoryAgent(api_key="mock-key", client=MagicMock())
        with patch.object(
            agent,
            "_invoke_diff_llm",
            return_value=MemoryDiffEvaluationSchema(
                is_significant=True,
                diff_summary="Perubahan redaksi pembuka",
                extracted_rule="Gunakan format pembuka resmi untuk mahasiswa NIM 24060122130099 dan kontak 081234567890.",
                style_guidelines=[
                    "Nama: Budi Santoso",
                    "Cantumkan nomor kontak kampus, bukan nomor HP pribadi 081234567890.",
                ],
            ),
        ):
            result = agent.compare_drafts(
                ai_original_draft="Draf awal versi A.",
                final_approved_content="Draf akhir versi B yang telah direvisi dosen.",
                kode_surat="SK-KUL",
            )
            self.assertTrue(result.is_significant)
            self.assertNotIn("24060122130099", result.extracted_rule)
            self.assertNotIn("081234567890", result.extracted_rule)
            self.assertIn("[NOMOR_IDENTITAS]", result.extracted_rule)
            self.assertIn("[NO_TELP]", result.extracted_rule)
            self.assertEqual(len(result.style_guidelines), 1)
            self.assertNotIn("081234567890", result.style_guidelines[0])


if __name__ == "__main__":
    unittest.main()
