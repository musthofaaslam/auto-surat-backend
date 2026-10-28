# Dokumentasi Teknis & Panduan Integrasi Backend: AutoSurat Agentic AI (`surat/agents/`)

---

## 1. Daftar Fitur Modul Agent yang Sudah Berjalan dengan Baik (Tervalidasi)

Seluruh komponen di dalam direktori `backend-django/surat/agents/` telah melalui audit logika dan pengujian otomatis (`test_agents.py`) dengan rincian kapabilitas sebagai berikut:

### A. Penyusunan Draf Surat & Zero-Hallucination Engine (`letter_agent.py`)
1. **Ekstraksi Dinamis 10 Jenis Surat Resmi Kampus:**
   - Mendukung penuh ke-10 kode surat (`SK-KUL`, `SK-BEA`, `SP-TRA`, `SP-SKC`, `SP-TAS`, `SP-MAG`, `SR-BEA`, `SR-MAG`, `SI-MAG`, `SI-SUR`) berdasarkan spesifikasi `required_field_surat.json`, kolom `SuratType.required_payload_fields` di DB, maupun `dynamic_fields_dict` kustom.
2. **Structured Outputs dengan Toleransi Skema Tinggi (`schemas.py`):**
   - Menggunakan skema Pydantic dinamis (`extra="ignore"`) dan pembersih *markdown code fence* (`` ```json ... ``` ``) otomatis, sehingga respons Gemini tidak pernah crash meskipun LLM menyertakan field ekstra atau blok markdown.
3. **Zero-Hallucination Policy & Token-Saving Guard:**
   - Jika mahasiswa belum menyebutkan atribut wajib pada prompt awal, agen secara deterministik memotong skor `self_critique_score <= 7`, menyusun kalimat pertanyaan klarifikasi yang spesifik per field, dan **melewati panggilan LLM ke-2 yang sia-sia** (menghemat 50% pemakaian token & waktu tunggu pada input tidak lengkap).
4. **Self-Reflection Loop dengan Deterministic Slot Merging:**
   - Apabila seluruh field wajib sudah lengkap pada Iterasi 1 tetapi skor kualitas bahasa `< 8`, agen menjalankan 1 kali iterasi perbaikan redaksional ke LLM dan melakukan **Deterministic Slot Merging** (`merge_payload_slots`) antara payload Iterasi 1 dan Iterasi 2 agar tidak ada atribut yang hilang saat revisi.
5. **Auto-Fallback Multi-Model untuk Error `404`, `429` (Rate Limit), dan `503`:**
   - Apabila model utama mengalami *high demand* (`503`), tidak ditemukan (`404`), atau kehabisan kuota/rate-limit per model (`429 RESOURCE_EXHAUSTED`), agen otomatis beralih mencoba kandidat di `FALLBACK_MODELS` (`gemini-3.1-flash-lite`, `gemini-3.8-flash`, `gemini-flash-lite-latest`).
6. **Dukungan Dokumen Multimodal Gemini API (`attachments`):**
   - Mampu menerima berkas lampiran PDF/Gambar (misal *Letter of Acceptance* / LoA magang, transkrip, atau pengumuman beasiswa) dan mengubahnya menjadi `types.Part.from_bytes` untuk diekstrak langsung oleh Gemini.

### B. Conversational Slot-Filling Memory & Multi-Turn Re-Draft (`slot_memory.py` & `prompts.py`)
1. **Akumulasi Konteks Multi-Turn Tanpa Kehilangan Riwayat (`clean_multiturn_prompt_context`):**
   - Merapikan tumpukan header `KONTEKS AWAL:` dan `INFORMASI TAMBAHAN / KOREKSI PENGGUNA:` dari seluruh iterasi revisi secara kronologis (`[Konteks Awal]`, `[Tambahan #1]`, `[Tambahan #2]`, dst.) tanpa membuang revisi di tengah.
2. **Filter Cerdas `is_value_filled()` & `CompatCleanString`:**
   - Membedakan secara akurat antara penanda kosong dari LLM (`"Tidak disebutkan"`, `"Belum ada"`, `"-"`, `None`) dengan kalimat penjelasan sah mahasiswa yang kebetulan memuat kata serupa (misal: *"Backend Developer (Tidak disebutkan divisi spesifik di pengumuman resmi)"*).
