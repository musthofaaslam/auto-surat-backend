# Dokumentasi Teknis & Panduan Integrasi: AutoSurat Agentic AI (Level 2)

Dokumen ini ditujukan bagi Project Manager (PM), tim Frontend, dan tim DevOps sebagai panduan integrasi arsitektur Agentic AI Level 2 pada sistem `auto-surat-backend`.

---

## 1. Overview Arsitektur: Agentic AI Level 2 (Human-in-the-Loop & State Pausing)

Sistem AutoSurat menerapkan arsitektur **Agentic AI Level 2 (Agent as a Copilot / Gatekeeper)** untuk menjamin keabsahan hukum pada penerbitan dokumen resmi universitas, Tanda Tangan Elektronik (TTE), dan verifikasi QR Code publik.

Prinsip inti dari arsitektur ini adalah **State Pausing**, yang memisahkan siklus hidup dokumen menjadi dua fase terisolasi:

1. **Fase Pembuatan Draf oleh AI (Pra-Approval):**
   - Mahasiswa cukup mengirimkan konteks keperluan surat dalam bahasa alami (natural language).
   - `SuratDraftingAgent` mengekstrak atribut terstruktur sesuai kontrak `required_field_surat.json`, menyusun naskah surat dinas formal, dan menjalankan *Self-Reflection Loop* (evaluasi kualitas mandiri dengan ambang skor minimal `8/10`).
   - **Titik Henti Mutlak (State Pausing):** Setelah draf selesai disusun, status surat dikunci pada `PENDING_APPROVAL`. Pada tahap ini, sistem **dilarang keras** menerbitkan Nomor Surat Resmi, membuat token TTE, membuat QR Code, ataupun mengunggah PDF ke Cloudinary.
2. **Fase Persetujuan Manusia & Eksekusi Alat (Pasca-Approval):**
   - Dosen atau Pejabat berwenang meninjau draf AI pada dashboard, melakukan penyuntingan redaksional apabila diperlukan, dan memberikan keputusan `APPROVE` atau `REJECT`.
   - Hanya setelah keputusan `APPROVE` final diterima dari pejabat berwenang, `SuratExecutionTools` mengeksekusi penomoran resmi, pembuatan hash SHA-256 TTE & QR Code verifikasi, pencetakan PDF melalui WeasyPrint, serta pengunggahan ke Cloudinary hingga status akhir menjadi `SENT` atau `PRINTED`.

---

## 2. Environment Setup (Konfigurasi Production `.env`)

Tambahkan variabel lingkungan berikut pada berkas `.env` di peladen (server) production:

```ini
# Kredensial Utama Google Gemini API (Wajib)
GEMINI_API_KEY=your_production_gemini_api_key_here

# Model LLM untuk Penyusunan Draf (Fase 1) dan Evaluasi Memori Diffing (Fase 3)
GEMINI_MODEL_NAME=gemini-3.8-flash
GEMINI_MEMORY_MODEL_NAME=gemini-3.8-flash

# Parameter Operasional Self-Reflection & Batas Waktu Jaringan Agen
AGENT_CRITIQUE_MIN_SCORE=8
AGENT_MAX_REVISIONS=1
AGENT_TIMEOUT_SECONDS=30.0
AGENT_MEMORY_TIMEOUT_SECONDS=20.0

# Kredensial Penyimpanan Dokumen PDF Cloudinary (Wajib untuk Eksekusi Alat Fase 2)
CLOUDINARY_CLOUD_NAME=your_cloudinary_cloud_name
CLOUDINARY_API_KEY=your_cloudinary_api_key
CLOUDINARY_API_SECRET=your_cloudinary_api_secret
```

