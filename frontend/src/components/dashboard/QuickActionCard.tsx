import React from 'react';
import { Plus, Sparkles, ArrowRight } from 'lucide-react';

interface QuickActionCardProps {
  onNavigateToBuatSurat: () => void;
}

export const QuickActionCard: React.FC<QuickActionCardProps> = ({ onNavigateToBuatSurat }) => {
  return (
    <div className="bg-gradient-to-r from-slate-900 to-slate-800 rounded-2xl p-5 sm:p-6 text-white shadow-xs flex flex-col md:flex-row items-start md:items-center justify-between gap-4 border border-slate-700/80">
      <div className="space-y-1.5 max-w-2xl">
        <div className="inline-flex items-center space-x-1.5 px-2.5 py-0.5 rounded-full bg-blue-500/20 text-blue-200 border border-blue-400/30 text-[10px] font-semibold tracking-wide uppercase">
          <Sparkles className="w-3 h-3 text-blue-300" />
          <span>Layanan Persuratan Mandiri</span>
        </div>
        <h2 className="text-base sm:text-lg font-bold tracking-tight text-white">
          Buat Permohonan Surat Baru
        </h2>
        <p className="text-xs font-normal text-slate-300 leading-relaxed">
          Ajukan surat keterangan aktif kuliah, izin riset observasi, rekomendasi magang, atau jenis naskah dinas resmi lainnya melalui formulir mandiri terstruktur atau bantuan percakapan Sesi Chat AI.
        </p>
      </div>

      <button
        onClick={onNavigateToBuatSurat}
        className="w-full sm:w-auto px-5 py-2.5 rounded-xl bg-white text-slate-900 text-xs font-semibold hover:bg-slate-100 active:scale-95 transition-all duration-150 shadow-sm flex items-center justify-center space-x-2 shrink-0 ts-btn cursor-pointer"
        aria-label="Navigasi ke formulir buat surat baru"
      >
        <Plus className="w-4 h-4 text-slate-900" />
        <span>Mulai Pengajuan Surat</span>
        <ArrowRight className="w-3.5 h-3.5 text-slate-500" />
      </button>
    </div>
  );
};

export default QuickActionCard;