3. **Elevasi Skor Otomatis Saat Seluruh Slot Terpenuhi:**
   - Saat proses *Re-Draft* (`draft_letter_with_reflection`) berhasil melengkapi seluruh atribut wajib yang sebelumnya kosong, agen otomatis membersihkan catatan revisi lama dan memastikan `self_critique_score >= 8` agar surat tidak terjebak di `REVISION_REQUIRED`.

### C. Agentic Memory Loop & Proteksi Privasi / Anti-PII (`memory_agent.py`)
1. **Pra-Filter Diff Deterministik (`difflib.SequenceMatcher`):**
   - Hanya memanggil LLM jika benar-benar terdapat modifikasi teks antara `ai_original_draft` dan `final_approved_content`.
2. **PII Sanitizer pada Evaluasi Fallback (`_sanitize_pii_from_text`):**
   - Menyensor Nama, NIM, NIP, Nomor HP/WA, dan Email mahasiswa secara otomatis agar data pribadi tidak pernah bocor ke tabel `AgentFeedbackMemory` maupun *System Prompt* mahasiswa lain.
3. **Scoped Style Rules per Fakultas & Program Studi (`_load_active_style_rules`):**
   - Memuat aturan gaya bahasa dari `AgentFeedbackMemory` dengan memprioritaskan Program Studi dan Fakultas mahasiswa pemohon (`student_metadata`), serta melakukan deduplikasi *case-insensitive*.

### D. Safe Post-Approval Execution Tools (`execution_tools.py`)
1. **Resolusi Dinamis Pejabat Penandatangan (`signer`) & Kota Instansi:**
   - Memetakan nama lengkap (`signer.user.nama`), NIP (`signer.user.nip_nim`), jabatan struktural (`signer.jabatan_struktural`), dan kota universitas secara dinamis ke konteks template PDF maupun *fallback* PDF (tanpa hardcode pejabat fiktif).
2. **Deteksi Kesiapan Template HTML (`_is_template_ready_for_ai_content`):**
   - Memeriksa apakah file template HTML berukuran `> 0 byte`, bebas dari syntax error `{{ ../`, dan memiliki variabel penerima naskah AI (`{{ final_approved_content }}` / `{{ isi_surat }}`). Jika template backend belum siap, otomatis merender tata naskah dinas resmi terintegrasi.

---

## 2. Katalog Fungsi & Endpoint Internal Agen yang Siap Dipanggil Backend

