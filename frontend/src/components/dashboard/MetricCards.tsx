import React from 'react';
import type { SuratRequestListItem } from '../../types';
import { FileText, Clock, CheckCircle2 } from 'lucide-react';

interface MetricCardsProps {
  requests: SuratRequestListItem[];
  isLoading?: boolean;
}

export const MetricCards: React.FC<MetricCardsProps> = ({ requests, isLoading = false }) => {
  const totalCount = requests.length;
  const pendingCount = requests.filter(
    (r) => r.status === 'PENDING_APPROVAL' || r.status === 'IN_REVIEW' || r.status === 'SUBMITTED'
  ).length;
  const publishedCount = requests.filter(
    (r) => r.status === 'APPROVED' || r.status === 'SENT' || r.status === 'PRINTED'
  ).length;

  const metrics = [
    {
      id: 'total',
      label: 'Total Surat',
      value: totalCount,
      subtext: 'Seluruh berkas terdaftar',
      icon: FileText,
      iconColor: 'text-slate-800',
      bgColor: 'bg-slate-100',
      badgeColor: 'bg-slate-100 text-slate-700',
    },
    {
      id: 'pending',
      label: 'Menunggu Persetujuan',
      value: pendingCount,
      subtext: 'Dalam antrean verifikasi dosen',
      icon: Clock,
      iconColor: 'text-amber-600',
      bgColor: 'bg-amber-50',
      badgeColor: 'bg-amber-50 text-amber-700 border border-amber-200/80',
    },
    {
      id: 'published',
      label: 'Terbit',
      value: publishedCount,
      subtext: 'Dokumen bertanda tangan sah',
      icon: CheckCircle2,
      iconColor: 'text-emerald-600',
      bgColor: 'bg-emerald-50',
      badgeColor: 'bg-emerald-50 text-emerald-700 border border-emerald-200/80',
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      {metrics.map((m) => {
        const IconComponent = m.icon;
        return (
          <div
            key={m.id}
            className="bg-white border border-slate-200/90 rounded-2xl p-5 shadow-xs transition-all duration-150 hover:border-slate-300 hover:shadow-sm flex flex-col justify-between"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                {m.label}
              </span>
              <div
                className={`w-9 h-9 rounded-xl ${m.bgColor} flex items-center justify-center shrink-0 shadow-2xs`}
              >
                <IconComponent className={`w-4 h-4 ${m.iconColor}`} />
              </div>
            </div>

            <div className="mt-4">
              <div className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900 leading-tight">
                {isLoading ? (
                  <span className="inline-block w-12 h-7 bg-slate-200 animate-pulse rounded" />
                ) : (
                  m.value
                )}
              </div>
              <p className="text-[11px] font-normal text-slate-500 mt-1">
                {m.subtext}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default MetricCards;
