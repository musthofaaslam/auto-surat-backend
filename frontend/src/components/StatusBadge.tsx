import React from 'react';
import type { SuratStatusCode } from '../types';

interface StatusBadgeProps {
  status: SuratStatusCode | string;
  size?: 'xs' | 'sm' | 'md';
  showDot?: boolean;
}

// Architectural Note:
// Zero-emoji semantic status tokens. Uses crisp 1px borders, subtle tints,
// monospace metadata indicators, and micro-pulse on actively changing states.

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status,
  size = 'md',
  showDot = true,
}) => {
  const sizeClasses =
    size === 'xs'
      ? 'px-1.5 py-0.5 text-[10px]'
      : size === 'sm'
      ? 'px-2 py-0.5 text-xs'
      : 'px-2.5 py-1 text-xs';

  switch (status) {
    case 'SUBMITTED':
      return (
        <span
          className={`inline-flex items-center font-medium rounded-md bg-slate-100 text-slate-700 border border-slate-300 ${sizeClasses}`}
        >
          {showDot && (
            <span className="w-1.5 h-1.5 rounded-full bg-slate-500 mr-1.5 animate-pulse shrink-0"></span>
          )}
          <span>DIAJUKAN (SUBMITTED)</span>
        </span>
      );
    case 'REVISION_REQUIRED':
      return (
        <span
          className={`inline-flex items-center font-medium rounded-md bg-amber-50 text-amber-800 border border-amber-300 ${sizeClasses}`}
        >
          {showDot && <span className="w-1.5 h-1.5 rounded-full bg-amber-600 mr-1.5 shrink-0"></span>}
          <span>REVISI DIPERLUKAN</span>
        </span>
      );
    case 'PENDING_APPROVAL':
      return (
        <span
          className={`inline-flex items-center font-medium rounded-md bg-blue-50 text-blue-800 border border-blue-300 ${sizeClasses}`}
        >
          {showDot && <span className="w-1.5 h-1.5 rounded-full bg-blue-600 mr-1.5 shrink-0"></span>}
          <span>MENUNGGU PERSETUJUAN</span>
        </span>
      );
    case 'IN_REVIEW':
      return (
        <span
          className={`inline-flex items-center font-medium rounded-md bg-sky-50 text-sky-800 border border-sky-300 ${sizeClasses}`}
        >
          {showDot && (
            <span className="w-1.5 h-1.5 rounded-full bg-sky-600 mr-1.5 animate-pulse shrink-0"></span>
          )}
          <span>DALAM PENINJAUAN BERJENJANG</span>
        </span>
      );
    case 'APPROVED':
      return (
        <span
          className={`inline-flex items-center font-medium rounded-md bg-emerald-50 text-emerald-800 border border-emerald-300 ${sizeClasses}`}
        >
          {showDot && <span className="w-1.5 h-1.5 rounded-full bg-emerald-600 mr-1.5 shrink-0"></span>}
          <span>DISETUJUI</span>
        </span>
      );
    case 'REJECTED':
      return (
        <span
          className={`inline-flex items-center font-medium rounded-md bg-rose-50 text-rose-800 border border-rose-300 ${sizeClasses}`}
        >
          {showDot && <span className="w-1.5 h-1.5 rounded-full bg-rose-600 mr-1.5 shrink-0"></span>}
          <span>DITOLAK</span>
        </span>
      );
    case 'SENT':
      return (
        <span
          className={`inline-flex items-center font-medium rounded-md bg-teal-50 text-teal-800 border border-teal-300 ${sizeClasses}`}
        >
          {showDot && <span className="w-1.5 h-1.5 rounded-full bg-teal-600 mr-1.5 shrink-0"></span>}
          <span>TERKIRIM</span>
        </span>
      );
    case 'PRINTED':
      return (
        <span
          className={`inline-flex items-center font-medium rounded-md bg-indigo-50 text-indigo-800 border border-indigo-300 ${sizeClasses}`}
        >
          {showDot && <span className="w-1.5 h-1.5 rounded-full bg-indigo-600 mr-1.5 shrink-0"></span>}
          <span>DICETAK</span>
        </span>
      );
    case 'FAILED':
      return (
        <span
          className={`inline-flex items-center font-medium rounded-md bg-red-50 text-red-800 border border-red-300 ${sizeClasses}`}
        >
          {showDot && <span className="w-1.5 h-1.5 rounded-full bg-red-600 mr-1.5 shrink-0"></span>}
          <span>GAGAL</span>
        </span>
      );
    default:
      return (
        <span
          className={`inline-flex items-center font-medium rounded-md bg-slate-100 text-slate-700 border border-slate-300 ${sizeClasses}`}
        >
          {status}
        </span>
      );
  }
};

export default StatusBadge;

