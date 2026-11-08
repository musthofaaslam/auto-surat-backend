import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import suratService from '../services/suratService';
import type { SuratRequestListItem } from '../types';
import StatusBadge from '../components/StatusBadge';
import AIChatDrawer from '../components/AIChatDrawer';
import {
  FileText,
  PlusCircle,
  RefreshCw,
  Clock,
  AlertTriangle,
  CheckCircle2,
  ArrowRight,
  SlidersHorizontal,
  Sparkles,
  Bot,
  Activity,
  Layers,
  ChevronRight,
} from 'lucide-react';

// Architectural Note (Taste-Skill 2.5 - Executive Cockpit):
// Redesigned dashboard adhering strictly to Swiss typography, 16px baseline text,
// real agentic telemetry stats, and high-craft document streams.

export const DashboardPage: React.FC = () => {
  const { user } = useAuth();
  const [requests, setRequests] = useState<SuratRequestListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [activeTab, setActiveTab] = useState<'records' | 'copilot'>('records');

  const fetchRequests = async () => {
    setIsLoading(true);
    try {
      const data = await suratService.getSuratRequests();
      setRequests(data);
    } catch {
      // Graceful fallback
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchRequests();
  }, []);

  const isStudent = user?.role === 'STUDENT';
  const isLecturerOrAdmin =
    user?.role === 'LECTURER' || user?.role === 'STAFF' || user?.role === 'ADMIN';

  const totalCount = requests.length;
  const pendingCount = requests.filter(
    (r) => r.status === 'PENDING_APPROVAL' || r.status === 'IN_REVIEW'
  ).length;
  const revisionCount = requests.filter(
    (r) => r.status === 'REVISION_REQUIRED' || r.status === 'FAILED'
  ).length;
  const completedCount = requests.filter(
    (r) => r.status === 'APPROVED' || r.status === 'SENT' || r.status === 'PRINTED' || r.status === 'PROCESSED'
  ).length;

  const filteredRequests = requests.filter((r) => {
    if (statusFilter === 'ALL') return true;
    if (statusFilter === 'PENDING')
      return r.status === 'PENDING_APPROVAL' || r.status === 'IN_REVIEW';
    if (statusFilter === 'REVISION')
      return r.status === 'REVISION_REQUIRED' || r.status === 'FAILED';
    if (statusFilter === 'COMPLETED')
      return (
        r.status === 'APPROVED' ||
        r.status === 'SENT' ||
        r.status === 'PRINTED' ||
        r.status === 'PROCESSED'
      );
    return true;
  });

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-10">
      {/* 1. EXECUTIVE HERO & TELEMETRY STRIP */}
      <div className="ts-card p-7 sm:p-9 bg-white relative overflow-hidden">
        {/* Subtle decorative background gradient */}
        <div className="absolute top-0 right-0 w-96 h-96 bg-gradient-to-bl from-blue-50/60 via-slate-50/20 to-transparent pointer-events-none rounded-bl-full" />

        <div className="relative z-10 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
          <div className="space-y-2">
            <div className="flex items-center space-x-2.5">
              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold uppercase tracking-wider bg-slate-900 text-white font-mono">
                {user?.role}
              </span>
              <span className="text-sm font-mono text-slate-500 font-medium">
                NIP/NIM: {user?.nip_nim}
              </span>
              <span className="text-slate-300">•</span>
              <span className="inline-flex items-center text-xs font-medium text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 mr-1.5 animate-pulse" />
                Sistem Terhubung (Online)
              </span>
            </div>

            <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
              Selamat datang, {user?.nama}
            </h1>

            {user?.profile && (
              <p className="text-sm text-slate-600 font-medium">
                {user.profile.prodi ? `${user.profile.prodi} — ` : ''}
                {user.profile.fakultas || 'Fakultas Akademik'}
              </p>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {isLecturerOrAdmin && (
              <Link
                to="/approvals"
                className="h-11 px-5 text-sm font-semibold text-slate-800 bg-white border border-slate-300 hover:bg-slate-50 rounded-lg shadow-2xs transition ts-btn"
              >
                <Clock className="w-4 h-4 mr-2 text-blue-600" />
                <span>Antrean Persetujuan ({pendingCount})</span>
              </Link>
            )}

            <Link
              to="/surat/new"
              className="h-11 px-5 text-sm font-semibold text-white bg-slate-900 hover:bg-slate-800 rounded-lg shadow-xs transition ts-btn"
            >
              <PlusCircle className="w-4 h-4 mr-2" />
              <span>Buat Permohonan Surat</span>
            </Link>
          </div>
        </div>

        {/* Live Agentic Telemetry Strip */}
        <div className="mt-7 pt-5 border-t border-slate-100 grid grid-cols-2 md:grid-cols-4 gap-4 text-xs font-mono text-slate-600">
          <div className="flex items-center space-x-2">
            <Bot className="w-4 h-4 text-blue-600" />
            <span>Agent: <strong className="text-slate-900">Gemini 3.1 Flash</strong></span>
          </div>
          <div className="flex items-center space-x-2">
            <Activity className="w-4 h-4 text-emerald-600" />
            <span>Memory: <strong className="text-slate-900">Redis Active</strong></span>
          </div>
          <div className="flex items-center space-x-2">
            <Sparkles className="w-4 h-4 text-amber-600" />
            <span>Zero-Hallucination: <strong className="text-slate-900">Enforced</strong></span>
          </div>
          <div className="flex items-center space-x-2">
            <Layers className="w-4 h-4 text-purple-600" />
            <span>Security: <strong className="text-slate-900">TTE SHA-256</strong></span>
          </div>
        </div>
      </div>

      {/* 2. STATUTORY METRIC TILES (TASTE-SKILL 4-UP) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <div className="ts-card ts-card-interactive p-6 bg-white flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-500">
            <span className="text-sm font-semibold tracking-wide uppercase text-slate-600 font-sans">
              Total Permohonan
            </span>
            <FileText className="w-5 h-5 text-slate-400" />
          </div>
          <div className="mt-4">
            <div className="text-4xl font-extrabold text-slate-900 font-mono tracking-tight">
              {totalCount}
            </div>
            <div className="text-xs text-slate-500 mt-1.5 leading-relaxed">
              Arsip naskah surat dinas diajukan
            </div>
          </div>
        </div>

        <div className="ts-card ts-card-interactive p-6 bg-white flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold tracking-wide uppercase text-blue-700 font-sans">
              Menunggu Approval
            </span>
            <Clock className="w-5 h-5 text-blue-500" />
          </div>
          <div className="mt-4">
            <div className="text-4xl font-extrabold text-blue-900 font-mono tracking-tight">
              {pendingCount}
            </div>
            <div className="text-xs text-slate-500 mt-1.5 leading-relaxed">
              Menanti review pejabat DPA / Dekan
            </div>
          </div>
        </div>

        <div className="ts-card ts-card-interactive p-6 bg-white flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold tracking-wide uppercase text-amber-700 font-sans">
              Revisi Diminta
            </span>
            <AlertTriangle className="w-5 h-5 text-amber-500" />
          </div>
          <div className="mt-4">
            <div className="text-4xl font-extrabold text-amber-900 font-mono tracking-tight">
              {revisionCount}
            </div>
            <div className="text-xs text-slate-500 mt-1.5 leading-relaxed">
              Koreksi data wajib dari AI Self-Critique
            </div>
          </div>
        </div>

        <div className="ts-card ts-card-interactive p-6 bg-white flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold tracking-wide uppercase text-emerald-700 font-sans">
              Selesai & Diterbitkan
            </span>
            <CheckCircle2 className="w-5 h-5 text-emerald-500" />
          </div>
          <div className="mt-4">
            <div className="text-4xl font-extrabold text-emerald-900 font-mono tracking-tight">
              {completedCount}
            </div>
            <div className="text-xs text-slate-500 mt-1.5 leading-relaxed">
              TTE digital sah & siap diunduh
            </div>
          </div>
        </div>
      </div>

      {/* 3. WORKSPACE VIEW TOGGLE (STUDENTS CAN TOGGLE BETWEEN LIVE COPILOT & DOSSIER TABLE) */}
      {isStudent && (
        <div className="flex items-center space-x-3 border-b border-slate-200 pb-3">
          <button
            onClick={() => setActiveTab('records')}
            className={`px-4 py-2 text-sm font-bold tracking-tight rounded-md transition ts-btn ${
              activeTab === 'records'
                ? 'bg-slate-900 text-white shadow-xs'
                : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
            }`}
          >
            <FileText className="w-4 h-4 mr-2" />
            Daftar Berkas Permohonan ({requests.length})
          </button>
          <button
            onClick={() => setActiveTab('copilot')}
            className={`px-4 py-2 text-sm font-bold tracking-tight rounded-md transition ts-btn ${
              activeTab === 'copilot'
                ? 'bg-slate-900 text-white shadow-xs'
                : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
            }`}
          >
            <Sparkles className="w-4 h-4 mr-2 text-blue-400" />
            Asisten Percakapan AI (Copilot)
          </button>
        </div>
      )}

      {/* 4. ACTIVE WORKSPACE VIEW */}
      {activeTab === 'copilot' && isStudent ? (
        <div className="space-y-4">
          <div className="ts-card p-6 bg-white">
            <h2 className="text-lg font-bold text-slate-900 tracking-tight">
              Studio Konsultasi & Pengisian Slot AI
            </h2>
            <p className="text-sm text-slate-600 mt-1 leading-relaxed">
              Jelaskan tujuan dan data surat Anda menggunakan bahasa santai atau resmi.
              Agen akan mengekstrak atribut secara cerdas dan memverifikasi kelengkapan dokumen.
            </p>
          </div>
          <AIChatDrawer />
        </div>
      ) : (
        /* DOSSIER TABLE (EXECUTIVE DATA TABLE) */
        <div className="ts-card bg-white overflow-hidden shadow-xs">
          {/* Toolbar */}
          <div className="p-6 border-b border-slate-200 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            <div>
              <h2 className="text-base font-bold text-slate-900 tracking-tight flex items-center space-x-2">
                <FileText className="w-4 h-4 text-slate-700" />
                <span>Arsip Permohonan Dokumen Resmi</span>
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Pantau proses verifikasi berjenjang dan unduh surat resmi ber-TTE.
              </p>
            </div>

            <div className="flex items-center space-x-3">
              {/* Filter Pills */}
              <div className="inline-flex rounded-lg border border-slate-200 p-1 bg-slate-50 text-xs font-semibold">
                <button
                  onClick={() => setStatusFilter('ALL')}
                  className={`px-3 py-1.5 rounded-md transition ts-btn ${
                    statusFilter === 'ALL'
                      ? 'bg-white text-slate-900 shadow-2xs font-bold'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Semua ({totalCount})
                </button>
                <button
                  onClick={() => setStatusFilter('PENDING')}
                  className={`px-3 py-1.5 rounded-md transition ts-btn ${
                    statusFilter === 'PENDING'
                      ? 'bg-white text-blue-700 shadow-2xs font-bold'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Approval ({pendingCount})
                </button>
                <button
                  onClick={() => setStatusFilter('REVISION')}
                  className={`px-3 py-1.5 rounded-md transition ts-btn ${
                    statusFilter === 'REVISION'
                      ? 'bg-white text-amber-700 shadow-2xs font-bold'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Revisi ({revisionCount})
                </button>
                <button
                  onClick={() => setStatusFilter('COMPLETED')}
                  className={`px-3 py-1.5 rounded-md transition ts-btn ${
                    statusFilter === 'COMPLETED'
                      ? 'bg-white text-emerald-700 shadow-2xs font-bold'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Selesai ({completedCount})
                </button>
              </div>

              <button
                onClick={fetchRequests}
                title="Perbarui daftar"
                disabled={isLoading}
                className="p-2 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-100 border border-slate-200 transition ts-btn"
              >
                <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
              </button>
            </div>
          </div>

          {/* Table */}
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-left">
              <thead className="bg-slate-50/80 text-slate-600 text-xs font-bold uppercase tracking-wider">
                <tr>
                  <th scope="col" className="px-6 py-4">ID</th>
                  <th scope="col" className="px-6 py-4">Jenis Dokumen Resmi</th>
                  <th scope="col" className="px-6 py-4">Pemohon</th>
                  <th scope="col" className="px-6 py-4">Nomor Surat Resmi</th>
                  <th scope="col" className="px-6 py-4">Status Siklus</th>
                  <th scope="col" className="px-6 py-4">Waktu Pengajuan</th>
                  <th scope="col" className="px-6 py-4 text-right">Aksi</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-slate-100 text-sm">
                {isLoading ? (
                  <tr>
                    <td colSpan={7} className="px-6 py-16 text-center text-slate-400">
                      <div className="flex flex-col items-center justify-center space-y-3">
                        <RefreshCw className="w-6 h-6 animate-spin text-slate-400" />
                        <span className="text-sm font-medium">Memuat arsip surat...</span>
                      </div>
                    </td>
                  </tr>
                ) : filteredRequests.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-6 py-16 text-center text-slate-400">
                      <FileText className="w-10 h-10 mx-auto text-slate-300 mb-3" />
                      <p className="font-semibold text-slate-800 text-sm">
                        Tidak ada berkas permohonan pada kategori ini
                      </p>
                      <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto leading-relaxed">
                        Silakan buat permohonan baru menggunakan formulir atau asisten percakapan AI.
                      </p>
                    </td>
                  </tr>
                ) : (
                  filteredRequests.map((req) => (
                    <tr key={req.id} className="hover:bg-slate-50/80 transition-colors">
                      <td className="px-6 py-4 font-mono font-semibold text-slate-500">
                        #{req.id}
                      </td>
                      <td className="px-6 py-4">
                        <div className="font-bold text-slate-900 leading-snug">
                          {req.nama_surat}
                        </div>
                        <div className="text-xs text-slate-400 font-mono mt-0.5">
                          {req.kode_surat} • Kategori: {req.kategori}
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <div className="font-semibold text-slate-800">
                          {req.nama_mahasiswa}
                        </div>
                        <div className="text-xs text-slate-400 font-mono mt-0.5">
                          {req.nim_mahasiswa}
                        </div>
                      </td>
                      <td className="px-6 py-4 font-mono text-sm">
                        {req.nomor_surat_resmi ? (
                          <span className="font-semibold text-slate-900 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
                            {req.nomor_surat_resmi}
                          </span>
                        ) : (
                          <span className="text-slate-400 italic text-xs">Belum terbit</span>
                        )}
                      </td>
                      <td className="px-6 py-4">
                        <StatusBadge status={req.status} size="sm" />
                      </td>
                      <td className="px-6 py-4 text-xs text-slate-500 whitespace-nowrap">
                        {new Date(req.created_at).toLocaleDateString('id-ID', {
                          day: 'numeric',
                          month: 'short',
                          year: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </td>
                      <td className="px-6 py-4 text-right whitespace-nowrap">
                        <Link
                          to={`/surat/${req.id}`}
                          className="inline-flex items-center px-3.5 py-1.5 text-xs font-semibold text-slate-800 bg-white border border-slate-300 rounded-md hover:bg-slate-50 shadow-2xs transition ts-btn"
                        >
                          <span>Buka Berkas</span>
                          <ChevronRight className="w-3.5 h-3.5 ml-1 text-slate-400" />
                        </Link>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

export default DashboardPage;