| Variabel | Nilai Rekomendasi | Deskripsi |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | *(Rahasia)* | Kunci autentikasi API Google GenAI SDK (`google-genai`). |
| `GEMINI_MODEL_NAME` | `gemini-3.8-flash` | Model utama untuk ekstraksi payload dan penyusunan draf surat. |
| `GEMINI_MEMORY_MODEL_NAME` | `gemini-3.8-flash` | Model berbiaya rendah untuk komparasi *diff* gaya bahasa Dosen. |
| `AGENT_CRITIQUE_MIN_SCORE` | `8` | Skor minimum (skala 1-10) agar draf AI lolos evaluasi mandiri tanpa revisi ulang. |
| `AGENT_MAX_REVISIONS` | `1` | Batas maksimum iterasi perbaikan otomatis (*Self-Reflection Loop*). |
| `AGENT_TIMEOUT_SECONDS` | `30.0` | Batas waktu tunggu panggilan HTTP ke layanan LLM (detik). |

---

## 3. Alur API (API Flow) untuk Integrasi Frontend

Seluruh proses inferensi AI dan pembuatan dokumen PDF dieksekusi di latar belakang (*background worker thread*) agar aplikasi Frontend tidak mengalami kendala *HTTP Request Timeout*.

### Langkah 1: Pengajuan Surat oleh Mahasiswa (Asinkron)
- **Endpoint:** `POST /api/surat/request/`
- **Autentikasi:** Bearer Token (Akun Mahasiswa)
- **Request Body:**
  ```json
  {
    "kode_surat": "SP-MAG",
    "user_prompt_context": "Saya ingin mengajukan surat pengantar magang ke PT Telkom Indonesia sebagai Backend Engineer Intern mulai 1 November 2026 sampai 31 Januari 2027."
  }
  ```
- **Response (`202 Accepted`):**
  ```json
  {
    "status": "success",
    "message": "Permohonan surat Surat Pengantar Magang berhasil diterima dan sedang diproses secara asinkron oleh agen AI.",
    "request_id": 101,
    "surat_status": "SUBMITTED",
    "data": {
      "request_id": 101,
      "kode_surat": "SP-MAG",
      "status": "SUBMITTED"
    }
  }
  ```
- **Catatan Frontend:** Karena respons bersifat asinkron (`202 Accepted`), status awal surat adalah `SUBMITTED`. Worker AI bekerja di latar belakang untuk menyusun draf.

### Langkah 2: Pengecekan Status `PENDING_APPROVAL` & Pratinjau Draf
- **Endpoint:** `GET /api/surat/requests/{id}/`
- **Autentikasi:** Bearer Token (Mahasiswa / Dosen)
- **Mekanisme Frontend:** Lakukan *polling* berkala (misal setiap 2-3 detik) atau muat ulang halaman detail hingga atribut `status` berubah dari `SUBMITTED` menjadi `PENDING_APPROVAL` (atau `FAILED` jika terjadi gangguan layanan).
- **Atribut Penting pada Response `GET /api/surat/requests/{id}/` saat `PENDING_APPROVAL`:**
  - `payload_data`: Objek JSON terstruktur hasil ekstraksi AI (`instansi_tujuan`, `posisi_dilamar`, `tanggal_mulai`, `tanggal_selesai`, `tujuan_keperluan`).
  - `ai_original_draft`: Teks naskah surat formal yang disusun oleh AI (ditampilkan pada editor pratinjau Dosen/Admin).
  - `self_critique_score`: Skor kualitas draf (1-10) hasil evaluasi internal AI.
  - `revision_notes`: Daftar catatan evaluasi internal AI untuk diperhatikan oleh Dosen/Admin.
  - `nomor_surat_resmi`, `file_pdf_url`, `qr_verification_code`: Masih bernilai `null` (jaminan *State Pausing*).

