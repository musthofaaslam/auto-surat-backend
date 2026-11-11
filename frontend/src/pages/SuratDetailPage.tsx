import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import suratService from '../services/suratService';
import { extractErrorMessage } from '../services/api';
import type { SuratRequestDetail } from '../types';
import StatusBadge from '../components/StatusBadge';
import PDFViewer from '../components/PDFViewer';
import AgentPipelineStepper from '../components/AgentPipelineStepper';
import DiffViewer from '../components/DiffViewer';
import OfficialLetterSheet from '../components/OfficialLetterSheet';
import {
  ArrowLeft,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  Clock,
  ShieldCheck,
  Send,
  AlertCircle,
  FileCode,
  ExternalLink,
  Layers,
  Paperclip,
  FileText,
  GitCompare,
  Eye,
} from 'lucide-react';

// Architectural Note:
// Executive inspector displaying authentic Indonesian university official letterhead (A4 Sheet),
// Phase 3 AgentFeedbackMemory diff comparator, multi-stage approval stepper,
// and real-time polling during asynchronous drafting/hashing execution.

export const SuratDetailPage: React.FC = () => {
  const { user } = useAuth();
  const { id } = useParams<{ id: string }>();
  const [detail, setDetail] = useState<SuratRequestDetail | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Determine whether the logged in user is a reviewer/approver (Lecturer, Staff, Admin)
  const isApproverOrLecturer =
    user?.role === 'LECTURER' || user?.role === 'STAFF' || user?.role === 'ADMIN';

  // Inspector View Modes: 'sheet' (Authentic A4 Letter) | 'audit' (AI Telemetry & Diff) | 'pdf' (Published PDF)
  const [inspectorView, setInspectorView] = useState<'sheet' | 'audit' | 'pdf'>('sheet');

  // Re-draft state
  const [additionalContext, setAdditionalContext] = useState<string>('');
  const [isSubmittingRedraft, setIsSubmittingRedraft] = useState<boolean>(false);
  const [redraftSuccess, setRedraftSuccess] = useState<string | null>(null);
  const [redraftError, setRedraftError] = useState<string | null>(null);

  const fetchDetail = async () => {
    if (!id) return;
    try {
      const data = await suratService.getSuratRequestDetail(parseInt(id, 10));
      setDetail(data);
    } catch {
      setErrorMsg('Gagal memuat rincian permohonan surat dari server.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchDetail();
  }, [id]);

  // Real-time polling for asynchronous workers
  useEffect(() => {
    if (!detail) return;
    if (
      detail.status === 'SUBMITTED' ||
      detail.status === 'IN_REVIEW' ||
      (detail.status === 'APPROVED' && !detail.file_pdf_url)
    ) {
      const timer = setInterval(() => {
        fetchDetail();
      }, 3500);
      return () => clearInterval(timer);
    }
  }, [detail?.status, detail?.file_pdf_url]);

  const handleRedraftSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!id || !additionalContext.trim()) return;

    setIsSubmittingRedraft(true);
    setRedraftError(null);
    setRedraftSuccess(null);

    try {
      const res = await suratService.redraftSuratRequest(parseInt(id, 10), {
        additional_prompt_context: additionalContext.trim(),
      });
      setRedraftSuccess(res.message || 'Informasi tambahan revisi berhasil dikirim ke agen.');
      setAdditionalContext('');
      fetchDetail();
    } catch (err: any) {
      setRedraftError(
        extractErrorMessage(err, 'Gagal mengirim informasi perbaikan revisi.')
      );
    } finally {
      setIsSubmittingRedraft(false);
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-[70vh] flex flex-col items-center justify-center space-y-3">
        <RefreshCw className="w-8 h-8 animate-spin text-slate-500" />
        <span className="text-sm font-semibold text-slate-700">Menghubungkan ke berkas persuratan...</span>
      </div>
    );
  }

  if (errorMsg || !detail) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-16 text-center">
        <div className="p-4 bg-rose-50 text-rose-600 rounded-full inline-flex mb-4 border border-rose-200">
          <AlertCircle className="w-8 h-8" />
        </div>
        <h2 className="text-xl font-bold text-slate-900">Berkas Surat Tidak Ditemukan</h2>
        <p className="text-sm text-slate-500 mt-2">{errorMsg || 'Data permohonan surat tidak tersedia.'}</p>
        <div className="mt-6">
          <Link
            to="/dashboard"
            className="inline-flex items-center text-sm font-semibold text-slate-800 bg-white border border-slate-300 px-4 py-2.5 rounded-lg shadow-2xs transition ts-btn"
          >
            <ArrowLeft className="w-4 h-4 mr-2" />
            Kembali ke Dasbor
          </Link>
        </div>
      </div>
    );
  }

  const isRevisionNeeded =
    detail.status === 'REVISION_REQUIRED' || detail.status === 'FAILED';

  const notesList = Array.isArray(detail.revision_notes)
    ? detail.revision_notes
    : detail.revision_notes
    ? [String(detail.revision_notes)]
    : [];

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8">
      {/* 1. TOP HEADER & BREADCRUMB COCKPIT */}
      <div className="ts-card p-6 sm:p-8 bg-white flex flex-col md:flex-row md:items-center md:justify-between gap-5">
        <div>
          <div className="flex items-center space-x-2 text-xs font-semibold text-slate-500">
            <Link
              to="/dashboard"
              className="hover:text-slate-900 transition flex items-center"
            >
              <ArrowLeft className="w-3.5 h-3.5 mr-1" />
              Dasbor
            </Link>
            <span className="text-slate-300">/</span>
            <span className="font-mono text-slate-700">Berkas #{detail.id}</span>
            <span className="text-slate-300">•</span>
            <span className="font-mono text-blue-700 bg-blue-50 px-2 py-0.5 rounded border border-blue-200/60 font-semibold">
              [{detail.kode_surat}]
            </span>
          </div>

          <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight mt-2">
            {detail.nama_surat}
          </h1>

          <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-sm text-slate-600 mt-2 font-medium">
            <div>
              Pemohon:{' '}
              <strong className="text-slate-900">{detail.nama_mahasiswa}</strong> (
              <span className="font-mono">{detail.nim_mahasiswa}</span>)
            </div>
            <div>
              Prodi: <span className="text-slate-800">{detail.prodi_mahasiswa}</span>
            </div>
            <div>
              Fakultas: <span className="text-slate-800">{detail.fakultas_mahasiswa}</span>
            </div>
          </div>
        </div>

        <div className="flex flex-col items-start md:items-end space-y-2.5">
          <StatusBadge status={detail.status} size="md" />

          {detail.nomor_surat_resmi && (
            <div className="text-xs font-mono font-bold text-slate-900 bg-slate-100 px-3 py-1 rounded-md border border-slate-200 shadow-2xs">
              No. Resmi: {detail.nomor_surat_resmi}
            </div>
          )}

          <button
            onClick={fetchDetail}
            className="inline-flex items-center text-xs font-semibold text-slate-600 hover:text-slate-900 transition ts-btn"
          >
            <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
            Segarkan Status
          </button>
        </div>
      </div>

      {/* 2. AGENTIC AI LEVEL 2 PIPELINE STEPPER */}
      <AgentPipelineStepper
        status={detail.status}
        critiqueScore={detail.self_critique_score}
        approvals={detail.approvals}
        nomorSurat={detail.nomor_surat_resmi}
      />

      {/* 3. ASYNCHRONOUS NOTIFICATION (SUBMITTED / APPROVED ISSUANCE) */}
      {detail.status === 'SUBMITTED' && (
        <div className="ts-card p-5 bg-blue-50/70 border-blue-200 flex items-start space-x-3.5 text-blue-950">
          <Clock className="w-5 h-5 shrink-0 text-blue-600 animate-spin mt-0.5" />
          <div className="space-y-1">
            <h4 className="font-bold text-sm">Agen AI Sedang Menyusun & Mengevaluasi Draf Surat</h4>
            <p className="text-xs text-blue-800 leading-relaxed">
              Model Gemini 3.1 Flash sedang menjalankan inferensi ekstraksi slot, validasi aturan akademik,
              dan loop refleksi mandiri di latar belakang. Halaman ini akan diperbarui secara otomatis.
            </p>
          </div>
        </div>
      )}

      {detail.status === 'APPROVED' && !detail.file_pdf_url && (
        <div className="ts-card p-5 bg-purple-50/70 border-purple-200 flex items-start space-x-3.5 text-purple-950">
          <Clock className="w-5 h-5 shrink-0 text-purple-600 animate-spin mt-0.5" />
          <div className="space-y-1">
            <h4 className="font-bold text-sm">Penerbitan Dokumen Resmi & TTE Sedang Berjalan</h4>
            <p className="text-xs text-purple-800 leading-relaxed">
              Persetujuan telah dikonfirmasi. Sistem sedang menerbitkan nomor surat resmi sekuensial,
              menghitung tanda tangan elektronik (TTE), merender dokumen PDF, dan mengunggah ke Cloudinary.
            </p>
          </div>
        </div>
      )}

      {/* 4. REVISION REQUIRED CALLOUT (SELF-REFLECTION AI GATE) */}
      {isRevisionNeeded && (
        <div className="ts-card p-6 bg-amber-50/70 border-amber-300 space-y-4">
          <div className="flex items-start space-x-3.5">
            <AlertTriangle className="w-6 h-6 text-amber-700 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <h3 className="text-sm font-bold uppercase tracking-wider text-amber-950">
                Informasi Tambahan Diperlukan (Self-Critique AI Gate)
              </h3>
              <p className="text-xs text-amber-800 leading-relaxed">
                Agen mendeteksi atribut dinas yang belum lengkap atau membutuhkan konfirmasi agar surat memenuhi standar penerbitan resmi:
              </p>
              {notesList.length > 0 && (
                <ul className="list-disc list-inside mt-2 space-y-1 text-xs text-amber-950 font-semibold font-mono">
                  {notesList.map((note, idx) => (
                    <li key={idx}>{note}</li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          {/* Form Re-draft */}
          <form onSubmit={handleRedraftSubmit} className="pt-4 border-t border-amber-200 space-y-3">
            {redraftError && (
              <div className="p-3 rounded-md bg-rose-100 text-rose-900 text-xs font-medium">
                {redraftError}
              </div>
            )}
            {redraftSuccess && (
              <div className="p-3 rounded-md bg-emerald-100 text-emerald-950 text-xs font-medium">
                {redraftSuccess}
              </div>
            )}

            <label
              htmlFor="additionalContext"
              className="block text-xs font-bold uppercase tracking-wider text-amber-950 font-sans"
            >
              Jawaban / Konfirmasi Informasi Tambahan Mahasiswa:
            </label>
            <textarea
              id="additionalContext"
              rows={3}
              value={additionalContext}
              onChange={(e) => setAdditionalContext(e.target.value)}
              placeholder="Contoh: Tanggal mulai magang adalah 2026-08-01 sampai 2026-11-30 pada divisi Backend Engineer..."
              className="block w-full p-3 text-xs sm:text-sm border border-amber-300 rounded-md bg-white focus:ring-1 focus:ring-amber-900 focus:border-amber-900 text-slate-900 leading-relaxed shadow-2xs"
            />
            <div className="flex justify-end">
              <button
                type="submit"
                disabled={isSubmittingRedraft || !additionalContext.trim()}
                className="inline-flex items-center px-5 py-2.5 text-xs font-bold text-white bg-amber-900 hover:bg-amber-800 disabled:opacity-50 rounded-md shadow-xs transition ts-btn"
              >
                {isSubmittingRedraft ? (
                  <span>Mengirim koreksi ke agen...</span>
                ) : (
                  <>
                    <Send className="w-4 h-4 mr-2" />
                    <span>Kirim Informasi Revisi (Re-Draft Loop)</span>
                  </>
                )}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* 5. INSPECTION STUDIO VIEWS (SHEET vs AUDIT vs PDF) */}
      <div className="space-y-4">
        {/* Workspace Mode Pills */}
        <div className="flex items-center justify-between border-b border-slate-200 pb-3">
          <div className="flex items-center space-x-2">
            <button
              onClick={() => setInspectorView('sheet')}
              className={`px-4 py-2 text-xs sm:text-sm font-bold rounded-lg transition ts-btn ${
                inspectorView === 'sheet'
                  ? 'bg-slate-900 text-white shadow-xs'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
              }`}
            >
              <FileText className="w-4 h-4 mr-2" />
              Lembar Surat Resmi (A4 Sheet)
            </button>
            {isApproverOrLecturer && (
              <button
                onClick={() => setInspectorView('audit')}
                className={`px-4 py-2 text-xs sm:text-sm font-bold rounded-lg transition ts-btn ${
                  inspectorView === 'audit'
                    ? 'bg-slate-900 text-white shadow-xs'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                }`}
              >
                <GitCompare className="w-4 h-4 mr-2" />
                Telemetri AI & Diff Naskah
              </button>
            )}
            {detail.file_pdf_url && (
              <button
                onClick={() => setInspectorView('pdf')}
                className={`px-4 py-2 text-xs sm:text-sm font-bold rounded-lg transition ts-btn ${
                  inspectorView === 'pdf'
                    ? 'bg-slate-900 text-white shadow-xs'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                }`}
              >
                <ShieldCheck className="w-4 h-4 mr-2 text-emerald-500" />
                Pratinjau PDF Asli & TTE
              </button>
            )}
          </div>

          <div className="text-xs font-mono text-slate-500 hidden sm:block">
            {detail.final_approved_content ? 'Status Naskah: Approved (Final)' : 'Status Naskah: AI Draft (Iterasi 1)'}
          </div>
        </div>

        {/* View Content */}
        {inspectorView === 'sheet' || (!isApproverOrLecturer && inspectorView === 'audit') ? (
          /* AUTHENTIC OFFICIAL LETTER A4 SHEET VIEW */
          <div className="bg-slate-100/70 p-6 sm:p-10 rounded-xl border border-slate-200 overflow-x-auto">
            <OfficialLetterSheet detail={detail} />
          </div>
        ) : inspectorView === 'audit' && isApproverOrLecturer ? (
          /* AI TELEMETRY, DIFF, AND APPROVAL HIERARCHY */
          <div className="space-y-6">
            {/* Phase 3 Diff Engine */}
            <DiffViewer
              originalDraft={detail.ai_original_draft}
              finalContent={detail.final_approved_content}
            />

            {/* Extracted Payload Attributes */}
            {detail.payload_data && Object.keys(detail.payload_data).length > 0 && (
              <div className="ts-card p-6 bg-white space-y-3">
                <div className="flex items-center space-x-2 text-xs font-bold uppercase tracking-wider text-slate-800">
                  <Layers className="w-4 h-4 text-blue-600" />
                  <span>Atribut Terekstraksi (Structured Payload):</span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {Object.entries(detail.payload_data).map(([key, val]) => (
                    <div key={key} className="p-3 rounded-lg bg-slate-50 border border-slate-200 text-xs">
                      <div className="text-[10px] text-slate-500 font-mono uppercase">{key}</div>
                      <div className="font-bold text-slate-900 truncate mt-1">
                        {val === null || val === undefined ? '-' : String(val)}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Approvals Timeline */}
            <div className="ts-card p-6 bg-white space-y-4">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800 flex items-center space-x-2">
                <CheckCircle2 className="w-4 h-4 text-slate-700" />
                <span>Hierarki & Riwayat Persetujuan Pejabat Kampus</span>
              </h3>

              <div className="space-y-3">
                {detail.approvals.map((app) => (
                  <div
                    key={app.id}
                    className="p-4 rounded-lg border border-slate-200 bg-slate-50/50 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 text-xs"
                  >
                    <div>
                      <div className="font-bold text-slate-900 text-sm">
                        Langkah {app.step_order}: {app.approver_name || 'Pejabat Berwenang'}
                      </div>
                      <div className="text-xs text-slate-500 font-mono mt-0.5">
                        NIP: {app.approver_nip || '-'}
                      </div>
                      {app.catatan && (
                        <div className="mt-2 p-2.5 bg-white rounded border border-slate-200 text-slate-700 italic">
                          Catatan: "{app.catatan}"
                        </div>
                      )}
                    </div>
                    <span
                      className={`px-3 py-1 rounded-md text-xs font-bold uppercase shrink-0 ${
                        app.status === 'APPROVED'
                          ? 'bg-emerald-100 text-emerald-800'
                          : app.status === 'REJECTED'
                          ? 'bg-rose-100 text-rose-800'
                          : 'bg-blue-100 text-blue-800'
                      }`}
                    >
                      {app.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Audit Logs */}
            <div className="ts-card p-6 bg-white space-y-3">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800 flex items-center space-x-2">
                <FileCode className="w-4 h-4 text-slate-700" />
                <span>Log Audit Sistem Agentic AI</span>
              </h3>
              <div className="space-y-2 max-h-56 overflow-y-auto">
                {detail.audit_logs.map((log) => (
                  <div
                    key={log.id}
                    className="p-2.5 rounded bg-slate-50 border border-slate-200 text-xs flex items-center justify-between"
                  >
                    <div>
                      <span className="font-mono font-bold text-slate-700 mr-2">
                        [{log.action_id}]
                      </span>
                      <span className="text-slate-800">{log.action}</span>
                    </div>
                    <span className="text-[11px] text-slate-400 font-mono">
                      {new Date(log.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : (
          /* PDF & DIGITAL EVIDENCE VIEW */
          <div className="space-y-6">
            <PDFViewer
              pdfUrl={detail.file_pdf_url}
              nomorSurat={detail.nomor_surat_resmi}
              documentTitle={detail.nama_surat}
              requestId={detail.id}
            />
          </div>
        )}
      </div>
    </div>
  );
};

export default SuratDetailPage;
