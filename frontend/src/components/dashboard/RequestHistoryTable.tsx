import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import type { SuratRequestListItem } from '../../types';
import StatusBadge from '../StatusBadge';
import { Clock, RefreshCw, FileText } from 'lucide-react';

interface RequestHistoryTableProps {
  requests: SuratRequestListItem[];
  isLoading?: boolean;
  onRefresh: () => void;
}

export const RequestHistoryTable: React.FC<RequestHistoryTableProps> = ({
  requests,
  isLoading = false,
  onRefresh,
}) => {
  const [filter, setFilter] = useState<'ALL' | 'PENDING' | 'DONE'>('ALL');

  const filteredRequests = requests.filter((req) => {
    if (filter === 'PENDING') {
      return (
        req.status === 'PENDING_APPROVAL' ||
        req.status === 'IN_REVIEW' ||
        req.status === 'SUBMITTED'
      );
    }
    if (filter === 'DONE') {
      return (
        req.status === 'APPROVED' || req.status === 'SENT' || req.status === 'PRINTED'
      );
    }
    return true;
  });

  return (
    <section
      aria-label="Riwayat Permohonan Naskah Dinas"
      className="w-full bg-white border border-slate-200/90 rounded-2xl shadow-xs p-5 sm:p-6 space-y-4"
    >
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-3 border-b border-slate-100 gap-3">
        <div className="flex items-center space-x-2.5">
          <div className="w-8 h-8 rounded-lg bg-slate-100 text-slate-800 flex items-center justify-center shrink-0">
            <Clock className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h2 className="text-xs font-semibold text-slate-900 uppercase tracking-wider">
                Riwayat Permohonan Naskah Dinas
              </h2>
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-700 font-semibold">
                {requests.length} Berkas
              </span>
            </div>
            <p className="text-[11px] text-slate-500 font-normal mt-0.5">
              Daftar seluruh berkas permohonan surat, status verifikasi berjenjang, dan tanda tangan elektronik resmi.
            </p>
          </div>
        </div>

        {/* Quick Refresh Button */}
        <button
          onClick={onRefresh}
          disabled={isLoading}
          className="self-start sm:self-auto px-3 py-1.5 rounded-lg border border-slate-200 text-slate-700 text-xs hover:bg-slate-50 transition-colors flex items-center space-x-1.5 ts-btn cursor-pointer"
          title="Segarkan data riwayat permohonan"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          <span>Segarkan</span>
        </button>
      </div>

      {/* Filter Status Pills */}
      <div className="flex items-center space-x-1.5 overflow-x-auto pb-1">
        {(['ALL', 'PENDING', 'DONE'] as const).map((filterKey) => {
          const labels: Record<string, string> = {
            ALL: 'Semua Berkas',
            PENDING: 'Menunggu Persetujuan',
            DONE: 'Diterbitkan / Selesai',
          };
          const isActive = filter === filterKey;
          return (
            <button
              key={filterKey}
              onClick={() => setFilter(filterKey)}
              className={`px-3 py-1 rounded-lg text-xs transition-all duration-150 whitespace-nowrap cursor-pointer ${
                isActive
                  ? 'bg-slate-900 text-white font-semibold shadow-2xs'
                  : 'bg-slate-100/80 text-slate-600 hover:bg-slate-200/80 hover:text-slate-900 font-normal'
              }`}
            >
              {labels[filterKey]}
            </button>
          );
        })}
      </div>

      {/* Request Items List */}
      {filteredRequests.length > 0 ? (
        <div className="border border-slate-200/90 rounded-xl overflow-hidden divide-y divide-slate-100 bg-white shadow-2xs">
          {filteredRequests.map((req) => (
            <div
              key={req.id}
              className="p-3.5 sm:p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 hover:bg-slate-50/80 transition-all duration-150 group"
            >
              <div className="space-y-1 min-w-0">
                <div className="flex items-center space-x-2">
                  <span className="text-[11px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 font-semibold group-hover:bg-slate-900 group-hover:text-white transition-colors shrink-0">
                    {req.kode_surat}
                  </span>
                  <span className="text-xs font-semibold text-slate-900 truncate">
                    {req.nama_surat}
                  </span>
                </div>
                <div className="text-[11px] font-normal text-slate-400 flex items-center space-x-2">
                  <span>ID: #{req.id}</span>
                  <span>•</span>
                  <span>
                    Dibuat:{' '}
                    {new Date(req.created_at).toLocaleDateString('id-ID', {
                      day: 'numeric',
                      month: 'short',
                      year: 'numeric',
                    })}
                  </span>
                </div>
              </div>

              <div className="flex items-center space-x-3 self-end sm:self-center shrink-0">
                <StatusBadge status={req.status} />
                <Link
                  to={`/surat/${req.id}`}
                  className="px-3 py-1.5 text-xs font-medium text-slate-700 bg-slate-100 hover:bg-slate-900 hover:text-white rounded-lg transition-all duration-150 ts-btn cursor-pointer"
                >
                  Lihat Detail
                </Link>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="p-8 text-center border border-dashed border-slate-200 rounded-xl space-y-2">
          <FileText className="w-8 h-8 text-slate-300 mx-auto" />
          <div className="text-xs font-semibold text-slate-700">Tidak ada berkas permohonan surat</div>
          <p className="text-[11px] text-slate-400 max-w-sm mx-auto">
            {filter === 'ALL'
              ? 'Belum ada data permohonan naskah dinas. Silakan gunakan menu Buat Surat untuk mengajukan permohonan pertama Anda.'
              : 'Tidak ada berkas dengan status filter yang dipilih.'}
          </p>
        </div>
      )}
    </section>
  );
};

export default RequestHistoryTable;
