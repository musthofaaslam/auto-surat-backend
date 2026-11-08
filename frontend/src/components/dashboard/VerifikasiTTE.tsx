import React, { useState } from 'react';
import suratService from '../../services/suratService';
import { extractErrorMessage } from '../../services/api';
import type { VerificationData } from '../../types';
import {
  ShieldCheck,
  ShieldAlert,
  Search,
  RefreshCw,
  ArrowRight,
  AlertCircle,
} from 'lucide-react';

export const VerifikasiTTE: React.FC = () => {
  const [verifyTokenInput, setVerifyTokenInput] = useState<string>('');
  const [verifyResult, setVerifyResult] = useState<VerificationData | null>(null);
  const [isVerifying, setIsVerifying] = useState<boolean>(false);
  const [verifyErrorMsg, setVerifyErrorMsg] = useState<string | null>(null);

  const handleVerifySubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!verifyTokenInput.trim()) return;

    setIsVerifying(true);
    setVerifyErrorMsg(null);
    setVerifyResult(null);

    try {
      const cleanToken = verifyTokenInput.trim();
      const res = await suratService.verifySurat(cleanToken);
      setVerifyResult(res);
    } catch (err) {
      setVerifyErrorMsg(
        extractErrorMessage(
          err,
          'Gagal memverifikasi dokumen. Pastikan token yang Anda masukkan benar.'
        )
      );
    } finally {
      setIsVerifying(false);
    }
  };

  return (
    <section
      aria-label="Verifikasi Keaslian TTE Dokumen"
      className="w-full bg-white border border-slate-200/90 rounded-2xl shadow-xs p-6 sm:p-8 space-y-6"
    >
      {/* Header */}
      <div className="border-b border-slate-100 pb-4">
        <div className="flex items-center space-x-2.5 mb-1.5">
          <ShieldCheck className="w-5 h-5 text-emerald-600" />
          <h1 className="text-base sm:text-lg font-semibold text-slate-900 tracking-tight">
            Verifikasi Keaslian TTE Dokumen
          </h1>
        </div>
        <p className="text-xs font-normal text-slate-500 leading-relaxed">
          Pusat validasi keabsahan dokumen persuratan dinas akademik. Masukkan kode token verifikasi
          atau nomor dokumen surat yang tertera pada naskah fisik maupun digital.
        </p>
      </div>

      {/* Search Form */}
      <form onSubmit={handleVerifySubmit} className="max-w-2xl space-y-3">
        <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider">
          Token / Kode Verifikasi Dokumen
        </label>
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
          <div className="relative flex-1">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
              <Search className="w-4 h-4" />
            </div>
            <input
              type="text"
              value={verifyTokenInput}
              onChange={(e) => setVerifyTokenInput(e.target.value)}
              placeholder="Contoh token: TTE-2026-X8910AB atau UUID TTE"
              className="w-full pl-9 pr-3 py-2.5 text-xs font-normal border border-slate-300 rounded-lg bg-white text-slate-900 focus:border-slate-900 focus:ring-1 focus:ring-slate-900 focus:outline-none transition shadow-2xs"
              required
            />
          </div>
          <button
            type="submit"
            disabled={isVerifying || !verifyTokenInput.trim()}
            className="px-5 py-2.5 rounded-lg bg-slate-900 text-white text-xs font-semibold hover:bg-slate-800 disabled:opacity-50 transition shadow-xs flex items-center justify-center space-x-2 shrink-0 cursor-pointer"
          >
            {isVerifying ? (
              <>
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                <span>Memvalidasi...</span>
              </>
            ) : (
              <>
                <span>Periksa Keabsahan</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </>
            )}
          </button>
        </div>
      </form>

      {verifyErrorMsg && (
        <div className="max-w-2xl p-4 rounded-xl bg-rose-50 border border-rose-200 text-xs font-normal text-rose-800 flex items-start space-x-2.5">
          <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
          <div>{verifyErrorMsg}</div>
        </div>
      )}

      {/* Verification Result Card */}
      {verifyResult && (
        <div className="max-w-2xl pt-2">
          {verifyResult.status === 'VALID' ? (
            <div className="border border-emerald-300 bg-white rounded-2xl p-5 shadow-xs space-y-4">
              <div className="flex items-center space-x-3 border-b border-emerald-100 pb-3">
                <div className="w-9 h-9 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center shrink-0">
                  <ShieldCheck className="w-5 h-5" />
                </div>
                <div>
                  <div className="text-xs font-semibold text-emerald-950 uppercase tracking-wider">
                    Dokumen Sah & Terverifikasi
                  </div>
                  <div className="text-[11px] font-normal text-emerald-800">
                    {verifyResult.message}
                  </div>
                </div>
              </div>

              {verifyResult.detail_surat && (
                <div className="space-y-2">
                  <div className="text-xs font-semibold text-slate-800 uppercase tracking-wider">
                    Rincian Dokumen Resmi
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                    <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                      <div className="text-[10px] font-normal text-slate-400">Nomor Surat Resmi</div>
                      <div className="font-semibold text-slate-900 mt-0.5">
                        {verifyResult.detail_surat.nomor_surat_resmi || '-'}
                      </div>
                    </div>
                    <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                      <div className="text-[10px] font-normal text-slate-400">Jenis Dokumen</div>
                      <div className="font-semibold text-slate-900 mt-0.5">
                        {verifyResult.detail_surat.jenis_surat}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {verifyResult.mahasiswa && (
                <div className="space-y-2 pt-2 border-t border-slate-100">
                  <div className="text-xs font-semibold text-slate-800 uppercase tracking-wider">
                    Identitas Mahasiswa Pemohon
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                    <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                      <div className="text-[10px] font-normal text-slate-400">Nama Lengkap</div>
                      <div className="font-semibold text-slate-900 mt-0.5">
                        {verifyResult.mahasiswa.nama}
                      </div>
                    </div>
                    <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                      <div className="text-[10px] font-normal text-slate-400">NIM & Program Studi</div>
                      <div className="font-semibold text-slate-900 mt-0.5">
                        {verifyResult.mahasiswa.nim} • {verifyResult.mahasiswa.prodi}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {verifyResult.tte_info && (
                <div className="space-y-2 pt-2 border-t border-slate-100">
                  <div className="text-xs font-semibold text-slate-800 uppercase tracking-wider">
                    Integritas Kriptografi TTE
                  </div>
                  <div className="p-3 rounded-lg bg-slate-900 text-white text-xs space-y-1">
                    <div className="text-[10px] font-normal text-slate-400">
                      Penandatangan:{' '}
                      <span className="text-white font-semibold">
                        {verifyResult.tte_info.penandatangan}
                      </span>
                    </div>
                    <div className="text-[10px] font-normal text-slate-400 truncate">
                      Hash SHA-256:{' '}
                      <span className="text-emerald-400 font-normal">
                        {verifyResult.tte_info.hash_sha256}
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="border border-rose-300 bg-rose-50/60 rounded-2xl p-5 shadow-xs space-y-3">
              <div className="flex items-center space-x-3">
                <div className="w-9 h-9 rounded-full bg-rose-100 text-rose-700 flex items-center justify-center shrink-0">
                  <ShieldAlert className="w-5 h-5" />
                </div>
                <div>
                  <div className="text-xs font-semibold text-rose-950 uppercase tracking-wider">
                    Verifikasi Gagal / Dokumen Palsu
                  </div>
                  <div className="text-[11px] font-normal text-rose-800">
                    {verifyResult.message}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
};

export default VerifikasiTTE;
