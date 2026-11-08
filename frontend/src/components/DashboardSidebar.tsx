import React from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  FileText,
  ShieldCheck,
  CheckSquare,
  LogOut,
  LayoutDashboard,
  User as UserIcon,
  X,
  Sparkles,
} from 'lucide-react';
import type { SuratType } from '../types';

interface DashboardSidebarProps {
  isOpen: boolean;
  onClose: () => void;
  activeMainView: 'dashboard' | 'verify';
  onSelectMainView: (view: 'dashboard' | 'verify') => void;
  onSelectLetterInForm: (kodeSurat: string) => void;
  suratTypes: SuratType[];
  selectedKodeSurat: string;
}

export const DashboardSidebar: React.FC<DashboardSidebarProps> = ({
  isOpen,
  onClose,
  activeMainView,
  onSelectMainView,
  onSelectLetterInForm,
  suratTypes,
  selectedKodeSurat,
}) => {
  const { user, logout } = useAuth();

  const handleLogout = async () => {
    await logout();
    window.location.href = '/login';
  };

  const isLecturerOrAdmin =
    user?.role === 'LECTURER' || user?.role === 'STAFF' || user?.role === 'ADMIN';

  // Group letters into 3 academic categories
  const letterGroups = [
    {
      category: 'Surat Keterangan',
      types: suratTypes.filter((s) => s.kode_surat.startsWith('SK-')),
    },
    {
      category: 'Surat Pengantar',
      types: suratTypes.filter((s) => s.kode_surat.startsWith('SP-')),
    },
    {
      category: 'Surat Rekomendasi & Izin',
      types: suratTypes.filter(
        (s) => s.kode_surat.startsWith('SR-') || s.kode_surat.startsWith('SI-')
      ),
    },
  ];

  const sidebarContent = (
    <div className="flex flex-col h-full bg-white text-slate-900 border-r border-slate-200 select-none">
      {/* 1. BRAND HEADER */}
      <div className="h-16 px-4 flex items-center justify-between border-b border-slate-100 shrink-0">
        <div className="flex items-center space-x-2.5">
          <div className="w-8 h-8 rounded-lg bg-slate-900 text-white flex items-center justify-center shadow-2xs">
            <FileText className="w-4 h-4" />
          </div>
          <div className="flex flex-col">
            <div className="flex items-center space-x-1.5">
              <span className="font-semibold text-sm tracking-tight text-slate-900 leading-tight">
                AutoSurat
              </span>
              <span className="inline-flex items-center px-1.5 py-0.2 rounded text-[10px] font-semibold bg-blue-50 text-blue-700 border border-blue-200/70">
                <Sparkles className="w-2.5 h-2.5 mr-0.5" />
                v2.0 AI
              </span>
            </div>
            <span className="text-[10px] text-slate-400 tracking-wider uppercase font-normal">
              Tata Naskah Dinas
            </span>
          </div>
        </div>

        {/* Mobile Close Button */}
        <button
          onClick={onClose}
          className="lg:hidden p-1.5 rounded-md text-slate-400 hover:text-slate-800 hover:bg-slate-100 transition"
          aria-label="Tutup bilah sisi"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* 2. SCROLLABLE NAVIGATION SECTIONS */}
      <div className="flex-1 overflow-y-auto px-3 py-4 space-y-6">
        {/* Core Navigation Items (Direct Replacement of Navbar Links) */}
        <div className="space-y-1">
          <div className="px-2 pb-1.5 text-[10px] font-semibold tracking-wider text-slate-400 uppercase">
            Menu Utama
          </div>

          {/* Menu Dasbor (Formulir Surat & Sesi Chat AI) */}
          <button
            onClick={() => {
              onSelectMainView('dashboard');
              onClose();
            }}
            className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs transition ${
              activeMainView === 'dashboard'
                ? 'bg-slate-900 text-white font-semibold shadow-2xs'
                : 'text-slate-700 hover:bg-slate-100/80 hover:text-slate-900 font-normal'
            }`}
          >
            <div className="flex items-center space-x-2.5">
              <LayoutDashboard className="w-3.5 h-3.5 shrink-0" />
              <span>Dasbor</span>
            </div>
          </button>

          {/* Menu Verifikasi TTE */}
          <button
            onClick={() => {
              onSelectMainView('verify');
              onClose();
            }}
            className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs transition ${
              activeMainView === 'verify'
                ? 'bg-slate-900 text-white font-semibold shadow-2xs'
                : 'text-slate-700 hover:bg-slate-100/80 hover:text-slate-900 font-normal'
            }`}
          >
            <div className="flex items-center space-x-2.5">
              <ShieldCheck className="w-3.5 h-3.5 shrink-0 text-emerald-600" />
              <span>Verifikasi TTE</span>
            </div>
          </button>

          {/* Antrean Persetujuan (Hanya Tampil Jika Dosen/Admin) */}
          {isLecturerOrAdmin && (
            <Link
              to="/approvals"
              onClick={onClose}
              className="flex items-center justify-between px-3 py-2 rounded-lg text-xs font-normal text-slate-700 hover:bg-slate-100/80 hover:text-slate-900 transition"
            >
              <div className="flex items-center space-x-2.5">
                <CheckSquare className="w-3.5 h-3.5 shrink-0 text-amber-600" />
                <span>Antrean Persetujuan</span>
              </div>
            </Link>
          )}
        </div>

        {/* Master Jenis Surat (Katalog 10 Jenis Surat) */}
        <div className="space-y-4 pt-2 border-t border-slate-100">
          <div className="px-2 text-[10px] font-semibold tracking-wider text-slate-400 uppercase">
            Katalog Jenis Surat
          </div>

          {letterGroups.map((group) => {
            if (group.types.length === 0) return null;
            return (
              <div key={group.category} className="space-y-1">
                <div className="px-2 text-[11px] font-semibold text-slate-500">
                  {group.category}
                </div>
                <div className="space-y-0.5">
                  {group.types.map((item) => {
                    const isSelected =
                      activeMainView === 'dashboard' && selectedKodeSurat === item.kode_surat;
                    return (
                      <button
                        key={item.kode_surat}
                        onClick={() => {
                          onSelectLetterInForm(item.kode_surat);
                          onClose();
                        }}
                        className={`w-full text-left px-2.5 py-1.5 rounded-md text-xs transition flex items-center justify-between group ${
                          isSelected
                            ? 'bg-slate-100 text-slate-900 font-semibold'
                            : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900 font-normal'
                        }`}
                      >
                        <div className="flex items-center space-x-2 truncate">
                          <span className="w-1.5 h-1.5 rounded-full bg-slate-300 group-hover:bg-slate-600 shrink-0" />
                          <span className="truncate">{item.nama_surat}</span>
                        </div>
                        <span className="text-[10px] px-1 rounded bg-slate-100 text-slate-500 shrink-0 ml-1">
                          {item.kode_surat}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 3. USER FOOTER & LOGOUT */}
      <div className="p-3 border-t border-slate-100 bg-slate-50/60 shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2.5 min-w-0">
            <div className="w-8 h-8 rounded-full bg-slate-200 border border-slate-300 flex items-center justify-center text-slate-700 shrink-0">
              <UserIcon className="w-4 h-4" />
            </div>
            <div className="flex flex-col min-w-0">
              <span className="text-xs font-semibold text-slate-900 truncate">
                {user?.nama || 'Pengguna'}
              </span>
              <div className="flex items-center space-x-1 text-[10px] text-slate-500 font-normal">
                <span className="truncate">{user?.nip_nim}</span>
                <span>•</span>
                <span className="uppercase font-semibold text-slate-700">{user?.role}</span>
              </div>
            </div>
          </div>

          <button
            onClick={handleLogout}
            title="Keluar dari sesi"
            className="p-1.5 rounded-md text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition shrink-0"
            aria-label="Keluar dari sesi"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop Persistent Sidebar (Open by default) */}
      <aside
        className={`hidden lg:block w-72 h-screen shrink-0 transition-all duration-200 ${
          isOpen ? 'translate-x-0' : '-translate-x-full lg:w-0 overflow-hidden'
        }`}
      >
        {sidebarContent}
      </aside>

      {/* Mobile Off-Canvas Drawer (Slides in from the left) */}
      {isOpen && (
        <div className="lg:hidden fixed inset-0 z-50 flex">
          {/* Backdrop Blur Overlay */}
          <div
            onClick={onClose}
            className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs transition-opacity"
            aria-hidden="true"
          />

          {/* Sliding Panel */}
          <div className="relative w-72 max-w-[85vw] h-full shadow-2xl z-10 animate-in slide-in-from-left duration-200">
            {sidebarContent}
          </div>
        </div>
      )}
    </>
  );
};

export default DashboardSidebar;
