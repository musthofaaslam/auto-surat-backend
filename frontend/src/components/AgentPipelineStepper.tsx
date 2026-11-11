import React from 'react';
import type { SuratStatusCode, SuratApproval } from '../types';
import { ShieldCheck, CheckCircle2, Clock, AlertTriangle, FileText, Send, XCircle } from 'lucide-react';

interface AgentPipelineStepperProps {
  status: SuratStatusCode;
  critiqueScore?: number | null;
  approvals?: SuratApproval[];
  nomorSurat?: string | null;
}

// Architectural Note:
// Visualizes the Agentic AI Level 2 Human-in-the-Loop lifecycle as a clean,
// high-density technical pipeline without generic cartoon cards or clutter.

export const AgentPipelineStepper: React.FC<AgentPipelineStepperProps> = ({
  status,
  critiqueScore,
  approvals = [],
  nomorSurat,
}) => {
  // Determine current active or completed stage
  const isStage1Complete = status !== 'SUBMITTED';
  const isStage2Active = status === 'SUBMITTED' || status === 'REVISION_REQUIRED';
  const isStage2Passed =
    status !== 'SUBMITTED' && status !== 'REVISION_REQUIRED' && status !== 'FAILED';

  const isStage3Active = status === 'PENDING_APPROVAL' || status === 'IN_REVIEW';
  const isStage3Passed =
    status === 'APPROVED' ||
    status === 'SENT' ||
    status === 'PRINTED';

  const isStage4Active = status === 'APPROVED';
  const isStage4Complete = status === 'SENT' || status === 'PRINTED';

  const isRejected = status === 'REJECTED';
  const isFailed = status === 'FAILED';

  return (
    <div className="bg-white border border-slate-200 rounded-lg p-5 shadow-xs">
      <div className="flex items-center justify-between pb-3.5 mb-4 border-b border-slate-100">
        <div className="flex items-center space-x-2">
          <div className="w-5 h-5 rounded bg-slate-900 text-white flex items-center justify-center">
            <FileText className="w-3 h-3 text-slate-200" />
          </div>
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-900">
            Tahapan Permohonan Surat
          </h2>
        </div>
        <div className="text-[11px] font-mono text-slate-500">
          Tahap: <span className="font-semibold text-slate-800">{status}</span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        {/* Step 1: Ekstraksi Slot */}
        <div
          className={`p-3 rounded-md border text-xs transition-all ${
            isStage1Complete
              ? 'border-emerald-200 bg-emerald-50/30 text-emerald-950'
              : 'border-blue-200 bg-blue-50/40 text-blue-950 animate-pulse'
          }`}
        >
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[10px] font-mono uppercase tracking-wider font-semibold text-slate-500">
              Tahap 1
            </span>
            {isStage1Complete ? (
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
            ) : (
              <Clock className="w-3.5 h-3.5 text-blue-600 animate-spin shrink-0" />
            )}
          </div>
          <div className="font-semibold text-slate-900 leading-snug">
            Ekstraksi Slot & Multimodal
          </div>
          <div className="text-[11px] text-slate-500 mt-1 leading-relaxed">
            {isStage1Complete
              ? 'Atribut surat diekstrak & disintesis dari konteks pengajuan.'
              : 'Agen sedang mengekstrak entitas & dokumen lampiran.'}
          </div>
        </div>

        {/* Step 2: Self-Reflection Gate */}
        <div
          className={`p-3 rounded-md border text-xs transition-all ${
            status === 'REVISION_REQUIRED'
              ? 'border-amber-300 bg-amber-50/60 text-amber-950'
              : isStage2Passed
              ? 'border-emerald-200 bg-emerald-50/30 text-emerald-950'
              : isStage2Active
              ? 'border-slate-200 bg-slate-50 text-slate-600'
              : 'border-slate-200 bg-slate-50 text-slate-500'
          }`}
        >
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[10px] font-mono uppercase tracking-wider font-semibold text-slate-500">
              Tahap 2
            </span>
            {status === 'REVISION_REQUIRED' ? (
              <AlertTriangle className="w-3.5 h-3.5 text-amber-600 shrink-0" />
            ) : isStage2Passed ? (
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
            ) : (
              <Clock className="w-3.5 h-3.5 text-slate-400 shrink-0" />
            )}
          </div>
          <div className="font-semibold text-slate-900 leading-snug">
            Evaluasi Mandiri AI
          </div>
          <div className="text-[11px] text-slate-500 mt-1 leading-relaxed">
            {critiqueScore !== null && critiqueScore !== undefined ? (
              <span className="font-mono font-medium text-slate-800">
                Skor AI: {critiqueScore}/10{' '}
                {critiqueScore >= 8 ? '(Lolos Kualitas)' : '(Perlu Koreksi)'}
              </span>
            ) : (
              'Analisis integritas akademik & kelengkapan tata naskah.'
            )}
          </div>
        </div>

        {/* Step 3: Human-in-the-Loop Review */}
        <div
          className={`p-3 rounded-md border text-xs transition-all ${
            isRejected
              ? 'border-rose-200 bg-rose-50/50 text-rose-950'
              : isStage3Passed
              ? 'border-emerald-200 bg-emerald-50/30 text-emerald-950'
              : isStage3Active
              ? 'border-blue-200 bg-blue-50/40 text-blue-950'
              : 'border-slate-200 bg-slate-50 text-slate-500'
          }`}
        >
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[10px] font-mono uppercase tracking-wider font-semibold text-slate-500">
              Tahap 3
            </span>
            {isRejected ? (
              <XCircle className="w-3.5 h-3.5 text-rose-600 shrink-0" />
            ) : isStage3Passed ? (
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
            ) : isStage3Active ? (
              <Clock className="w-3.5 h-3.5 text-blue-600 animate-pulse shrink-0" />
            ) : (
              <ShieldCheck className="w-3.5 h-3.5 text-slate-400 shrink-0" />
            )}
          </div>
          <div className="font-semibold text-slate-900 leading-snug">
            Supervisi Pejabat Kampus
          </div>
          <div className="text-[11px] text-slate-500 mt-1 leading-relaxed">
            {approvals.length > 0 ? (
              <span>
                {approvals.filter((a) => a.status === 'APPROVED').length} dari{' '}
                {approvals.length} pejabat menyetujui.
              </span>
            ) : (
              'Antrean hierarkis (DPA / Kaprodi / Dekan).'
            )}
          </div>
        </div>

        {/* Step 4: TTE & Distribution */}
        <div
          className={`p-3 rounded-md border text-xs transition-all ${
            isFailed
              ? 'border-red-200 bg-red-50/50 text-red-950'
              : isStage4Complete
              ? 'border-emerald-200 bg-emerald-50/30 text-emerald-950'
              : isStage4Active
              ? 'border-purple-200 bg-purple-50/50 text-purple-950 animate-pulse'
              : 'border-slate-200 bg-slate-50 text-slate-500'
          }`}
        >
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[10px] font-mono uppercase tracking-wider font-semibold text-slate-500">
              Tahap 4
            </span>
            {isStage4Complete ? (
              <Send className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
            ) : isStage4Active ? (
              <Clock className="w-3.5 h-3.5 text-purple-600 animate-spin shrink-0" />
            ) : (
              <FileText className="w-3.5 h-3.5 text-slate-400 shrink-0" />
            )}
          </div>
          <div className="font-semibold text-slate-900 leading-snug">
            Penerbitan TTE & PDF
          </div>
          <div className="text-[11px] text-slate-500 mt-1 leading-relaxed truncate">
            {nomorSurat ? (
              <span className="font-mono font-medium text-slate-800">
                {nomorSurat}
              </span>
            ) : isStage4Active ? (
              'Menghitung hash SHA-256 & QR TTE...'
            ) : (
              'Penomoran resmi dinas & tanda tangan digital.'
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default AgentPipelineStepper;
