import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { FileText, Lock, User, AlertCircle, ArrowRight, ShieldCheck, Sparkles } from 'lucide-react';

export const LoginPage: React.FC = () => {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [nipNim, setNipNim] = useState('');
  const [password, setPassword] = useState('');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const from = (location.state as any)?.from?.pathname || '/dashboard';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!nipNim || !password) {
      setErrorMsg('NIP/NIM dan Password wajib diisi.');
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
        setErrorMsg('Gagal masuk. Periksa kembali NIP/NIM dan kata sandi Anda.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleFillDemo = (type: 'student' | 'lecturer') => {
    if (type === 'student') {
      setNipNim('INF24001');
      setPassword('12345678');
    } else {
      setNipNim('198001012005011001');
      setPassword('12345678');
    }
    setErrorMsg(null);
  };

  return (
    <div className="min-h-screen flex flex-col justify-center py-12 px-4 sm:px-6 lg:px-8 bg-slate-100">
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center">
        <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-slate-900 text-white shadow-md mx-auto mb-4 border border-slate-800">
          <FileText className="w-7 h-7 text-indigo-400" />
        </div>
        <div className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-full bg-indigo-50 border border-indigo-200 text-indigo-700 text-xs font-semibold mb-2">
          <Sparkles className="w-3.5 h-3.5" />
          <span>Agentic AI Persuratan Akademik v2.0</span>
        </div>
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900">
          AutoSurat Kampus
        </h1>
        <p className="mt-2 text-sm text-slate-600 max-w-sm mx-auto leading-relaxed">
          Penerbitan Tata Naskah Dinas Resmi dengan Validasi Level-2 Self-Reflection dan Tanda Tangan Elektronik (TTE).
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="ts-card p-6 sm:p-8 bg-white shadow-lg border border-slate-300">
          {errorMsg && (
            <div className="mb-5 p-3.5 rounded-lg bg-rose-50 border border-rose-300 flex items-start space-x-3 text-sm text-rose-800">
              <AlertCircle className="w-5 h-5 shrink-0 text-rose-600 mt-0.5" />
              <span className="leading-snug">{errorMsg}</span>
            </div>
          )}

          <form className="space-y-5" onSubmit={handleSubmit}>
            <div>
              <label
                htmlFor="nip_nim"
                className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5"
              >
                NIM / NIP Pengguna
              </label>
              <div className="relative rounded-lg">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                  <User className="w-5 h-5" />
                </div>
                <input
                  id="nip_nim"
                  name="nip_nim"
                  type="text"
                  required
                  value={nipNim}
                  onChange={(e) => setNipNim(e.target.value)}
                  placeholder="Contoh: INF24001 atau NIP Dosen"
                  className="block w-full pl-11 pr-4 py-3 text-sm text-slate-900 bg-slate-50 border border-slate-300 rounded-lg focus:ring-2 focus:ring-slate-900 focus:border-slate-900 focus:bg-white font-mono transition placeholder-slate-400"
                />
              </div>
            </div>

            <div>
              <label
                htmlFor="password"
                className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5"
              >
                Kata Sandi
              </label>
              <div className="relative rounded-lg">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                  <Lock className="w-5 h-5" />
                </div>
                <input
                  id="password"
                  name="password"
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Masukkan kata sandi"
                  className="block w-full pl-11 pr-4 py-3 text-sm text-slate-900 bg-slate-50 border border-slate-300 rounded-lg focus:ring-2 focus:ring-slate-900 focus:border-slate-900 focus:bg-white transition placeholder-slate-400"
                />
              </div>
            </div>

            <div className="pt-2">
              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full flex justify-center items-center py-3.5 px-4 rounded-lg text-sm font-semibold text-white bg-slate-900 hover:bg-slate-800 active:scale-[0.99] disabled:opacity-50 shadow-md transition"
              >
                {isSubmitting ? (
                  <span>Memverifikasi akun...</span>
                ) : (
                  <>
                    <span>Masuk ke Sistem</span>
                    <ArrowRight className="w-4 h-4 ml-2" />
                  </>
                )}
              </button>
            </div>
          </form>

          {/* Quick Preset Selector */}
          <div className="mt-8 pt-6 border-t border-slate-200">
            <span className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
              Akun Uji Coba Cepat (Demo Presets):
            </span>
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => handleFillDemo('student')}
                className="p-3 text-left rounded-lg border border-slate-200 bg-slate-50 hover:bg-slate-100 hover:border-slate-300 transition text-slate-800"
              >
                <div className="font-semibold text-xs text-slate-900">Mahasiswa</div>
                <div className="text-xs text-slate-600 font-mono mt-1">INF24001</div>
              </button>
              <button
                type="button"
                onClick={() => handleFillDemo('lecturer')}
                className="p-3 text-left rounded-lg border border-slate-200 bg-slate-50 hover:bg-slate-100 hover:border-slate-300 transition text-slate-800"
              >
                <div className="font-semibold text-xs text-slate-900">Dosen / Pejabat</div>
                <div className="text-xs text-slate-600 font-mono mt-1 truncate">19800101...</div>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default LoginPage;
