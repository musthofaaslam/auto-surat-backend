import React, { useState, useEffect } from 'react';
import suratService from '../services/suratService';
import type { SuratRequestListItem, SuratRequestDetail } from '../types';
import StatusBadge from '../components/StatusBadge';
import PDFViewer from '../components/PDFViewer';
import DiffViewer from '../components/DiffViewer';
import OfficialLetterSheet from '../components/OfficialLetterSheet';
import {
  CheckSquare,
  Check,
  X,
  AlertCircle,
  RefreshCw,
  Sparkles,
  Edit3,
  Clock,
  Eye,
  FileText,
  ShieldCheck,
  Send,
  Layers,
} from 'lucide-react';

// Architectural Note (Taste-Skill 2.5 - Document Review Studio):
// Executive workspace for Lecturers and Deans. Integrates live authentic A4 document preview,
// inline text refinement, Phase 3 Diff Comparator, and single-click TTE publication.

export const ApprovalQueuePage: React.FC = () => {
  const [requests, setRequests] = useState<SuratRequestListItem[]>([]);
  const [selectedRequestId, setSelectedRequestId] = useState<number | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<SuratRequestDetail | null>(null);

  const [isLoadingList, setIsLoadingList] = useState(true);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [isProcessingAction, setIsProcessingAction] = useState(false);

  // Approval Form State
  const [editedContent, setEditedContent] = useState<string>('');
  const [approvalNote, setApprovalNote] = useState<string>('');
  const [finalStatus, setFinalStatus] = useState<'SENT' | 'PRINTED'>('PRINTED');
  const [viewMode, setViewMode] = useState<'sheet' | 'diff' | 'editor'>('sheet');

  // Reject Modal State
  const [showRejectModal, setShowRejectModal] = useState<boolean>(false);
  const [rejectionReason, setRejectionReason] = useState<string>('');

  const [actionSuccessMsg, setActionSuccessMsg] = useState<string | null>(null);
  const [actionErrorMsg, setActionErrorMsg] = useState<string | null>(null);

  const fetchQueue = async () => {
    setIsLoadingList(true);
    try {
      const data = await suratService.getSuratRequests();
      setRequests(data);
      if (!selectedRequestId && data.length > 0) {
        const firstPending =
          data.find(
            (r) => r.status === 'PENDING_APPROVAL' || r.status === 'IN_REVIEW'
          ) || data[0];
        setSelectedRequestId(firstPending.id);
      }
    } catch {
      setActionErrorMsg('Gagal memuat antrean persetujuan dari server.');
    } finally {
      setIsLoadingList(false);
    }
  };

  useEffect(() => {
    fetchQueue();
  }, []);

  useEffect(() => {
    if (!selectedRequestId) return;
    const loadDetail = async () => {
      setIsLoadingDetail(true);
      try {
        const detail = await suratService.getSuratRequestDetail(selectedRequestId);
        setSelectedDetail(detail);
        setEditedContent(detail.final_approved_content || detail.ai_original_draft || '');
        setApprovalNote('');
        setActionSuccessMsg(null);
        setActionErrorMsg(null);
      } catch {
        setActionErrorMsg('Gagal memuat detail permohonan surat.');
      } finally {
        setIsLoadingDetail(false);
      }
    };

    loadDetail();
  }, [selectedRequestId]);

  const currentPendingApproval =
    selectedDetail?.approvals.find((app) => app.status === 'PENDING') ||
    selectedDetail?.approvals[0];

  const handleApprove = async () => {
    if (!currentPendingApproval) {
      setActionErrorMsg('Langkah antrean persetujuan (approval_id) tidak ditemukan.');
      return;
    }

    setIsProcessingAction(true);
    setActionErrorMsg(null);
    setActionSuccessMsg(null);

    try {
      const result = await suratService.submitApprovalAction(currentPendingApproval.id, {
        action: 'APPROVE',
        catatan: approvalNote,
        final_approved_content: editedContent,
        final_status: finalStatus,
      });

      setActionSuccessMsg(result.message || 'Surat resmi berhasil disetujui dan diterbitkan.');
      setTimeout(() => {
        fetchQueue();
        if (selectedRequestId) {
          suratService.getSuratRequestDetail(selectedRequestId).then(setSelectedDetail);
        }
      }, 1000);
    } catch (err: any) {
      setActionErrorMsg(
        err.response?.data?.error ||
          err.response?.data?.message ||
          'Gagal memproses persetujuan surat.'
      );
    } finally {
      setIsProcessingAction(false);
    }
  };

  const handleReject = async () => {
    if (!currentPendingApproval) {
      setActionErrorMsg('Langkah antrean persetujuan tidak ditemukan.');
      return;
    }
    if (!rejectionReason.trim()) {
      setActionErrorMsg('Alasan penolakan wajib diisi.');
      return;
    }

    setIsProcessingAction(true);
    setActionErrorMsg(null);
    setActionSuccessMsg(null);

    try {
      const result = await suratService.submitApprovalAction(currentPendingApproval.id, {
        action: 'REJECT',
        alasan_penolakan: rejectionReason.trim(),
      });

      setActionSuccessMsg(result.message || 'Permohonan surat berhasil ditolak.');
      setShowRejectModal(false);
      setRejectionReason('');
      setTimeout(() => {
        fetchQueue();
        if (selectedRequestId) {
          suratService.getSuratRequestDetail(selectedRequestId).then(setSelectedDetail);
        }
      }, 1000);
    } catch (err: any) {
      setActionErrorMsg(
        err.response?.data?.error ||
          err.response?.data?.message ||
          'Gagal menolak permohonan surat.'
      );
    } finally {
      setIsProcessingAction(false);
    }
  };

  // Keyboard shortcut listener
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        if (!showRejectModal && !isProcessingAction && currentPendingApproval?.status === 'PENDING') {
          e.preventDefault();
          handleApprove();
        }
      }
      if (e.key === 'Escape' && showRejectModal) {
        setShowRejectModal(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [showRejectModal, isProcessingAction, currentPendingApproval, editedContent, approvalNote, finalStatus]);

  const pendingCount = requests.filter(
    (r) => r.status === 'PENDING_APPROVAL' || r.status === 'IN_REVIEW'
  ).length;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8">
      {/* 1. HEADER COCKPIT */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-4 border-b border-slate-200 gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight flex items-center space-x-2.5">
            <CheckSquare className="w-7 h-7 text-slate-800" />
            <span>Meja Tinjauan & Persetujuan Naskah Dinas</span>
          </h1>
          <p className="text-sm text-slate-600 mt-1 leading-relaxed">
            Periksa draf buatan agen AI, lakukan penyuntingan redaksional, dan terbitkan Tanda Tangan Elektronik (TTE) resmi.
          </p>
        </div>

        <button
          onClick={fetchQueue}
          disabled={isLoadingList}
          className="h-10 px-4 text-xs font-semibold text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 shadow-2xs transition ts-btn"
        >
          <RefreshCw className={`w-3.5 h-3.5 mr-2 ${isLoadingList ? 'animate-spin' : ''}`} />
          Segarkan Antrean ({requests.length})
        </button>
      </div>

      {actionSuccessMsg && (
        <div className="p-4 rounded-lg bg-emerald-50 border border-emerald-200 text-xs sm:text-sm text-emerald-950 flex items-center justify-between shadow-xs">
          <span className="font-semibold">{actionSuccessMsg}</span>
          <button onClick={() => setActionSuccessMsg(null)} className="ts-btn">
            <X className="w-4 h-4 text-emerald-700" />
          </button>
        </div>
      )}

      {actionErrorMsg && (
        <div className="p-4 rounded-lg bg-rose-50 border border-rose-200 text-xs sm:text-sm text-rose-950 flex items-center justify-between shadow-xs">
          <div className="flex items-center space-x-2">
            <AlertCircle className="w-5 h-5 text-rose-700 shrink-0" />
            <span className="font-semibold">{actionErrorMsg}</span>
          </div>
          <button onClick={() => setActionErrorMsg(null)} className="ts-btn">
            <X className="w-4 h-4 text-rose-700" />
          </button>
        </div>
      )}

      {/* 2. WORKSPACE GRID: DOSSIER LIST (4 cols) & REVIEW STUDIO (8 cols) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Left: Dossier List */}
        <div className="lg:col-span-4 ts-card bg-white overflow-hidden flex flex-col h-[840px]">
          <div className="p-4 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-800">
              Antrean Berkas ({requests.length})
            </span>
            <span className="text-xs font-mono font-semibold text-blue-700 bg-blue-50 px-2 py-0.5 rounded border border-blue-200">
              {pendingCount} Menunggu Keputusan
            </span>
          </div>

          <div className="flex-1 overflow-y-auto divide-y divide-slate-100">
            {isLoadingList ? (
              <div className="p-12 text-center text-slate-400 text-xs space-y-2">
                <RefreshCw className="w-6 h-6 animate-spin mx-auto text-slate-400" />
                <span>Memuat antrean berkas...</span>
              </div>
            ) : requests.length === 0 ? (
              <div className="p-12 text-center text-slate-400 text-xs">
                Tidak ada permohonan surat dalam antrean saat ini.
              </div>
            ) : (
              requests.map((item) => {
                const isSelected = item.id === selectedRequestId;
                return (
                  <div
                    key={item.id}
                    onClick={() => setSelectedRequestId(item.id)}
                    className={`p-4 cursor-pointer transition text-xs ${
                      isSelected
                        ? 'bg-slate-100/90 border-l-4 border-slate-900 shadow-2xs'
                        : 'hover:bg-slate-50'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-slate-500 font-bold">#{item.id}</span>
                      <StatusBadge status={item.status} size="xs" />
                    </div>
                    <div className="font-bold text-slate-900 text-sm mt-1.5 truncate">
                      {item.nama_surat}
                    </div>
                    <div className="flex items-center justify-between text-xs text-slate-500 mt-1 font-medium">
                      <span>{item.nama_mahasiswa}</span>
                      <span className="font-mono">{item.nim_mahasiswa}</span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right: Review Studio & Authentic Sheet Preview */}
        <div className="lg:col-span-8 space-y-6">
          {isLoadingDetail ? (
            <div className="ts-card bg-white p-16 text-center text-slate-400 h-[840px] flex flex-col items-center justify-center space-y-3">
              <RefreshCw className="w-8 h-8 animate-spin" />
              <span className="text-sm font-semibold">Memuat berkas permohonan...</span>
            </div>
          ) : selectedDetail ? (
            <div className="space-y-6">
              {/* Document Metadata Strip */}
              <div className="ts-card p-6 bg-white flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                <div>
                  <div className="flex items-center space-x-2 text-xs font-mono text-slate-500">
                    <span className="font-bold text-slate-800">Berkas #{selectedDetail.id}</span>
                    <span>•</span>
                    <span className="text-blue-700 font-bold">[{selectedDetail.kode_surat}]</span>
                  </div>
                  <h2 className="text-xl font-extrabold text-slate-900 tracking-tight mt-1">
                    {selectedDetail.nama_surat}
                  </h2>
                  <p className="text-xs text-slate-600 mt-1">
                    Pemohon: <strong>{selectedDetail.nama_mahasiswa}</strong> ({selectedDetail.nim_mahasiswa}) • {selectedDetail.prodi_mahasiswa}
                  </p>
                </div>

                <div className="flex flex-col items-start sm:items-end space-y-2">
                  <StatusBadge status={selectedDetail.status} size="md" />
                  {selectedDetail.self_critique_score !== null && (
                    <span className="text-xs font-mono font-bold text-slate-700 bg-slate-100 px-2.5 py-0.5 rounded border border-slate-200">
                      Skor Evaluasi AI: {selectedDetail.self_critique_score}/10
                    </span>
                  )}
                </div>
              </div>

              {/* View Mode Toggle: Sheet vs Live Editor vs Diff */}
              <div className="flex items-center justify-between border-b border-slate-200 pb-3">
                <div className="flex items-center space-x-2">
                  <button
                    onClick={() => setViewMode('sheet')}
                    className={`px-3.5 py-1.5 text-xs font-bold rounded-md transition ts-btn ${
                      viewMode === 'sheet'
                        ? 'bg-slate-900 text-white shadow-xs'
                        : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                    }`}
                  >
                    <FileText className="w-3.5 h-3.5 mr-1.5" />
                    Lembar Surat Resmi (A4)
                  </button>
                  <button
                    onClick={() => setViewMode('editor')}
                    className={`px-3.5 py-1.5 text-xs font-bold rounded-md transition ts-btn ${
                      viewMode === 'editor'
                        ? 'bg-slate-900 text-white shadow-xs'
                        : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                    }`}
                  >
                    <Edit3 className="w-3.5 h-3.5 mr-1.5" />
                    Penyunting Naskah Dinas
                  </button>
                  <button
                    onClick={() => setViewMode('diff')}
                    className={`px-3.5 py-1.5 text-xs font-bold rounded-md transition ts-btn ${
                      viewMode === 'diff'
                        ? 'bg-slate-900 text-white shadow-xs'
                        : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                    }`}
                  >
                    <Sparkles className="w-3.5 h-3.5 mr-1.5 text-amber-500" />
                    Live Diff AI vs Koreksi
                  </button>
                </div>

                <span className="text-xs text-slate-400 font-mono hidden sm:inline">
                  Pintasan: <kbd className="bg-slate-100 border border-slate-200 px-1 rounded">Ctrl</kbd> + <kbd className="bg-slate-100 border border-slate-200 px-1 rounded">Enter</kbd> (Setujui)
                </span>
              </div>

              {/* View Content */}
              {viewMode === 'sheet' ? (
                /* AUTHENTIC OFFICIAL LETTER A4 SHEET PREVIEW */
                <div className="bg-slate-100/70 p-6 sm:p-10 rounded-xl border border-slate-200 overflow-x-auto">
                  <OfficialLetterSheet
                    detail={selectedDetail}
                    contentOverride={editedContent}
                    isEditable={false}
                  />
                </div>
              ) : viewMode === 'editor' ? (
                /* INLINE EDITING STUDIO */
                <div className="ts-card p-6 bg-white space-y-4">
                  <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                    <h3 className="text-sm font-bold uppercase tracking-wider text-slate-900 flex items-center space-x-2">
                      <Edit3 className="w-4 h-4 text-blue-600" />
                      <span>Sunting Isi Naskah Surat Dinas</span>
                    </h3>
                  </div>
                  <p className="text-xs text-slate-500 leading-relaxed">
                    Ubah tata bahasa draf AI bila diperlukan. Hasil suntingan Anda akan diabadikan di <code className="font-semibold text-slate-800">AgentFeedbackMemory</code> untuk menyelaraskan preferensi gaya surat berikutnya.
                  </p>
                  <textarea
                    rows={12}
                    value={editedContent}
                    onChange={(e) => setEditedContent(e.target.value)}
                    className="w-full p-4 font-serif text-sm border border-slate-300 rounded-md bg-white focus:ring-1 focus:ring-slate-900 leading-relaxed text-slate-900 shadow-2xs"
                  />
                </div>
              ) : (
                /* LIVE DIFF VIEW */
                <DiffViewer
                  originalDraft={selectedDetail.ai_original_draft}
                  finalContent={editedContent}
                  title="Live Diff: Perubahan Naskah dari Draf Asli AI"
                />
              )}

              {/* Decision & Action Bar */}
              <div className="ts-card p-6 bg-white space-y-5">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800 border-b border-slate-100 pb-2">
                  Keputusan & Tindakan Pejabat Penandatangan
                </h3>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label
                      htmlFor="approvalNote"
                      className="block text-xs font-semibold text-slate-700 mb-1"
                    >
                      Catatan Keputusan (Opsional)
                    </label>
                    <input
                      type="text"
                      id="approvalNote"
                      value={approvalNote}
                      onChange={(e) => setApprovalNote(e.target.value)}
                      placeholder="Contoh: Disetujui untuk persyaratan magang industri..."
                      className="block w-full px-3.5 py-2 text-xs border border-slate-300 rounded-md bg-white focus:ring-1 focus:ring-slate-900"
                    />
                  </div>

                  <div>
                    <label
                      htmlFor="finalStatus"
                      className="block text-xs font-semibold text-slate-700 mb-1"
                    >
                      Kanal Penerbitan Pasca Persetujuan
                    </label>
                    <select
                      id="finalStatus"
                      value={finalStatus}
                      onChange={(e) => setFinalStatus(e.target.value as 'SENT' | 'PRINTED')}
                      className="block w-full px-3.5 py-2 text-xs border border-slate-300 rounded-md bg-white focus:ring-1 focus:ring-slate-900 font-medium"
                    >
                      <option value="PRINTED">Terbitkan & Arsipkan untuk Cetak Fisik (PRINTED)</option>
                      <option value="SENT">Terbitkan & Kirim Otomatis via Email/Telegram (SENT)</option>
                    </select>
                  </div>
                </div>

                <div className="flex items-center justify-end space-x-3 pt-3 border-t border-slate-100">
                  <button
                    type="button"
                    onClick={() => setShowRejectModal(true)}
                    disabled={isProcessingAction}
                    className="h-10 px-5 text-xs font-bold text-rose-700 bg-rose-50 hover:bg-rose-100 border border-rose-300 rounded-lg transition ts-btn"
                  >
                    <X className="w-4 h-4 mr-1.5" />
                    <span>Tolak Permohonan</span>
                  </button>

                  <button
                    type="button"
                    onClick={handleApprove}
                    disabled={isProcessingAction}
                    className="h-10 px-6 text-xs font-bold text-white bg-slate-900 hover:bg-slate-800 disabled:opacity-50 rounded-lg shadow-xs transition ts-btn"
                  >
                    {isProcessingAction ? (
                      <span>Memproses Penerbitan TTE...</span>
                    ) : (
                      <>
                        <Check className="w-4 h-4 mr-1.5" />
                        <span>Setujui & Terbitkan Surat (TTE)</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className="ts-card bg-white p-16 text-center text-slate-400 text-sm">
              Pilih permohonan surat dari antrean di sebelah kiri untuk memulai peninjauan naskah dinas.
            </div>
          )}
        </div>
      </div>

      {/* Rejection Modal */}
      {showRejectModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4">
          <div className="bg-white rounded-xl border border-slate-200 max-w-md w-full p-6 space-y-4 shadow-xl ts-card">
            <div className="flex items-center space-x-2 text-rose-600">
              <AlertCircle className="w-6 h-6" />
              <h3 className="text-base font-bold text-slate-900">Alasan Penolakan Permohonan</h3>
            </div>

            <p className="text-xs text-slate-600 leading-relaxed">
              Jelaskan alasan penolakan secara lugas. Alasan ini akan dikirimkan kepada mahasiswa pemohon dan tercatat di audit log.
            </p>

            <textarea
              rows={4}
              value={rejectionReason}
              onChange={(e) => setRejectionReason(e.target.value)}
              placeholder="Contoh: Berkas lampiran LoA tidak memuat tanda tangan pimpinan instansi..."
              className="block w-full p-3 text-xs border border-slate-300 rounded-md focus:ring-1 focus:ring-slate-900"
            />

            <div className="flex items-center justify-end space-x-3 pt-2">
              <button
                type="button"
                onClick={() => setShowRejectModal(false)}
                className="px-4 py-2 text-xs font-semibold text-slate-700 bg-white border border-slate-300 hover:bg-slate-50 rounded-md transition ts-btn"
              >
                Batal
              </button>
              <button
                type="button"
                onClick={handleReject}
                disabled={isProcessingAction || !rejectionReason.trim()}
                className="px-5 py-2 text-xs font-bold text-white bg-rose-600 hover:bg-rose-500 disabled:opacity-50 rounded-md shadow-xs transition ts-btn"
              >
                {isProcessingAction ? 'Menyimpan...' : 'Konfirmasi Tolak'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ApprovalQueuePage;
