import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import suratService from '../services/suratService';
import type { VerificationData } from '../types';
import {
  ShieldCheck,
  ShieldAlert,
  Search,
  FileText,
  User,
  Hash,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  ArrowLeft,
  Calendar,
  Building2,
  GraduationCap,
} from 'lucide-react';

export const VerifySuratPage: React.FC = () => {
  const { token: urlToken } = useParams<{ token?: string }>();
  const navigate = useNavigate();

  const [inputToken, setInputToken] = useState<string>(urlToken || '');
  const [data, setData] = useState<VerificationData | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const verifyToken = async (tokenToVerify: string) => {
    if (!tokenToVerify.trim()) return;

    setIsLoading(true);
    setErrorMessage(null);
    setData(null);

    try {
      const result = await suratService.verifySurat(tokenToVerify.trim());
      setData(result);
    } catch (err: any) {
      if (err.response?.status === 404) {
        setData({
          status: 'INVALID',
          message:
            'Dokumen Surat TIDAK VALID atau palsu. Token verifikasi tidak terdaftar pada repositori persuratan dinas resmi.',
        });
      } else {
        setErrorMessage(
          err.response?.data?.message || 'Gagal menghubungi server verifikasi dokumen persuratan.'
        );
      }
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (urlToken) {
      setInputToken(urlToken);
      verifyToken(urlToken);
    }
  }, [urlToken]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputToken.trim()) return;
    navigate(`/verify/${inputToken.trim()}`);
    verifyToken(inputToken.trim());
  };

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-10 sm:py-14 space-y-8">
      {/* Title Header */}
      <div className="text-center space-y-3">
        <Link
          to="/dashboard"
          className="inline-flex items-center text-xs font-semibold text-slate-500 hover:text-slate-900 transition px-3 py-1.5 rounded-md hover:bg-slate-100"
        >
          <ArrowLeft className="w-3.5 h-3.5 mr-1.5" />
          <span>Kembali ke Beranda Sistem</span>
        </Link>
        <div className="w-14 h-14 bg-slate-900 text-white rounded-2xl flex items-center justify-center mx-auto shadow-md border border-slate-800">
          <ShieldCheck className="w-7 h-7 text-emerald-400" />
        </div>
        <h1 className="text-2xl sm:text-3xl font-bold text-slate-900 tracking-tight">
          Verifikasi Publik Keaslian TTE Dokumen
        </h1>
        <p className="text-sm text-slate-600 max-w-xl mx-auto leading-relaxed">
          Pusat validasi keabsahan dokumen persuratan dinas akademik. Masukkan kode token verifikasi
          atau pindai QR Code TTE yang tertera pada naskah surat fisik/digital.
        </p>
      </div>

      {/* Search Token Input */}
      <form onSubmit={handleSubmit} className="ts-card p-4 sm:p-5 bg-white border border-slate-300 shadow-md">
        <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-2">
          Token / Kode Verifikasi Dokumen
        </label>
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
          <div className="relative flex-1">
            <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
              <Hash className="w-5 h-5" />
            </div>
            <input
              type="text"
              value={inputToken}
              onChange={(e) => setInputToken(e.target.value)}
              placeholder="Contoh: a1b2c3d4e5f67890..."
              className="block w-full pl-11 pr-4 py-3 text-sm border border-slate-300 rounded-lg focus:ring-2 focus:ring-slate-900 focus:border-slate-900 bg-slate-50 focus:bg-white placeholder-slate-400 font-mono transition"
            />
          </div>
          <button
            type="submit"
            disabled={isLoading || !inputToken.trim()}
            className="inline-flex justify-center items-center px-6 py-3 text-sm font-semibold text-white bg-slate-900 hover:bg-slate-800 disabled:opacity-50 rounded-lg shadow-sm transition shrink-0"
          >
            {isLoading ? (
              <RefreshCw className="w-4 h-4 animate-spin mr-2" />
            ) : (
              <Search className="w-4 h-4 mr-2" />
            )}
            <span>Verifikasi Dokumen</span>
          </button>
        </div>
      </form>

      {errorMessage && (
        <div className="p-4 rounded-xl bg-amber-50 border border-amber-300 text-sm text-amber-800 flex items-center space-x-3 shadow-sm">
          <AlertCircle className="w-5 h-5 shrink-0 text-amber-600" />
          <span className="font-medium">{errorMessage}</span>
        </div>
      )}

      {/* Verification Result Card */}
      {data && (
        <div
          className={`ts-card p-6 sm:p-8 bg-white border-2 shadow-lg space-y-6 ${
            data.status === 'VALID' ? 'border-emerald-500 ring-4 ring-emerald-50' : 'border-rose-500 ring-4 ring-rose-50'
          }`}
        >
          {/* Status Indicator */}
          <div className="flex items-center space-x-4 pb-6 border-b border-slate-200">
            {data.status === 'VALID' ? (
              <div className="w-14 h-14 rounded-2xl bg-emerald-100 text-emerald-700 flex items-center justify-center shrink-0 border border-emerald-300 shadow-sm">
                <CheckCircle2 className="w-8 h-8" />
              </div>
            ) : (
              <div className="w-14 h-14 rounded-2xl bg-rose-100 text-rose-700 flex items-center justify-center shrink-0 border border-rose-300 shadow-sm">
                <ShieldAlert className="w-8 h-8" />
              </div>
            )}
            <div>
              <div
                className={`text-base sm:text-lg font-bold tracking-tight uppercase ${
                  data.status === 'VALID' ? 'text-emerald-800' : 'text-rose-800'
                }`}
              >
                {data.status === 'VALID' ? 'DOKUMEN RESMI TERCATAT & TERVERIFIKASI' : 'DOKUMEN TIDAK TERVERIFIKASI'}
              </div>
              <p className="text-sm text-slate-600 mt-1 leading-relaxed">{data.message}</p>
            </div>
          </div>

          {/* Valid Details */}
          {data.status === 'VALID' && (
            <div className="space-y-6">
              {/* Surat Detail */}
              {data.detail_surat && (
                <div className="space-y-3">
                  <div className="flex items-center space-x-2 text-slate-800 font-bold uppercase tracking-wider text-xs">
                    <FileText className="w-4 h-4 text-indigo-600" />
                    <span>Rincian Naskah Dinas Resmi</span>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 bg-slate-50 p-4 sm:p-5 rounded-xl border border-slate-200">
                    <div>
                      <span className="text-slate-500 text-xs font-semibold uppercase tracking-wider block mb-1">
                        Nomor Surat Resmi
                      </span>
                      <span className="font-mono font-bold text-base text-slate-900">
                        {data.detail_surat.nomor_surat_resmi || '-'}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 text-xs font-semibold uppercase tracking-wider block mb-1">
                        Jenis Dokumen
                      </span>
                      <span className="font-bold text-sm text-slate-900">
                        {data.detail_surat.jenis_surat}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 text-xs font-semibold uppercase tracking-wider block mb-1">
                        Kategori Klasifikasi
                      </span>
                      <span className="text-sm text-slate-800">{data.detail_surat.kategori}</span>
                    </div>
                    <div>
                      <span className="text-slate-500 text-xs font-semibold uppercase tracking-wider block mb-1">
                        Tanggal Penerbitan
                      </span>
                      <div className="flex items-center text-sm text-slate-800 font-medium">
                        <Calendar className="w-3.5 h-3.5 mr-1.5 text-slate-400" />
                        <span>
                          {new Date(data.detail_surat.tanggal_terbit).toLocaleDateString('id-ID', {
                            day: 'numeric',
                            month: 'long',
                            year: 'numeric',
                          })}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Mahasiswa Info */}
              {data.mahasiswa && (
                <div className="space-y-3">
                  <div className="flex items-center space-x-2 text-slate-800 font-bold uppercase tracking-wider text-xs">
                    <User className="w-4 h-4 text-indigo-600" />
                    <span>Identitas Pemohon Dokumen</span>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 bg-slate-50 p-4 sm:p-5 rounded-xl border border-slate-200">
                    <div>
                      <span className="text-slate-500 text-xs font-semibold uppercase tracking-wider block mb-1">
                        Nama Lengkap Mahasiswa
                      </span>
                      <span className="font-bold text-sm text-slate-900">{data.mahasiswa.nama}</span>
                    </div>
                    <div>
                      <span className="text-slate-500 text-xs font-semibold uppercase tracking-wider block mb-1">
                        Nomor Induk Mahasiswa (NIM)
                      </span>
                      <span className="font-mono font-bold text-sm text-slate-900">
                        {data.mahasiswa.nim}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 text-xs font-semibold uppercase tracking-wider block mb-1">
                        Program Studi
                      </span>
                      <div className="flex items-center text-sm text-slate-800">
                        <GraduationCap className="w-3.5 h-3.5 mr-1.5 text-slate-400" />
                        <span>{data.mahasiswa.prodi}</span>
                      </div>
                    </div>
                    <div>
                      <span className="text-slate-500 text-xs font-semibold uppercase tracking-wider block mb-1">
                        Fakultas
                      </span>
                      <div className="flex items-center text-sm text-slate-800">
                        <Building2 className="w-3.5 h-3.5 mr-1.5 text-slate-400" />
                        <span>{data.mahasiswa.fakultas}</span>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* TTE Cryptographic Evidence */}
              {data.tte_info && (
                <div className="space-y-3">
                  <div className="flex items-center space-x-2 text-slate-800 font-bold uppercase tracking-wider text-xs">
                    <ShieldCheck className="w-4 h-4 text-emerald-600" />
                    <span>Bukti Kriptografis Tanda Tangan Elektronik (TTE)</span>
                  </div>
                  <div className="space-y-3 bg-emerald-50/50 p-4 sm:p-5 rounded-xl border border-emerald-200">
                    <div>
                      <span className="text-emerald-800 text-xs font-bold uppercase tracking-wider block mb-1">
                        Pejabat Penandatangan Sah
                      </span>
                      <span className="font-bold text-sm text-slate-900">
                        {data.tte_info.penandatangan}
                      </span>
                    </div>
                    <div>
                      <span className="text-emerald-800 text-xs font-bold uppercase tracking-wider block mb-1">
                        Integritas Naskah (SHA-256 Digest)
                      </span>
                      <div className="font-mono text-xs text-slate-900 bg-white p-3 rounded-lg break-all border border-emerald-300 shadow-inner">
                        {data.tte_info.hash_sha256}
                      </div>
                    </div>
                    <div>
                      <span className="text-emerald-800 text-xs font-bold uppercase tracking-wider block mb-1">
                        Stempel Waktu Penandatanganan (Timestamp)
                      </span>
                      <span className="text-slate-800 font-mono text-xs font-medium">
                        {new Date(data.tte_info.tanggal_ttd).toLocaleString('id-ID', {
                          dateStyle: 'full',
                          timeStyle: 'long',
                        })}
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default VerifySuratPage;
