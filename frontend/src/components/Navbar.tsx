import React, { useState } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  FileText,
  CheckSquare,
  ShieldCheck,
  PlusCircle,
  LogOut,
  LayoutDashboard,
  User as UserIcon,
  Menu,
  X,
  Sparkles,
} from 'lucide-react';

// Architectural Note (Taste-Skill 2.5 - Navbar):
// High-craft 72px executive header. Equal left and right content edges (--container: 1280px).
// Zero-emoji Swiss typographic clarity, subtle 1px border hairline, and responsive drawer.

export const Navbar: React.FC = () => {
  const { user, logout, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const isActive = (path: string) => location.pathname === path;

  const isLecturerOrAdmin =
    user?.role === 'LECTURER' || user?.role === 'STAFF' || user?.role === 'ADMIN';

  return (
    <header className="sticky top-0 z-40 bg-white/95 backdrop-blur-md border-b border-slate-200/80 transition-all">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-[72px]">
          {/* Brand Mark */}
          <div className="flex items-center space-x-10">
            <Link
              to="/dashboard"
              className="flex items-center space-x-3 focus:outline-none group"
            >
              <div className="w-9 h-9 rounded-lg bg-slate-900 flex items-center justify-center text-white shadow-xs group-hover:bg-slate-800 transition">
                <FileText className="w-5 h-5" />
              </div>
              <div className="flex flex-col">
                <div className="flex items-center space-x-1.5">
                  <span className="font-bold text-base tracking-tight text-slate-900 leading-tight">
                    AutoSurat
                  </span>
                  <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-blue-50 text-blue-700 border border-blue-200/60 font-mono">
                    <Sparkles className="w-2.5 h-2.5 mr-1" />
                    v2.0 AI
                  </span>
                </div>
                <span className="text-[11px] text-slate-500 tracking-wider uppercase font-medium">
                  Tata Naskah Dinas Akademik
                </span>
              </div>
            </Link>

            {/* Desktop Navigation Links */}
            {isAuthenticated && (
              <nav className="hidden md:flex items-center space-x-2">
                <Link
                  to="/dashboard"
                  aria-current={isActive('/dashboard') ? 'page' : undefined}
                  className={`inline-flex items-center px-3.5 py-2 text-sm font-medium transition-all ts-btn rounded-md ${
                    isActive('/dashboard')
                      ? 'bg-slate-100 text-slate-900 font-semibold'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
                  }`}
                >
                  <LayoutDashboard className="w-4 h-4 mr-2 text-slate-500" />
                  Dasbor
                </Link>

                <Link
                  to="/surat/new"
                  aria-current={isActive('/surat/new') ? 'page' : undefined}
                  className={`inline-flex items-center px-3.5 py-2 text-sm font-medium transition-all ts-btn rounded-md ${
                    isActive('/surat/new')
                      ? 'bg-slate-100 text-slate-900 font-semibold'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
                  }`}
                >
                  <PlusCircle className="w-4 h-4 mr-2 text-slate-500" />
                  Permohonan Baru
                </Link>

                {isLecturerOrAdmin && (
                  <Link
                    to="/approvals"
                    aria-current={isActive('/approvals') ? 'page' : undefined}
                    className={`inline-flex items-center px-3.5 py-2 text-sm font-medium transition-all ts-btn rounded-md ${
                      isActive('/approvals')
                        ? 'bg-slate-100 text-slate-900 font-semibold'
                        : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
                    }`}
                  >
                    <CheckSquare className="w-4 h-4 mr-2 text-slate-500" />
                    Antrean Persetujuan
                  </Link>
                )}

                <Link
                  to="/verify"
                  aria-current={isActive('/verify') ? 'page' : undefined}
                  className={`inline-flex items-center px-3.5 py-2 text-sm font-medium transition-all ts-btn rounded-md ${
                    isActive('/verify')
                      ? 'bg-slate-100 text-slate-900 font-semibold'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
                  }`}
                >
                  <ShieldCheck className="w-4 h-4 mr-2 text-slate-500" />
                  Verifikasi Publik
                </Link>
              </nav>
            )}
          </div>

          {/* User Controls & Mobile Menu Button */}
          <div className="flex items-center space-x-3">
            {isAuthenticated && user ? (
              <div className="flex items-center space-x-3">
                <div className="hidden sm:flex flex-col text-right">
                  <span className="text-sm font-semibold text-slate-900 leading-tight">
                    {user.nama}
                  </span>
                  <div className="flex items-center justify-end space-x-1.5 mt-0.5">
                    <span className="text-xs text-slate-500 font-mono">
                      {user.nip_nim}
                    </span>
                    <span className="text-[10px] px-1.5 py-0.2 rounded font-semibold uppercase bg-slate-100 text-slate-700 border border-slate-200">
                      {user.role}
                    </span>
                  </div>
                </div>

                <div className="w-9 h-9 rounded-full bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-700 shadow-2xs">
                  <UserIcon className="w-4 h-4" />
                </div>

                <button
                  onClick={handleLogout}
                  title="Keluar dari sesi"
                  className="hidden md:inline-flex items-center justify-center p-2 rounded-md text-slate-500 hover:text-rose-600 hover:bg-rose-50 border border-transparent hover:border-rose-200 transition ts-btn"
                >
                  <LogOut className="w-4 h-4" />
                </button>

                {/* Mobile Menu Hamburger */}
                <button
                  onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                  className="md:hidden p-2 rounded-md text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition"
                  aria-label="Buka menu navigasi"
                >
                  {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
                </button>
              </div>
            ) : (
              <div className="flex items-center space-x-2">
                <Link
                  to="/verify"
                  className="px-3.5 py-2 text-xs font-semibold text-slate-700 hover:text-slate-900 transition ts-btn"
                >
                  Verifikasi Publik
                </Link>
                <Link
                  to="/login"
                  className="px-4 py-2 text-xs font-semibold text-white bg-slate-900 hover:bg-slate-800 rounded-md shadow-xs transition ts-btn"
                >
                  Masuk Akun
                </Link>
              </div>
            )}
          </div>
        </div>

        {/* Mobile Dropdown Menu */}
        {isAuthenticated && mobileMenuOpen && (
          <div className="md:hidden py-3 border-t border-slate-200 space-y-1">
            <Link
              to="/dashboard"
              onClick={() => setMobileMenuOpen(false)}
              className={`flex items-center px-3 py-2 rounded-md text-sm font-medium ${
                isActive('/dashboard')
                  ? 'bg-slate-100 text-slate-900 font-semibold'
                  : 'text-slate-600 hover:bg-slate-50'
              }`}
            >
              <LayoutDashboard className="w-4 h-4 mr-2" />
              Dasbor
            </Link>

            <Link
              to="/surat/new"
              onClick={() => setMobileMenuOpen(false)}
              className={`flex items-center px-3 py-2 rounded-md text-sm font-medium ${
                isActive('/surat/new')
                  ? 'bg-slate-100 text-slate-900 font-semibold'
                  : 'text-slate-600 hover:bg-slate-50'
              }`}
            >
              <PlusCircle className="w-4 h-4 mr-2" />
              Permohonan Baru
            </Link>

            {isLecturerOrAdmin && (
              <Link
                to="/approvals"
                onClick={() => setMobileMenuOpen(false)}
                className={`flex items-center px-3 py-2 rounded-md text-sm font-medium ${
                  isActive('/approvals')
                    ? 'bg-slate-100 text-slate-900 font-semibold'
                    : 'text-slate-600 hover:bg-slate-50'
                }`}
              >
                <CheckSquare className="w-4 h-4 mr-2" />
                Antrean Persetujuan
              </Link>
            )}

            <Link
              to="/verify"
              onClick={() => setMobileMenuOpen(false)}
              className={`flex items-center px-3 py-2 rounded-md text-sm font-medium ${
                isActive('/verify')
                  ? 'bg-slate-100 text-slate-900 font-semibold'
                  : 'text-slate-600 hover:bg-slate-50'
              }`}
            >
              <ShieldCheck className="w-4 h-4 mr-2" />
              Verifikasi Surat
            </Link>

            <button
              onClick={() => {
                setMobileMenuOpen(false);
                handleLogout();
              }}
              className="w-full flex items-center px-3 py-2 rounded-md text-sm font-medium text-rose-600 hover:bg-rose-50"
            >
              <LogOut className="w-4 h-4 mr-2" />
              Keluar dari Sesi
            </button>
          </div>
        )}
      </div>
    </header>
  );
};

export default Navbar;
