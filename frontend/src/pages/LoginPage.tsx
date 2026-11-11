import React, { useState } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  FileText,
  Lock,
  User,
  AlertCircle,
  ArrowRight,
  ShieldCheck,
  Eye,
  EyeOff,
  GraduationCap,
  Briefcase,
  Check,
} from 'lucide-react';

// Architectural Note (Taste-Skill 2.5 - Minimalist Authentication Studio):
// Clean executive login workstation adhering to Swiss typographic clarity,
// optical hairlines, and harmonized color palettes identical to the AutoSurat dashboard.
// Strictly eliminates AI jargon and promotional banners.

export const LoginPage: React.FC = () => {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [nipNim, setNipNim] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [selectedPreset, setSelectedPreset] = useState<'student' | 'lecturer' | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const from = (location.state as any)?.from?.pathname || '/dashboard';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!nipNim.trim() || !password.trim()) {
      setErrorMsg('NIM/NIP dan Kata Sandi wajib diisi.');
      return;
    }

    setErrorMsg(null);
    setIsSubmitting(true);

    try {
      await login(nipNim.trim(), password.trim());
      navigate(from, { replace: true });
    } catch (err: any) {
      if (err.response?.data?.message) {
        const extra = err.response?.data?.errors?.non_field_errors
          ? ` (${err.response.data.errors.non_field_errors.join(', ')})`
          : '';
        setErrorMsg(`${err.response.data.message}${extra}`);
      } else if (err.response?.data?.errors?.non_field_errors) {
        setErrorMsg(err.response.data.errors.non_field_errors.join(', '));
      } else {
        setErrorMsg('Gagal masuk. Periksa kembali NIM/NIP dan kata sandi Anda.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleFillDemo = (type: 'student' | 'lecturer') => {
    setSelectedPreset(type);
    setErrorMsg(null);
    if (type === 'student') {
      setNipNim('INF24001');
      setPassword('12345678');
    } else {
      setNipNim('198001012005011001');
      setPassword('12345678');
    }
  };

  return (
    <div className="min-h-[calc(100vh-130px)] flex flex-col justify-center items-center py-10 px-4 sm:px-6">
      {/* Brand Header */}
      <div className="w-full max-w-[420px] text-center mb-6">
        <div className="w-10 h-10 rounded-xl bg-slate-900 text-white flex items-center justify-center shadow-2xs mx-auto mb-3">
          <FileText className="w-5 h-5 text-slate-100" />
        </div>
        <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 leading-tight">
          AutoSurat
        </h1>
        <p className="text-xs text-slate-500 mt-1 uppercase tracking-wider font-medium">
          Tata Naskah Dinas Akademik
        </p>
      </div>

      {/* Main Login Card */}
      <div className="w-full max-w-[420px] bg-white border border-slate-200/90 rounded-2xl shadow-xs p-6 sm:p-8 space-y-6">
        <div>
          <h2 className="text-base font-semibold text-slate-900 tracking-tight">
            Masuk ke Akun
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Akses layanan pengajuan surat dinas dan verifikasi dokumen.
          </p>
        </div>

        {/* Error Alert Box */}
        {errorMsg && (
          <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 flex items-start space-x-2.5 text-xs text-rose-800 animate-in fade-in duration-200">
            <AlertCircle className="w-4 h-4 shrink-0 text-rose-600 mt-0.5" />
            <span className="leading-snug">{errorMsg}</span>
          </div>
        )}

        {/* Form Controls */}
        <form className="space-y-4" onSubmit={handleSubmit}>
          {/* NIM / NIP Input */}
          <div className="space-y-1.5">
            <label
              htmlFor="nip_nim"
              className="block text-[11px] font-semibold text-slate-700 uppercase tracking-wider"
            >
              NIM / NIP Pengguna
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                <User className="w-4 h-4" />
              </div>
              <input
                id="nip_nim"
                name="nip_nim"
                type="text"
                required
                value={nipNim}
                onChange={(e) => {
                  setNipNim(e.target.value);
                  setSelectedPreset(null);
                }}
                placeholder="Contoh: INF24001 / NIP Dosen"
                className="block w-full pl-10 pr-3.5 py-2.5 text-xs sm:text-sm text-slate-900 bg-slate-50/70 border border-slate-200 rounded-xl focus:bg-white focus:border-slate-900 focus:ring-1 focus:ring-slate-900 font-mono transition placeholder:font-sans placeholder:text-slate-400 shadow-2xs"
              />
            </div>
          </div>

          {/* Password Input */}
          <div className="space-y-1.5">
            <label
              htmlFor="password"
              className="block text-[11px] font-semibold text-slate-700 uppercase tracking-wider"
            >
              Kata Sandi
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                <Lock className="w-4 h-4" />
              </div>
              <input
                id="password"
                name="password"
                type={showPassword ? 'text' : 'password'}
                required
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  setSelectedPreset(null);
                }}
                placeholder="Masukkan kata sandi akun"
                className="block w-full pl-10 pr-10 py-2.5 text-xs sm:text-sm text-slate-900 bg-slate-50/70 border border-slate-200 rounded-xl focus:bg-white focus:border-slate-900 focus:ring-1 focus:ring-slate-900 transition placeholder:text-slate-400 shadow-2xs"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute inset-y-0 right-0 pr-3.5 flex items-center text-slate-400 hover:text-slate-700 transition cursor-pointer"
                title={showPassword ? 'Sembunyikan kata sandi' : 'Tampilkan kata sandi'}
                aria-label={showPassword ? 'Sembunyikan kata sandi' : 'Tampilkan kata sandi'}
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Submit Action Button */}
          <div className="pt-2">
            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full h-11 flex justify-center items-center px-4 rounded-xl text-xs sm:text-sm font-semibold text-white bg-slate-900 hover:bg-slate-800 active:scale-[0.99] disabled:opacity-50 shadow-2xs transition-all duration-150 ts-btn cursor-pointer"
            >
              {isSubmitting ? (
                <span>Memverifikasi akun...</span>
              ) : (
                <>
                  <span>Masuk ke Sistem</span>
                  <ArrowRight className="w-4 h-4 ml-1.5 text-slate-300" />
                </>
              )}
            </button>
          </div>
        </form>

        {/* Demo Accounts Presets (Quick Fast Login) */}
        <div className="pt-4 border-t border-slate-100">
          <div className="flex items-center justify-between mb-2.5">
            <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
              Akun Uji Coba Cepat
            </span>
            <span className="text-[10px] text-slate-400">Klik untuk isi otomatis</span>
          </div>

          <div className="grid grid-cols-2 gap-2.5">
            {/* Student Preset */}
            <button
              type="button"
              onClick={() => handleFillDemo('student')}
              className={`p-2.5 text-left rounded-xl border transition-all duration-150 flex flex-col justify-between group cursor-pointer ${
                selectedPreset === 'student'
                  ? 'border-slate-900 bg-slate-50 ring-1 ring-slate-900/10'
                  : 'border-slate-200/90 bg-slate-50/60 hover:bg-slate-100/80 hover:border-slate-300'
              }`}
            >
              <div className="flex items-center justify-between w-full">
                <div className="w-6 h-6 rounded-md bg-blue-50 text-blue-700 flex items-center justify-center border border-blue-100 shrink-0">
                  <GraduationCap className="w-3.5 h-3.5" />
                </div>
                {selectedPreset === 'student' && (
                  <Check className="w-3.5 h-3.5 text-slate-900" />
                )}
              </div>
              <div className="mt-2 min-w-0">
                <div className="text-xs font-semibold text-slate-900 truncate">
                  Mahasiswa
                </div>
                <div className="text-[11px] text-slate-500 font-mono mt-0.5 truncate">
                  INF24001
                </div>
              </div>
            </button>

            {/* Lecturer / Officer Preset */}
            <button
              type="button"
              onClick={() => handleFillDemo('lecturer')}
              className={`p-2.5 text-left rounded-xl border transition-all duration-150 flex flex-col justify-between group cursor-pointer ${
                selectedPreset === 'lecturer'
                  ? 'border-slate-900 bg-slate-50 ring-1 ring-slate-900/10'
                  : 'border-slate-200/90 bg-slate-50/60 hover:bg-slate-100/80 hover:border-slate-300'
              }`}
            >
              <div className="flex items-center justify-between w-full">
                <div className="w-6 h-6 rounded-md bg-amber-50 text-amber-700 flex items-center justify-center border border-amber-100 shrink-0">
                  <Briefcase className="w-3.5 h-3.5" />
                </div>
                {selectedPreset === 'lecturer' && (
                  <Check className="w-3.5 h-3.5 text-slate-900" />
                )}
              </div>
              <div className="mt-2 min-w-0">
                <div className="text-xs font-semibold text-slate-900 truncate">
                  Dosen / Pejabat
                </div>
                <div className="text-[11px] text-slate-500 font-mono mt-0.5 truncate">
                  19800101...
                </div>
              </div>
            </button>
          </div>
        </div>
      </div>

      {/* Public Verification Link */}
      <div className="mt-6 text-center">
        <Link
          to="/verify"
          className="inline-flex items-center space-x-1.5 text-xs text-slate-500 hover:text-slate-900 transition-colors"
        >
          <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
          <span>Ingin memeriksa keabsahan surat fisik?</span>
          <span className="font-semibold text-slate-900 underline decoration-slate-300 underline-offset-2 hover:decoration-slate-900">
            Verifikasi TTE
          </span>
        </Link>
      </div>
    </div>
  );
};

export default LoginPage;
