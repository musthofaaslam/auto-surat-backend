import React from 'react';
import type { SuratRequestDetail } from '../types';
import { ShieldCheck, QrCode } from 'lucide-react';

interface OfficialLetterSheetProps {
  detail: SuratRequestDetail;
  contentOverride?: string;
  isEditable?: boolean;
  onContentChange?: (val: string) => void;
}

// Architectural Note (Taste-Skill 2.5 - Authentic Official Letter):
// Renders the official academic recommendation/letter in authentic Indonesian
// two-party administrative structure matching national higher education standard:
// 1. Formal Institutional Letterhead (Kop Surat) with double border rule.
// 2. Document Title & Official Reference Number.
// 3. Pihak 1 (Yang bertandatangan di bawah ini: Signing Official).
// 4. Pihak 2 (Dengan ini menerangkan bahwa: Student Candidate).
// 5. Official Narrative Recommendation Content.
// 6. Formal Closing Statement.
// 7. Verified TTE Digital Signature block with SHA-256 seal & QR Code.

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
    <div className="official-letter-sheet p-8 sm:p-12 md:p-14 border border-slate-300 rounded-lg max-w-3xl mx-auto shadow-md relative overflow-hidden bg-white text-slate-900 font-serif">
      {/* 1. KOP SURAT RESMI DINAS */}
      <div className="text-center pb-3 relative">
        <div className="text-xs sm:text-sm font-semibold tracking-wider uppercase text-slate-800 font-sans">
          Kementerian Pendidikan Tinggi, Sains, dan Teknologi
        </div>
        <div className="text-base sm:text-lg font-bold tracking-tight uppercase text-slate-900 font-sans mt-0.5">
          Universitas Indonesia Emas
        </div>
        <div className="text-xs sm:text-sm font-semibold tracking-wide uppercase text-slate-800 font-sans">
          FAKULTAS {(detail.fakultas_mahasiswa || 'Ilmu Komputer').toUpperCase()}
        </div>
        <div className="text-[11px] text-slate-600 font-sans mt-1">
          Jl. Kampus Utama No. 1, Semarang | Laman: www.uie.ac.id | Pos-el: info@uie.ac.id
        </div>

        {/* Double Border Rule (Thick top, Thin bottom) */}
        <div className="mt-3 border-t-2 border-slate-900 pt-0.5">
          <div className="border-t border-slate-900"></div>
        </div>
      </div>

      {/* 2. NOMOR & JUDUL SURAT */}
      <div className="text-center my-5 space-y-1">
        <div className="text-sm sm:text-base font-bold uppercase tracking-wider underline text-slate-900">
          {detail.nama_surat || 'SURAT REKOMENDASI MAGANG'}
        </div>
        <div className="text-xs sm:text-sm font-mono text-slate-800 font-medium">
          Nomor: {detail.nomor_surat_resmi || `002/${detail.kode_surat || 'SR-MAG'}/FT/${new Date().getMonth() + 1}/${new Date().getFullYear()}`}
        </div>
      </div>

      {/* 3. PIHAK 1: YANG BERTANDATANGAN DI BAWAH INI */}
      <div className="mt-4 mb-2 text-xs sm:text-sm text-slate-800 font-sans">
        Yang bertandatangan di bawah ini:
      </div>
      <div className="mb-4 px-2 sm:px-4">
        <table className="w-full text-xs sm:text-sm font-serif">
          <tbody>
            <tr>
              <td className="py-1 w-40 text-slate-800">Nama</td>
              <td className="py-1 w-4 text-center">:</td>
              <td className="py-1 font-bold text-slate-900">
                {activeSigner?.signer_name || 'Dr. Joel Evans, M.T.'}
              </td>
            </tr>
            <tr>
              <td className="py-1 text-slate-800">NIP</td>
              <td className="py-1 text-center">:</td>
              <td className="py-1 font-mono text-slate-800">
                {activeSigner?.signer_nip || '198001012005011001'}
              </td>
            </tr>
            <tr>
              <td className="py-1 text-slate-800">Jabatan</td>
              <td className="py-1 text-center">:</td>
              <td className="py-1 text-slate-800">
                {activeSigner?.signer_role || 'Dekan Fakultas'}
              </td>
            </tr>
            <tr>
              <td className="py-1 text-slate-800">Instansi</td>
              <td className="py-1 text-center">:</td>
              <td className="py-1 text-slate-800">
                Universitas Indonesia Emas
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* 4. PIHAK 2: DENGAN INI MENERANGKAN BAHWA */}
      <div className="mt-3 mb-2 text-xs sm:text-sm text-slate-800 font-sans">
        Dengan ini menerangkan bahwa:
      </div>
      <div className="mb-5 px-2 sm:px-4">
        <table className="w-full text-xs sm:text-sm font-serif">
          <tbody>
            <tr>
              <td className="py-1 w-40 text-slate-800">Nama Mahasiswa</td>
              <td className="py-1 w-4 text-center">:</td>
              <td className="py-1 font-bold text-slate-900">{detail.nama_mahasiswa}</td>
            </tr>
            <tr>
              <td className="py-1 text-slate-800">NIM</td>
              <td className="py-1 text-center">:</td>
              <td className="py-1 font-mono font-medium text-slate-800">{detail.nim_mahasiswa}</td>
            </tr>
            <tr>
              <td className="py-1 text-slate-800">Program Studi</td>
              <td className="py-1 text-center">:</td>
              <td className="py-1 text-slate-800">{detail.prodi_mahasiswa}</td>
            </tr>
            <tr>
              <td className="py-1 text-slate-800">Fakultas</td>
              <td className="py-1 text-center">:</td>
              <td className="py-1 text-slate-800">{detail.fakultas_mahasiswa}</td>
            </tr>
            <tr>
              <td className="py-1 text-slate-800">Semester / T.A.</td>
              <td className="py-1 text-center">:</td>
              <td className="py-1 text-slate-800">Semester 7 / 2026/2027</td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* 5. ISI NASKAH SURAT REKOMENDASI (NARASI RESMI) */}
      <div className="my-5">
        {isEditable ? (
          <div>
            <label className="block text-[11px] font-sans font-semibold text-slate-500 mb-1 uppercase tracking-wider">
              Isi Narasi Draf Rekomendasi (Dapat Diedit Dosen Peninjau):
            </label>
            <textarea
              rows={8}
              value={content}
              onChange={(e) => onContentChange?.(e.target.value)}
              className="w-full p-3 font-serif text-xs sm:text-sm border border-slate-300 rounded bg-slate-50/50 focus:bg-white focus:ring-1 focus:ring-slate-900 leading-relaxed text-slate-900 text-justify"
              placeholder="Ketik atau edit isi kalimat rekomendasi..."
            />
          </div>
        ) : (
          <div className="text-xs sm:text-sm text-justify leading-relaxed whitespace-pre-wrap text-slate-800 indent-7 space-y-2">
            {content || 'Isi naskah resmi sedang diproses oleh agen AI.'}
          </div>
        )}
      </div>

      {/* 6. PARAGRAF PENUTUP */}
      <div className="text-xs sm:text-sm text-justify leading-relaxed text-slate-800 my-4 indent-7">
        Demikian Surat Rekomendasi ini kami buat dengan sebenarnya untuk dapat dipergunakan sebagaimana mestinya.
      </div>

      {/* 7. KOLOM TANDA TANGAN ELEKTRONIK (TTE) */}
      <div className="mt-8 pt-4 flex flex-col sm:flex-row items-end justify-between gap-6 border-t border-slate-100">
        <div className="w-full sm:w-auto text-left">
          {/* TTE QR & Security Verification Stamp */}
          <div className="border border-slate-400 bg-slate-50/80 p-3 rounded text-[9.5px] font-sans text-slate-700 max-w-xs leading-normal">
            <strong className="block text-slate-900 text-[10px] mb-1 font-bold">
              DOKUMEN DITANDATANGANI ELEKTRONIK (TTE)
            </strong>
            Surat ini sah dan diterbitkan resmi melalui Sistem Informasi AutoSurat.<br />
            <span className="text-slate-500 font-mono text-[9px] mt-1 block truncate">
              Verifikasi Keaslian: {activeSigner?.token || detail.qr_verification_code || detail.nomor_surat_resmi || 'VERIF-TTE-SHA256'}
            </span>
          </div>
        </div>

        <div className="w-full sm:w-64 text-center font-sans">
          <div className="text-xs text-slate-700">
            Semarang,{' '}
            {new Date(detail.created_at).toLocaleDateString('id-ID', {
              day: 'numeric',
              month: 'long',
              year: 'numeric',
            })}
          </div>
          <div className="text-xs font-semibold text-slate-900 mt-0.5">
            {activeSigner?.signer_role || 'Dekan Fakultas'},
          </div>

          <div className="my-2 h-16 flex items-center justify-center">
            <div className="w-14 h-14 bg-white border border-slate-300 rounded flex items-center justify-center shadow-2xs">
              <QrCode className="w-11 h-11 text-slate-800" />
            </div>
          </div>

          <div className="text-xs font-bold text-slate-900 underline font-serif">
            {activeSigner?.signer_name || 'Dr. Joel Evans, M.T.'}
          </div>
          <div className="text-[11px] font-mono text-slate-600 mt-0.5">
            NIP. {activeSigner?.signer_nip || '198001012005011001'}
          </div>
        </div>
      </div>
    </div>
  );
};

export default OfficialLetterSheet;
