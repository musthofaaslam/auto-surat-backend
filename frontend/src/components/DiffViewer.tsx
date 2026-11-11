import React, { useState } from 'react';
import { GitCompare, CheckCircle2, Split, Eye } from 'lucide-react';

interface DiffViewerProps {
  originalDraft: string | null;
  finalContent: string | null;
  title?: string;
}

// Architectural Note:
// Visualizes the Agentic AI Level 2 Fase 3 Memory Loop. Shows human-in-the-loop edits
// made by academic approvers against the AI's initial draft.

export const DiffViewer: React.FC<DiffViewerProps> = ({
  originalDraft,
  finalContent,
  title = 'Komparasi Draf AI vs Naskah Disetujui Dosen',
}) => {
  const [viewMode, setViewMode] = useState<'split' | 'unified'>('split');

  const original = (originalDraft || '').trim();
  const final = (finalContent || '').trim();

  // If final is missing or matches original, no diff needed
  const isIdentical = original === final || !final;

  if (isIdentical) {
    return (
      <div className="bg-white border border-slate-200 rounded-lg p-5 shadow-xs space-y-3">
        <div className="flex items-center justify-between pb-3 border-b border-slate-100">
          <div className="flex items-center space-x-2">
            <GitCompare className="w-4 h-4 text-slate-700" />
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900">
              {title}
            </h3>
          </div>
          <span className="inline-flex items-center text-[11px] font-medium text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
            <CheckCircle2 className="w-3 h-3 mr-1" />
            Disetujui Tanpa Perubahan
          </span>
        </div>

        <p className="text-xs text-slate-500 leading-relaxed">
          Pejabat berwenang menyetujui seluruh tata bahasa draf awal yang disusun oleh agen AI tanpa koreksi redaksional.
        </p>

        <div className="bg-slate-50 border border-slate-200 rounded p-3.5 font-mono text-xs text-slate-800 whitespace-pre-wrap leading-relaxed max-h-72 overflow-y-auto">
          {final || original || 'Belum ada naskah draf.'}
        </div>
      </div>
    );
  }

  // Split lines for basic comparison
  const origLines = original.split('\n');
  const finalLines = final.split('\n');
  const maxLines = Math.max(origLines.length, finalLines.length);

  return (
    <div className="bg-white border border-slate-200 rounded-lg p-5 shadow-xs space-y-4">
      {/* Header with Mode Toggle */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-3 border-b border-slate-100 gap-2">
        <div className="flex items-center space-x-2">
          <GitCompare className="w-4 h-4 text-blue-600" />
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900">
            {title}
          </h3>
        </div>

        <div className="flex items-center space-x-2">
          <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-blue-50 text-blue-800 border border-blue-200">
            Memory Feedback Loop Aktif
          </span>
          <div className="inline-flex rounded border border-slate-200 p-0.5 bg-slate-50 text-xs">
            <button
              onClick={() => setViewMode('split')}
              className={`px-2 py-0.5 rounded font-medium transition ${
                viewMode === 'split'
                  ? 'bg-white text-slate-900 shadow-2xs font-semibold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <Split className="w-3 h-3 inline mr-1" />
              Berdampingan
            </button>
            <button
              onClick={() => setViewMode('unified')}
              className={`px-2 py-0.5 rounded font-medium transition ${
                viewMode === 'unified'
                  ? 'bg-white text-slate-900 shadow-2xs font-semibold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <Eye className="w-3 h-3 inline mr-1" />
              Satu Kolom
            </button>
          </div>
        </div>
      </div>

      <p className="text-xs text-slate-500">
        Perbedaan antara draf awal AI dan perbaikan pejabat akademik. Pola perubahan ini disaring anti-PII dan disimpan ke <code className="text-slate-800 font-semibold">AgentFeedbackMemory</code> untuk menyelaraskan gaya bahasa generasi berikutnya.
      </p>

      {viewMode === 'split' ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs font-mono">
          {/* Left: Original AI Draft */}
          <div className="space-y-1">
            <div className="text-[11px] font-semibold text-rose-800 bg-rose-50 px-2.5 py-1 rounded border border-rose-200">
              Draf Awal AI (Sebelum Koreksi)
            </div>
            <div className="bg-rose-50/30 border border-rose-200/80 rounded p-3 text-slate-800 whitespace-pre-wrap leading-relaxed max-h-80 overflow-y-auto">
              {origLines.map((line, idx) => {
                const isDifferent = line !== finalLines[idx];
                return (
                  <div
                    key={idx}
                    className={`py-0.5 ${
                      isDifferent ? 'bg-rose-100/70 text-rose-900 line-through' : ''
                    }`}
                  >
                    {line || '\u00A0'}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Right: Final Approved Content */}
          <div className="space-y-1">
            <div className="text-[11px] font-semibold text-emerald-800 bg-emerald-50 px-2.5 py-1 rounded border border-emerald-200">
              Naskah Disetujui Dosen (Final)
            </div>
            <div className="bg-emerald-50/30 border border-emerald-200/80 rounded p-3 text-slate-800 whitespace-pre-wrap leading-relaxed max-h-80 overflow-y-auto">
              {finalLines.map((line, idx) => {
                const isDifferent = line !== origLines[idx];
                return (
                  <div
                    key={idx}
                    className={`py-0.5 ${
                      isDifferent ? 'bg-emerald-100/80 text-emerald-950 font-medium' : ''
                    }`}
                  >
                    {line || '\u00A0'}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      ) : (
        /* Unified View */
        <div className="bg-slate-50 border border-slate-200 rounded p-3 text-xs font-mono max-h-80 overflow-y-auto space-y-1">
          {Array.from({ length: maxLines }).map((_, idx) => {
            const oLine = origLines[idx];
            const fLine = finalLines[idx];

            if (oLine === fLine) {
              return (
                <div key={idx} className="text-slate-700 py-0.5">
                  &nbsp;&nbsp;{oLine || '\u00A0'}
                </div>
              );
            }

            return (
              <React.Fragment key={idx}>
                {oLine !== undefined && (
                  <div className="bg-rose-50 text-rose-800 px-1 py-0.5 border-l-2 border-rose-500 line-through">
                    - {oLine || '\u00A0'}
                  </div>
                )}
                {fLine !== undefined && (
                  <div className="bg-emerald-50 text-emerald-900 px-1 py-0.5 border-l-2 border-emerald-500 font-medium">
                    + {fLine || '\u00A0'}
                  </div>
                )}
              </React.Fragment>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default DiffViewer;