Seluruh fungsi dan kelas berikut telah diekspor langsung di [`surat/agents/__init__.py`](file:///d:/Bintang/Semst7/Perancangan%20Komputasi%20Interaktif/auto-surat-backend/backend-django/surat/agents/__init__.py) sehingga tim Backend cukup mengimpornya dari `surat.agents`:

```python
from surat.agents import (
    SuratDraftingAgent,
    AgenticMemoryAgent,
    SuratExecutionTools,
    SlotMemoryManager,
    is_value_filled,
    extract_dynamic_fields_from_surat_type,
    evaluate_draft_readiness,
    ensure_approval_queue_for_request,
    persist_attachments_for_request,
    build_safe_validator_adapter,
    execute_post_approval_tools,
    compare_and_store_memory,
)
```

| Nama Fungsi / Method | Lokasi File | Kegunaan untuk Backend |
| :--- | :--- | :--- |
| `extract_dynamic_fields_from_surat_type(surat_type)` | `surat/agents/backend_bridge.py` | Mengekstrak kolom `required_payload_fields` dari model `SuratType` menjadi `dict` yang siap dikirim ke `draft_letter()`. |
| `persist_attachments_for_request(surat_req, attachments)` | `surat/agents/backend_bridge.py` | Mengunggah daftar file `attachments` ke Cloudinary, menyimpan record `SuratAttachment`, dan mengembalikan list *bytes* dokumen untuk parameter `attachments` di `draft_letter()`. |
| `agent.draft_letter(..., dynamic_fields_dict=..., attachments=...)` | `surat/agents/letter_agent.py` | Menyusun draf surat awal (Fase 1) dengan dukungan penuh spesifikasi field dinamis dan ekstraksi dokumen Multimodal (PDF/Gambar). |
| `agent.draft_letter_with_reflection(..., dynamic_fields_dict=..., attachments=...)` | `surat/agents/letter_agent.py` | Menyusun ulang draf surat (*Re-Draft*) berbasis memori sesi (`SlotMemoryManager`) dengan *Deterministic Slot Merging*. |
| `evaluate_draft_readiness(draft_output, kode_surat, dynamic_fields_dict)` | `surat/agents/backend_bridge.py` | Mengevaluasi hasil draf AI (`is_ready_for_approval`, `recommended_status`, `critique_score`, `missing_fields`, `structured_payload`) menggunakan `SlotMemoryManager` & `is_value_filled()`. |
| `ensure_approval_queue_for_request(surat_req)` | `surat/agents/backend_bridge.py` | Membuat antrean `SuratApproval` berjenjang berdasarkan `ApprovalRule` (`DPA` $\rightarrow$ `KAPRODI` $\rightarrow$ `DEKAN`) saat draf AI mencapai `PENDING_APPROVAL`. |
| `build_safe_validator_adapter(SURAT_VALIDATORS)` | `surat/agents/backend_bridge.py` | Mengadaptasi signature ke-10 fungsi validator di `surat/services/validators.py` agar tidak melempar `TypeError`. |
| `execute_post_approval_tools(surat_req, signer, final_approved_content, final_status)` | `surat/agents/execution_tools.py` | Menjalankan pipeline Fase 2 (Nomor Surat, TTE & QR Code, Render PDF dengan `signer` dinamis, Upload Cloudinary). |
| `compare_and_store_memory(surat_req, ai_original_draft, final_approved_content)` | `surat/agents/memory_agent.py` | Menjalankan pipeline Fase 3 (Komparasi diff gaya bahasa Dosen dengan filter anti-PII dan menyimpannya ke `AgentFeedbackMemory`). |

---

## 3. Panduan Integrasi Eksplisit untuk Tim Backend (Menutup 7 Poin Bagian 2)

> **Catatan:** Saat ini modul `surat/agents/backend_bridge.py` sudah menyediakan *jembatan kompatibilitas runtime* otomatis. Namun, agar arsitektur kode di `surat/views.py`, `surat/services/validators.py`, dan `templates/` bersih, eksplisit, dan mudah dipelihara oleh tim Backend, silakan terapkan penyambungan berikut pada file Backend terkait:

### Integrasi #1, #3, dan #4 pada `_execute_drafting_agent_worker` (`surat/views.py#L116-L195`)

Di `surat/views.py`, teruskan `dynamic_fields_dict` dan `attachments` ke `active_agent.draft_letter()`, gunakan `evaluate_draft_readiness()` untuk menggantikan pengecekan substring naif `"tidak disebutkan"`, dan panggil `ensure_approval_queue_for_request(surat_req)` saat status menjadi `PENDING_APPROVAL`:

```python
from .agents import (
    SuratDraftingAgent,
    evaluate_draft_readiness,
    ensure_approval_queue_for_request,
)

def _execute_drafting_agent_worker(
    surat_request_id: int,
    user_prompt_context: str,
    kode_surat: str,
    student_metadata: Optional[Dict[str, Any]] = None,
    agent: Optional[SuratDraftingAgent] = None,
    dynamic_fields_dict: Optional[Dict[str, Any]] = None,
    attachments: Optional[list] = None,
) -> None:
    close_old_connections()
    try:
        active_agent = agent if agent is not None else SuratDraftingAgent()
        draft_output = active_agent.draft_letter(
            user_prompt_context=user_prompt_context,
            kode_surat=kode_surat,
            student_metadata=student_metadata,
            dynamic_fields_dict=dynamic_fields_dict,  # <-- [Perbaikan #3] Teruskan field dinamis
            attachments=attachments,                  # <-- [Perbaikan #5] Teruskan lampiran multimodal
        )

        # <-- [Perbaikan #4] Gunakan evaluator resmi agen (bukan substring naif "tidak disebutkan")
        readiness = evaluate_draft_readiness(
            draft_output=draft_output,
            kode_surat=kode_surat,
            dynamic_fields_dict=dynamic_fields_dict,
        )

        surat_req = SuratRequest.objects.select_related(
            "student", "student__prodi", "student__fakultas", "kode_surat"
        ).get(pk=surat_request_id)
        surat_req.payload_data = readiness["structured_payload"]
        surat_req.ai_original_draft = draft_output.ai_original_draft
        surat_req.self_critique_score = readiness["critique_score"]
        surat_req.revision_notes = readiness["revision_notes"]

        if not readiness["is_ready_for_approval"]:
            surat_req.status = SuratStatus.REVISION_REQUIRED
            surat_req.save(update_fields=[
                "payload_data", "ai_original_draft", "self_critique_score", "revision_notes", "status"
            ])
            SuratAuditLog.objects.create(
                surat_request=surat_req,
                action_id="AI_REV_REQ",
                action="AI_DRAFTING_REJECTED_INCOMPLETE_INFO",
            )
            return

        surat_req.status = SuratStatus.PENDING_APPROVAL
        surat_req.save(update_fields=[
            "payload_data", "ai_original_draft", "self_critique_score", "revision_notes", "status"
        ])

        # <-- [Perbaikan #1] Bangun antrean SuratApproval berjenjang sesuai ApprovalRule
        ensure_approval_queue_for_request(surat_req)
```

---

### Integrasi #2 dan #1 pada `_execute_redraft_agent_worker` (`surat/views.py#L343-L415`)

Di `_execute_redraft_agent_worker`, ganti pengecekan `has_null_required` (`v is None` pada 3 field magang) dengan `evaluate_draft_readiness()`, dan panggil `ensure_approval_queue_for_request(surat_req)` ketika re-draft lolos ke `PENDING_APPROVAL`:

```python
        draft_output = active_agent.draft_letter_with_reflection(
            user_prompt_context=user_prompt_context,
            kode_surat=kode_surat,
            previous_draft=previous_draft,
            previous_payload=previous_payload,
            previous_score=previous_score,
            revision_notes=revision_notes,
            student_metadata=student_metadata,
        )

        # <-- [Perbaikan #2] Evaluasi kelengkapan slot untuk seluruh 10 jenis surat
        readiness = evaluate_draft_readiness(
            draft_output=draft_output,
            kode_surat=kode_surat,
        )

        surat_req.payload_data = readiness["structured_payload"]
        surat_req.ai_original_draft = draft_output.ai_original_draft
        surat_req.self_critique_score = readiness["critique_score"]
        surat_req.revision_notes = readiness["revision_notes"]

        if not readiness["is_ready_for_approval"]:
            surat_req.status = SuratStatus.REVISION_REQUIRED
            action_code = "AI_REDRAFT_STILL_INCOMPLETE"
        else:
            surat_req.status = SuratStatus.PENDING_APPROVAL
            action_code = "AI_REDRAFT_SUCCESS_PENDING_APPROVAL"

        surat_req.save(update_fields=[
            "payload_data", "ai_original_draft", "self_critique_score", "revision_notes", "status"
        ])

        # <-- [Perbaikan #1] Buat antrean SuratApproval jika berhasil masuk PENDING_APPROVAL
        if surat_req.status == SuratStatus.PENDING_APPROVAL:
            ensure_approval_queue_for_request(surat_req)
```

---

### Integrasi #3 dan #5 pada `SuratRequestCreateAPIView.post` (`surat/views.py#L664-L708`)

Di `SuratRequestCreateAPIView.post`, gunakan `persist_attachments_for_request()` untuk menyimpan file lampiran ke `SuratAttachment` & mengekstrak byte multimodal, serta gunakan `extract_dynamic_fields_from_surat_type(surat_type)`:

```python
from .agents import (
    extract_dynamic_fields_from_surat_type,
    persist_attachments_for_request,
)

        user_prompt_context = serializer.validated_data.get("user_prompt_context", "")
        initial_payload = serializer.validated_data.get("payload_data") or {}
        attachment_files = serializer.validated_data.get("attachments") or []

        surat_req = SuratRequest.objects.create(
            student=student_obj,
            kode_surat=surat_type,
            status=SuratStatus.SUBMITTED,
            payload_data=initial_payload,
            user_prompt_context=user_prompt_context,
        )

        # <-- [Perbaikan #5] Upload lampiran ke Cloudinary, simpan SuratAttachment, & siapkan byte Multimodal
        multimodal_attachments = persist_attachments_for_request(
            surat_request=surat_req,
            attachment_files=attachment_files,
        )

        # <-- [Perbaikan #3] Ekstrak required_payload_fields dari SuratType dengan aman
        dynamic_fields_dict = extract_dynamic_fields_from_surat_type(surat_type)

        worker_thread = threading.Thread(
            target=_execute_drafting_agent_worker,
            kwargs={
                "surat_request_id": surat_req.id,
                "user_prompt_context": user_prompt_context,
                "kode_surat": surat_type.kode_surat,
                "student_metadata": student_metadata,
                "agent": self.get_drafting_agent(),
                "dynamic_fields_dict": dynamic_fields_dict,
                "attachments": multimodal_attachments,
            },
            name=f"surat-drafting-agent-{surat_req.id}",
            daemon=True,
        )
```

---

### Integrasi #6: Kontrak Variabel untuk Template HTML (`templates/kerangka-surat/`)

Method `SuratExecutionTools.build_pdf_template_context()` di [`surat/agents/execution_tools.py`](file:///d:/Bintang/Semst7/Perancangan%20Komputasi%20Interaktif/auto-surat-backend/backend-django/surat/agents/execution_tools.py#L437-L542) telah mengirimkan dictionary *context* lengkap berikut untuk digunakan oleh tim Backend saat mengisi ke-10 file template HTML di `templates/kerangka-surat/`:

| Nama Variabel Django Template | Isi Data |
| :--- | :--- |
| `{{ nomor_surat }}` / `{{ nomor_surat_resmi }}` | Nomor surat resmi yang diterbitkan sekuensial. |
| `{{ nama_surat }}` / `{{ kode_surat }}` | Nama & kode jenis surat resmi. |
| `{{ nama_mahasiswa }}`, `{{ nim }}` | Nama lengkap dan NIM mahasiswa pemohon. |
| `{{ program_studi }}` / `{{ prodi }}` | Nama Program Studi mahasiswa. |
| `{{ fakultas }}` / `{{ nama_fakultas }}` | Nama Fakultas mahasiswa. |
| `{{ semester_aktif }}`, `{{ tahun_akademik }}` | Semester aktif dan Tahun Akademik mahasiswa. |
| **`{{ final_approved_content }}`** / **`{{ isi_surat }}`** | **Wajib dicantumkan di `<body>` template:** Naskah surat resmi hasil AI yang telah disetujui/disunting oleh Dosen. |
| `{{ payload_data.<nama_field> }}` | Dictionary atribut spesifik hasil ekstraksi AI (misal `{{ payload_data.instansi_tujuan }}`). |
| `{{ kota_surat }}`, `{{ tanggal_surat }}` | Kota instansi dan tanggal penerbitan surat. |
| `{{ nama_penandatangan }}` / `{{ signer_nama }}` | Nama lengkap pejabat/dosen yang menyetujui surat. |
| `{{ nip_penandatangan }}` / `{{ signer_nip }}` | NIP pejabat/dosen penandatangan. |
| `{{ jabatan_penandatangan }}` / `{{ signer_jabatan }}` | Jabatan struktural pejabat penandatangan. |
| `{{ qr_code_url }}` / `{{ qr_verification_code }}` | URL verifikasi publik tanda tangan elektronik (TTE). |

*(Selama berkas template di `templates/kerangka-surat/` masih berukuran 0 byte atau belum memuat tag `{{ final_approved_content }}` / `{{ isi_surat }}`, `SuratExecutionTools` akan secara otomatis merender PDF menggunakan template dinas resmi internal sehingga pencetakan surat tidak pernah gagal).*

---

### Integrasi #7: Penyelarasan Signature `SURAT_VALIDATORS` (`surat/services/validators.py`)

Di `surat/services/validators.py#L107-L119`, tim Backend cukup membungkus `SURAT_VALIDATORS` menggunakan `build_safe_validator_adapter` dari `surat.agents` (atau menyamakan parameter fungsi `validate_sk_bea`, `validate_sp_skc`, `validate_si_mag`, `validate_si_sur`, dan `validate_sp_tra`):

```python
from surat.agents import build_safe_validator_adapter

SURAT_VALIDATORS = build_safe_validator_adapter({
    "SK-KUL": validate_sk_kul,
    "SK-BEA": validate_sk_bea,
    "SP-TRA": validate_sp_tra,
    "SP-SKC": validate_sp_skc,
    "SP-TAS": validate_sp_tas,
    "SP-MAG": validate_sp_mag,
    "SR-BEA": validate_sr_bea,
    "SR-MAG": validate_sr_mag,
    "SI-MAG": validate_si_mag,
    "SI-SUR": validate_si_sur,
})
```

---

## 4. Validasi & Pengujian Otomatis (`test_agents.py`)

Untuk menjalankan seluruh suite pengujian modul agen dan jembatan integrasi backend (26 unit & integration tests):

```bash
python backend-django/surat/agents/test_agents.py -v
```
