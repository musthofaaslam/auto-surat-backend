import React, { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import suratService from '../services/suratService';
import {
  FileText,
  ShieldCheck,
  CheckSquare,
  LogOut,
  LayoutDashboard,
  PlusCircle,
  User as UserIcon,
  X,
} from 'lucide-react';
import type { SuratType, MainViewType } from '../types';

export type { MainViewType };

interface DashboardSidebarProps {
  isOpen: boolean;
  onClose: () => void;
  activeMainView?: MainViewType;
  onSelectMainView?: (view: MainViewType) => void;
  onSelectLetterInForm?: (kodeSurat: string) => void;
  suratTypes?: SuratType[];
  selectedKodeSurat?: string;
}

export const DashboardSidebar: React.FC<DashboardSidebarProps> = ({
  isOpen,
  onClose,
  activeMainView,
  onSelectMainView,
  onSelectLetterInForm,
  suratTypes: propSuratTypes,
  selectedKodeSurat,
}) => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  // Desktop width shift collapse state (expanded w-72 by default)
  const [isDesktopCollapsed, setIsDesktopCollapsed] = useState(false);
  const [internalSuratTypes, setInternalSuratTypes] = useState<SuratType[]>([]);

  useEffect(() => {
    if (!propSuratTypes || propSuratTypes.length === 0) {
      suratService.getSuratTypes().then(setInternalSuratTypes).catch(() => {});
    }
  }, [propSuratTypes]);

  const activeSuratTypes =
    propSuratTypes && propSuratTypes.length > 0 ? propSuratTypes : internalSuratTypes;

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const isLecturerOrAdmin =
    user?.role === 'LECTURER' || user?.role === 'STAFF' || user?.role === 'ADMIN';

  // Helper to ensure mobile drawer closes upon item click while desktop sidebar stays permanently visible
  const handleItemNavigation = (action: () => void) => {
    action();
    if (typeof window !== 'undefined' && window.innerWidth < 1024) {
      onClose();
    }
  };

  const handleGoDashboard = () => {
    handleItemNavigation(() => {
      if (onSelectMainView) {
        onSelectMainView('dashboard');
      }
      if (location.pathname !== '/dashboard') {
        navigate('/dashboard?view=dashboard');
      }
    });
  };

  const handleGoBuatSurat = () => {
    handleItemNavigation(() => {
      if (onSelectMainView) {
        onSelectMainView('buat-surat');
      }
      if (location.pathname !== '/dashboard') {
        navigate('/dashboard?view=buat-surat');
      }
    });
  };

  const handleGoVerify = () => {
    handleItemNavigation(() => {
      if (onSelectMainView) {
        onSelectMainView('verify');
      }
      if (location.pathname !== '/dashboard') {
        navigate('/dashboard?view=verify');
      }
    });
  };

  const handleGoLetter = (kodeSurat: string) => {
    handleItemNavigation(() => {
      if (onSelectMainView) {
        onSelectMainView('buat-surat');
      }
      if (onSelectLetterInForm) {
        onSelectLetterInForm(kodeSurat);
      }
      navigate(`/dashboard?view=buat-surat&surat=${kodeSurat}`);
    });
  };

  // Group letters into 3 academic categories
  const letterGroups = [
    {
      category: 'Surat Keterangan',
      types: activeSuratTypes.filter((s) => s.kode_surat.startsWith('SK-')),
    },
    {
      category: 'Surat Pengantar',
      types: activeSuratTypes.filter((s) => s.kode_surat.startsWith('SP-')),
    },
    {
      category: 'Surat Rekomendasi & Izin',
      types: activeSuratTypes.filter(
        (s) => s.kode_surat.startsWith('SR-') || s.kode_surat.startsWith('SI-')
      ),
    },
  ];

  const isDashboardActive =
    ((location.pathname === '/dashboard' || location.pathname === '/') &&
      (!activeMainView || activeMainView === 'dashboard')) &&
    location.pathname !== '/buat-surat';
  const isBuatSuratActive =
    (location.pathname === '/dashboard' && activeMainView === 'buat-surat') ||
    location.pathname === '/buat-surat';
  const isVerifyActive =
    (location.pathname === '/dashboard' && activeMainView === 'verify') ||
    location.pathname.startsWith('/verify');
  const isApprovalsActive = location.pathname === '/approvals';

  const renderContent = (isCollapsed: boolean) => (
    <div className="flex flex-col h-full bg-white text-slate-900 border-r border-slate-200 select-none overflow-hidden">
      {/* 1. BRAND HEADER & DESKTOP COLLAPSE TOGGLE ON LOGO */}
      <div className={`h-16 px-4 flex items-center ${isCollapsed ? 'justify-center' : 'justify-between'} border-b border-slate-100 shrink-0`}>
        <div className="flex items-center space-x-2.5 min-w-0">
          {/* App Logo acting as Desktop Collapse/Expand Toggle */}
          <button
            type="button"
            onClick={() => {
              if (typeof window !== 'undefined' && window.innerWidth >= 1024) {
                setIsDesktopCollapsed(!isDesktopCollapsed);
              }
            }}
            className="w-8 h-8 rounded-lg bg-slate-900 text-white flex items-center justify-center shadow-2xs shrink-0 transition-all duration-150 hover:bg-slate-800 hover:scale-105 active:scale-95 cursor-pointer"
            title={isCollapsed ? 'Buka bilah sisi' : 'Ciutkan bilah sisi'}
            aria-label={isCollapsed ? 'Buka bilah sisi' : 'Ciutkan bilah sisi'}
          >
            <FileText className="w-4 h-4" />
          </button>

          {!isCollapsed && (
            <div className="flex flex-col min-w-0 animate-in fade-in duration-200">
              <span className="font-semibold text-sm tracking-tight text-slate-900 leading-tight">
                AutoSurat
              </span>
              <span className="text-[10px] text-slate-400 tracking-wider uppercase font-normal truncate">
                Tata Naskah Dinas
              </span>
            </div>
          )}
        </div>

        {/* Mobile Close Button */}
        {!isCollapsed && (
          <button
            onClick={onClose}
            className="lg:hidden p-1.5 rounded-md text-slate-400 hover:text-slate-800 hover:bg-slate-100 transition-colors"
            aria-label="Tutup bilah sisi"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* 2. SCROLLABLE NAVIGATION SECTIONS */}
      <div className="flex-1 overflow-y-auto px-3 py-4 space-y-6">
        {/* Core Navigation Items */}
        <div className="space-y-1">
          {!isCollapsed && (
            <div className="px-2 pb-1.5 text-[10px] font-semibold tracking-wider text-slate-400 uppercase animate-in fade-in duration-200">
              Menu Utama
            </div>
          )}

          {/* Menu Dashboard */}
          <button
            onClick={handleGoDashboard}
            title={isCollapsed ? 'Dashboard' : undefined}
            className={`w-full flex items-center ${
              isCollapsed ? 'justify-center px-2' : 'justify-between px-3'
            } py-2 rounded-lg text-xs transition-all duration-150 cursor-pointer ${
              isDashboardActive
                ? 'bg-slate-900 text-white font-semibold shadow-2xs'
                : 'text-slate-700 hover:bg-slate-100/80 hover:text-slate-900 font-normal hover:translate-x-0.5'
            }`}
          >
            <div className="flex items-center space-x-2.5">
              <LayoutDashboard className="w-3.5 h-3.5 shrink-0" />
              {!isCollapsed && <span>Dashboard</span>}
            </div>
          </button>

          {/* Menu Buat Surat */}
          <button
            onClick={handleGoBuatSurat}
            title={isCollapsed ? 'Buat Surat' : undefined}
            className={`w-full flex items-center ${
              isCollapsed ? 'justify-center px-2' : 'justify-between px-3'
            } py-2 rounded-lg text-xs transition-all duration-150 cursor-pointer ${
              isBuatSuratActive
                ? 'bg-slate-900 text-white font-semibold shadow-2xs'
                : 'text-slate-700 hover:bg-slate-100/80 hover:text-slate-900 font-normal hover:translate-x-0.5'
            }`}
          >
            <div className="flex items-center space-x-2.5">
              <PlusCircle className="w-3.5 h-3.5 shrink-0 text-blue-600" />
              {!isCollapsed && <span>Buat Surat</span>}
            </div>
          </button>

          {/* Menu Verifikasi TTE */}
          <button
            onClick={handleGoVerify}
            title={isCollapsed ? 'Verifikasi TTE' : undefined}
            className={`w-full flex items-center ${
              isCollapsed ? 'justify-center px-2' : 'justify-between px-3'
            } py-2 rounded-lg text-xs transition-all duration-150 cursor-pointer ${
              isVerifyActive
                ? 'bg-slate-900 text-white font-semibold shadow-2xs'
                : 'text-slate-700 hover:bg-slate-100/80 hover:text-slate-900 font-normal hover:translate-x-0.5'
            }`}
          >
            <div className="flex items-center space-x-2.5">
              <ShieldCheck className="w-3.5 h-3.5 shrink-0 text-emerald-600" />
              {!isCollapsed && <span>Verifikasi TTE</span>}
            </div>
          </button>

          {/* Antrean Persetujuan (Khusus Dosen/Admin) */}
          {isLecturerOrAdmin && (
            <Link
              to="/approvals"
              title={isCollapsed ? 'Antrean Persetujuan' : undefined}
              onClick={() => {
                if (typeof window !== 'undefined' && window.innerWidth < 1024) {
                  onClose();
                }
              }}
              className={`w-full flex items-center ${
                isCollapsed ? 'justify-center px-2' : 'justify-between px-3'
              } py-2 rounded-lg text-xs transition-all duration-150 ${
                isApprovalsActive
                  ? 'bg-slate-900 text-white font-semibold shadow-2xs'
                  : 'text-slate-700 hover:bg-slate-100/80 hover:text-slate-900 font-normal hover:translate-x-0.5'
              }`}
            >
              <div className="flex items-center space-x-2.5">
                <CheckSquare className="w-3.5 h-3.5 shrink-0 text-amber-600" />
                {!isCollapsed && <span>Antrean Persetujuan</span>}
              </div>
            </Link>
          )}
        </div>

        {/* Master Jenis Surat (Katalog 10 Jenis Surat) */}
        {!isCollapsed && (
          <div className="space-y-4 pt-2 border-t border-slate-100 animate-in fade-in duration-200">
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
                        isBuatSuratActive && selectedKodeSurat === item.kode_surat;
                      return (
                        <button
                          key={item.kode_surat}
                          onClick={() => handleGoLetter(item.kode_surat)}
                          className={`w-full text-left px-2.5 py-1.5 rounded-md text-xs transition-all duration-150 flex items-center justify-between group cursor-pointer ${
                            isSelected
                              ? 'bg-slate-100 text-slate-900 font-semibold'
                              : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900 font-normal hover:translate-x-1'
                          }`}
                        >
                          <div className="flex items-center space-x-2 truncate">
                            <span className="w-1.5 h-1.5 rounded-full bg-slate-300 group-hover:bg-slate-600 shrink-0 transition-colors" />
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
        )}
      </div>

      {/* 3. USER FOOTER & LOGOUT */}
      <div className="p-3 border-t border-slate-100 bg-slate-50/60 shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2.5 min-w-0">
            <div className="w-8 h-8 rounded-full bg-slate-200 border border-slate-300 flex items-center justify-center text-slate-700 shrink-0">
              <UserIcon className="w-4 h-4" />
            </div>
            {!isCollapsed && (
              <div className="flex flex-col min-w-0 animate-in fade-in duration-200">
                <span className="text-xs font-semibold text-slate-900 truncate">
                  {user?.nama || 'Pengguna'}
                </span>
                <div className="flex items-center space-x-1 text-[10px] text-slate-500 font-normal">
                  <span className="truncate">{user?.nip_nim}</span>
                  <span>•</span>
                  <span className="uppercase font-semibold text-slate-700">{user?.role}</span>
                </div>
              </div>
            )}
          </div>

          {!isCollapsed && (
            <button
              onClick={handleLogout}
              title="Keluar dari sesi"
              className="p-1.5 rounded-md text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors shrink-0 cursor-pointer"
              aria-label="Keluar dari sesi"
            >
              <LogOut className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop Persistent Sidebar with Width Shift Transition (Pushes main content gracefully) */}
      <aside
        className={`hidden lg:block h-screen shrink-0 bg-white border-r border-slate-200 z-30 select-none transition-[width] duration-300 ease-[cubic-bezier(0.2,0.8,0.2,1)] ${
          isDesktopCollapsed ? 'w-20' : 'w-72'
        }`}
      >
        {renderContent(isDesktopCollapsed)}
      </aside>

      {/* Mobile Off-Canvas Drawer Container */}
      <div
        className={`lg:hidden fixed inset-0 z-50 ${
          isOpen ? 'pointer-events-auto' : 'pointer-events-none'
        }`}
      >
        {/* Ultra-Smooth Backdrop Blur & Black Tint Overlay */}
        <div
          onClick={onClose}
          className={`fixed inset-0 smooth-mobile-backdrop cursor-pointer ${
            isOpen ? 'opacity-100' : 'opacity-0 pointer-events-none'
          }`}
          aria-hidden="true"
        />

        {/* Sliding Panel */}
        <div
          className={`relative w-72 max-w-[85vw] h-full shadow-2xl z-10 bg-white transition-transform duration-350 ease-[cubic-bezier(0.22,1,0.36,1)] ${
            isOpen ? 'translate-x-0' : '-translate-x-full'
          }`}
        >
          {renderContent(false)}
        </div>
      </div>
    </>
  );
};

export default DashboardSidebar;
