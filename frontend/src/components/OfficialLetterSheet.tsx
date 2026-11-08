import React from 'react';
import type { SuratRequestDetail } from '../types';
import { ShieldCheck, QrCode } from 'lucide-react';

interface OfficialLetterSheetProps {
  detail: SuratRequestDetail;
  contentOverride?: string;
  isEditable?: boolean;
  onContentChange?: (val: string) => void;
}

// Architectural Note (Taste-Skill 2.5 - Product at True Size):
// Renders the official academic letter in authentic Indonesian government/university
// tata naskah dinas format. Includes formal institutional letterhead (kop surat),
// hierarchical reference numbers, student credential table, and verified cryptographic TTE seal.

export const OfficialLetterSheet: React.FC<OfficialLetterSheetProps> = ({
  detail,
  contentOverride,
  isEditable = false,
  onContentChange,
}) => {
  const content =
    contentOverride !== undefined
      ? contentOverride
      : detail.final_approved_content || detail.ai_original_draft || '';

  const activeSigner = detail.signatures && detail.signatures.length > 0 ? detail.signatures[0] : null;

  return (
    <div className="official-letter-sheet p-8 sm:p-12 md:p-14 border border-slate-300 rounded-lg max-w-3xl mx-auto shadow-md relative overflow-hidden bg-white text-slate-900">
      {/* Official Watermark / Subdued Institutional Crest */}
      <div className="absolute inset-0 flex items-center justify-center opacity-[0.025] pointer-events-none select-none">
        <div className="w-96 h-96 rounded-full border-12 border-slate-900 flex items-center justify-center font-bold text-6xl font-serif">
          UNIVERSITAS
        </div>
      </div>

      {/* 1. KOP SURAT RESMI DINAS */}
      <div className="text-center pb-4 relative">
        <div className="text-xs sm:text-sm font-semibold tracking-wider uppercase text-slate-800 font-sans">
          Kementerian Pendidikan Tinggi, Sains, dan Teknologi
        </div>
        <div className="text-base sm:text-lg font-bold tracking-tight uppercase text-slate-900 font-sans mt-0.5">
          Universitas Terbuka Indonesia
        </div>
        <div className="text-xs sm:text-sm font-semibold tracking-wide uppercase text-slate-800 font-sans">
          {detail.fakultas_mahasiswa || 'Fakultas Ilmu Komputer'}
        </div>
        <div className="text-[11px] text-slate-600 font-sans mt-1">
          Jl. Kampus Merdeka No. 1, Kota Akademik 14045 • Laman: https://kampus.example.ac.id
        </div>

        {/* Double Border Rule (Thick top, Thin bottom) */}
        <div className="mt-3 border-t-2 border-slate-900 pt-0.5">
          <div className="border-t border-slate-900"></div>
        </div>
      </div>

      {/* 2. NOMOR & JUDUL SURAT */}
      <div className="text-center my-6 space-y-1">
        <div className="text-sm sm:text-base font-bold uppercase tracking-wider underline text-slate-900">
          {detail.nama_surat || 'SURAT KETERANGAN RESMI'}
        </div>
        <div className="text-xs sm:text-sm font-mono text-slate-700">
          Nomor: {detail.nomor_surat_resmi || `B/${detail.id}/UN.FK/${detail.kode_surat}/${new Date().getFullYear()}`}
        </div>
      </div>

      {/* 3. PARAGRAF PEMBUKA */}
      <div className="text-xs sm:text-sm text-justify leading-relaxed text-slate-800 mb-4">
        Yang bertanda tangan di bawah ini, Pimpinan {detail.fakultas_mahasiswa || 'Fakultas'} Universitas, menerangkan dengan sebenarnya bahwa:
      </div>

      {/* 4. TABEL IDENTITAS MAHASISWA PEMOHON */}
      <div className="my-4 px-2 sm:px-6">
        <table className="w-full text-xs sm:text-sm font-serif">
          <tbody>
            <tr className="border-b border-slate-100/60">
              <td className="py-1.5 w-44 font-semibold text-slate-900">Nama Lengkap</td>
              <td className="py-1.5 w-4 text-center">:</td>
              <td className="py-1.5 font-bold text-slate-900">{detail.nama_mahasiswa}</td>
            </tr>
            <tr className="border-b border-slate-100/60">
              <td className="py-1.5 font-semibold text-slate-900">Nomor Induk Mahasiswa (NIM)</td>
              <td className="py-1.5 text-center">:</td>
              <td className="py-1.5 font-mono font-medium text-slate-800">{detail.nim_mahasiswa}</td>
            </tr>
            <tr className="border-b border-slate-100/60">
              <td className="py-1.5 font-semibold text-slate-900">Program Studi</td>
              <td className="py-1.5 text-center">:</td>
              <td className="py-1.5 text-slate-800">{detail.prodi_mahasiswa}</td>
            </tr>
            <tr className="border-b border-slate-100/60">
              <td className="py-1.5 font-semibold text-slate-900">Fakultas</td>
              <td className="py-1.5 text-center">:</td>
              <td className="py-1.5 text-slate-800">{detail.fakultas_mahasiswa}</td>
            </tr>
            {detail.payload_data && Object.entries(detail.payload_data).slice(0, 3).map(([k, v]) => (
              <tr key={k} className="border-b border-slate-100/60">
                <td className="py-1.5 font-semibold text-slate-900 capitalize">
                  {k.replace(/_/g, ' ')}
                </td>
                <td className="py-1.5 text-center">:</td>
                <td className="py-1.5 text-slate-800">{v === null ? '-' : String(v)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 5. ISI NASKAH SURAT DINAS (EDITABLE OR STATIC) */}
      <div className="my-6">
        {isEditable ? (
          <div>
            <label className="block text-[11px] font-sans font-semibold text-slate-500 mb-1 uppercase tracking-wider">
              Isi Naskah Draf (Dapat Diedit Dosen Peninjau):
            </label>
            <textarea
              rows={8}
              value={content}
              onChange={(e) => onContentChange?.(e.target.value)}
              className="w-full p-3 font-serif text-xs sm:text-sm border border-slate-300 rounded bg-slate-50/50 focus:bg-white focus:ring-1 focus:ring-slate-900 leading-relaxed text-slate-900 text-justify"
              placeholder="Ketik atau edit isi kalimat surat..."
            />
          </div>
        ) : (
          <div className="text-xs sm:text-sm text-justify leading-relaxed whitespace-pre-wrap text-slate-800">
            {content || 'Isi naskah resmi sedang diproses oleh agen AI.'}
          </div>
        )}
      </div>

      {/* 6. PARAGRAF PENUTUP */}
      <div className="text-xs sm:text-sm text-justify leading-relaxed text-slate-800 my-4">
        Demikian surat keterangan ini diterbitkan secara sah untuk dipergunakan sebagaimana mestinya dengan penuh tanggung jawab.
      </div>

      {/* 7. KOLOM TANDA TANGAN ELEKTRONIK (TTE) */}
      <div className="mt-10 pt-4 flex flex-col sm:flex-row items-end justify-between gap-6">
        <div className="w-full sm:w-auto text-left">
          {/* TTE QR & Security Verification Stamp */}
          <div className="tte-digital-seal p-3 rounded-lg flex items-center space-x-3 text-emerald-900 max-w-xs">
            <div className="w-12 h-12 bg-white rounded border border-emerald-300 flex items-center justify-center shrink-0 shadow-2xs">
              <QrCode className="w-9 h-9 text-slate-800" />
            </div>
            <div className="text-[10px] font-sans leading-tight">
              <div className="font-bold flex items-center text-emerald-800">
                <ShieldCheck className="w-3 h-3 mr-1 text-emerald-600" />
                <span>TERVERIFIKASI TTE</span>
              </div>
              <div className="text-slate-500 mt-0.5 font-mono text-[9px] truncate max-w-[170px]">
                Token: {activeSigner?.token || detail.qr_verification_code || 'VERIF-AI-2026'}
              </div>
              <div className="text-slate-400 text-[9px] mt-0.5">
                Pindai QR untuk uji keabsahan
              </div>
            </div>
          </div>
        </div>

        <div className="w-full sm:w-64 text-center sm:text-right font-sans">
          <div className="text-xs text-slate-600">
            Kota Akademik,{' '}
            {new Date(detail.created_at).toLocaleDateString('id-ID', {
              day: 'numeric',
              month: 'long',
              year: 'numeric',
            })}
          </div>
          <div className="text-xs font-semibold text-slate-800 mt-1">
            a.n. Dekan Fakultas,
          </div>
          <div className="text-xs text-slate-600">
            Pejabat Berwenang / Koordinator
          </div>

          <div className="my-4 h-12 flex items-center justify-center sm:justify-end">
            <span className="font-serif italic text-slate-400 text-xs select-none">
              [Telah Ditandatangani Secara Elektronik]
            </span>
          </div>

          <div className="text-xs font-bold text-slate-900 underline font-serif">
            {activeSigner?.signer_name || 'Dr. Dosen Akademik, M.Kom.'}
          </div>
          <div className="text-[11px] font-mono text-slate-600">
            NIP: {activeSigner?.signer_nip || '198001012005011001'}
          </div>
        </div>
      </div>
    </div>
  );
};

export default OfficialLetterSheet;