### Langkah 3: Tindakan Persetujuan oleh Dosen/Pejabat (Asinkron)
- **Endpoint:** `POST /api/surat/approval/{approval_id}/action/`
- **Autentikasi:** Bearer Token (Akun Dosen / Pejabat Penyetuju)
- **Request Body (Saat Menyetujui / `APPROVE`):**
  ```json
  {
    "action": "APPROVE",
    "catatan": "Disetujui setelah penyesuaian redaksi sapaan instansi.",
    "final_approved_content": "Yth. Direktur Human Capital PT Telekomunikasi Indonesia (Persero) Tbk di Tempat...",
    "final_status": "SENT"
  }
  ```
  *(Catatan: Jika Dosen tidak mengubah isi draf, `final_approved_content` dapat berisi teks yang sama dengan `ai_original_draft` atau dikosongkan agar sistem otomatis menggunakan `ai_original_draft`. Atribut `final_status` dapat diisi `"SENT"` atau `"PRINTED"`).*
- **Request Body (Saat Menolak / `REJECT`):**
  ```json
  {
    "action": "REJECT",
    "alasan_penolakan": "Rentang tanggal magang berbenturan dengan jadwal ujian akhir semester."
  }
  ```
- **Response (`200 OK`):**
  - Sistem langsung menyimpan `final_approved_content`, mengubah status transisi ke `APPROVED`, dan mendelegasikan proses pencetakan PDF, TTE, Cloudinary, serta evaluasi memori ke *background thread*.

### Langkah 4: Eksekusi TTE, Cloudinary & Pengambilan Dokumen Final
- Di latar belakang, `_execute_approval_pipeline_worker` menjalankan `SuratExecutionTools`:
  1. Menerbitkan `nomor_surat_resmi` secara sekuensial.
  2. Membuat sidik jari digital SHA-256 (`hash_document`) dan token QR Code pada tabel `TteSignature`.
  3. Merender template HTML menjadi PDF dan mengunggahnya ke Cloudinary (`file_pdf_url`).
  4. Memperbarui status akhir surat menjadi `SENT` atau `PRINTED`.
- **Pengambilan Hasil Akhir oleh Frontend (`GET /api/surat/requests/{id}/`):**
  - Ketika proses latar belakang selesai, endpoint detail surat mahasiswa akan menampilkan:
    - `status`: `"SENT"` atau `"PRINTED"`
    - `nomor_surat_resmi`: Nomor surat resmi yang telah terbit
    - `file_pdf_url`: URL unduhan PDF resmi dari Cloudinary
    - `qr_verification_code`: URL verifikasi publik QR Code
    - `signatures`: Array berisi detail tanda tangan digital pejabat (`signer_name`, `signer_nip`, `hash_document`, `token`, `created_at`)

---

## 4. Agentic Memory Loop (Pembelajaran Preferensi Otomatis)

Setiap kali Dosen/Pejabat menyetujui surat pada tahap akhir, sistem secara otomatis menjalankan **Agentic Memory Loop** (`AgenticMemoryAgent` di dalam `surat/agents/memory_agent.py`):

1. **Komparasi Cerdas (Diffing):** Agen membandingkan teks asli buatan AI (`ai_original_draft`) dengan teks akhir yang disetujui Dosen (`final_approved_content`).
2. **Efisiensi Biaya & Latensi:** Jika Dosen menyetujui draf tanpa mengubah teks (identik), agen melewati pemanggilan LLM sehingga tidak ada biaya token tambahan.
3. **Ekstraksi Pedoman Gaya Bahasa (Style Guidelines):** Jika Dosen melakukan revisi substantif (misalnya mengubah format sapaan jabatan, istilah baku, atau struktur paragraf), LLM `gemini-3.8-flash` merangkum pola koreksi tersebut menjadi aturan umum (`extracted_rule`) dan menyimpannya ke tabel `AgentFeedbackMemory` berdasarkan `kode_surat`.
4. **Injeksi Otomatis pada Pengajuan Berikutnya:** Saat ada mahasiswa lain yang mengajukan jenis surat (`kode_surat`) yang sama di masa mendatang, `SuratDraftingAgent` otomatis memuat aturan aktif dari `AgentFeedbackMemory` dan menyuntikkannya ke dalam *System Prompt*, sehingga kualitas draf AI terus beradaptasi mengikuti standar redaksional pejabat kampus tanpa perlu mengubah kode program.

