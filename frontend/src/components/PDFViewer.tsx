import React from 'react';
import { FileText, Download, ExternalLink, ShieldCheck, Clock } from 'lucide-react';

interface PDFViewerProps {
  pdfUrl: string | null;
  nomorSurat?: string | null;
  documentTitle?: string;
  requestId?: number | string | null;
}

// Architectural Note (Taste-Skill 2.5):
// Robust PDF previewer providing native object & iframe presentation, direct download gateway,
// and informational placeholder when the document is still in pre-approval phase.
// Renders responsively at all breakpoints (1440, 1024, 768, 390).
// Prioritizes Internal Document Gateway (/surat/requests/:id/preview-pdf/) to achieve
// 100% reliable local preview & download with zero Cloudinary 401 dependency.

export const PDFViewer: React.FC<PDFViewerProps> = ({
  pdfUrl,
  nomorSurat,
  documentTitle = 'Dokumen Surat Resmi',
  requestId,
}) => {
  const resolvedId = React.useMemo(() => {
    if (requestId) return String(requestId);
    if (typeof window !== 'undefined') {
      const match = window.location.pathname.match(/\/surat\/(\d+)/);
      if (match && match[1]) return match[1];
    }
    return null;
  }, [requestId]);

  if (!pdfUrl && !resolvedId) {
    return (
      <div className="flex flex-col items-center justify-center p-8 sm:p-12 border-2 border-dashed border-slate-300 rounded-lg bg-slate-50/70 text-center tactile-card">
        <div className="w-12 h-12 bg-blue-50 text-blue-700 rounded-full flex items-center justify-center mb-3.5 border border-blue-200">
          <Clock className="w-6 h-6 animate-pulse" />
        </div>
        <h3 className="text-sm font-semibold text-slate-900">
          Naskah PDF Dalam Antrean Penerbitan
        </h3>
        <p className="text-xs text-slate-500 max-w-md mt-1.5 leading-relaxed">
          Dokumen PDF resmi berstandar tata naskah dinas, lengkap dengan Tanda Tangan Elektronik
          (TTE) terenkripsi SHA-256 dan QR Code verifikasi publik, akan digenerate otomatis
          segera setelah pejabat berwenang menyetujui draf ini.
        </p>
        <div className="mt-4 inline-flex items-center text-[11px] font-mono text-slate-600 bg-white px-3 py-1 rounded border border-slate-200">
          <ShieldCheck className="w-3.5 h-3.5 text-emerald-600 mr-1.5" />
          <span>Pipeline Fase 2 & 4 Otomatis Aktif Saat Approved</span>
        </div>
      </div>
    );
  }

  // Gunakan Internal Document Gateway bila ID request tersedia agar bebas dari kendala Cloudinary 401
  const previewUrl = resolvedId
    ? `/surat/requests/${resolvedId}/preview-pdf/`
    : (pdfUrl ? pdfUrl.replace(/fl_attachment\/?/g, '') : '');

  const downloadUrl = resolvedId
    ? `/surat/requests/${resolvedId}/download-pdf/`
    : (pdfUrl || '');

  return (
    <div className="flex flex-col h-full bg-white border border-slate-200 rounded-lg shadow-xs overflow-hidden tactile-card">
      {/* Top Action Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between px-4 py-3 bg-slate-50 border-b border-slate-200 gap-2">
        <div className="flex items-center space-x-2 truncate">
          <FileText className="w-4 h-4 text-slate-700 shrink-0" />
          <span className="text-xs font-semibold text-slate-900 truncate">
            {nomorSurat ? `Nomor: ${nomorSurat}` : documentTitle}
          </span>
        </div>
        <div className="flex items-center space-x-2 shrink-0">
          <a
            href={previewUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center px-3 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-300 rounded hover:bg-slate-50 shadow-2xs transition tactile-btn"
          >
            <ExternalLink className="w-3.5 h-3.5 mr-1 text-slate-500" />
            Buka Tab Baru
          </a>
          <a
            href={downloadUrl}
            download
            className="inline-flex items-center px-3 py-1.5 text-xs font-medium text-white bg-slate-900 rounded hover:bg-slate-800 shadow-xs transition tactile-btn"
          >
            <Download className="w-3.5 h-3.5 mr-1" />
            Unduh PDF
          </a>
        </div>
      </div>

      {/* PDF Viewport with Object & Iframe Multi-Tier Fallback */}
      <div className="relative w-full h-[580px] sm:h-[720px] bg-slate-100">
        <object
          data={previewUrl}
          type="application/pdf"
          className="w-full h-full"
        >
          <iframe
            src={previewUrl}
            title="Preview Dokumen Surat Resmi"
            className="w-full h-full border-0"
          >
            <div className="flex flex-col items-center justify-center h-full p-8 text-center bg-slate-50">
              <FileText className="w-12 h-12 text-slate-400 mb-3" />
              <p className="text-xs text-slate-600 mb-3 max-w-sm">
                Peramban Anda belum mendukung rendering PDF langsung pada bingkai ini.
                Silakan unduh atau buka berkas melalui tautan di bawah.
              </p>
              <a
                href={downloadUrl}
                download
                className="inline-flex items-center px-4 py-2 text-xs font-semibold text-white bg-slate-900 rounded hover:bg-slate-800 shadow-xs"
              >
                <Download className="w-4 h-4 mr-1.5" />
                Unduh Berkas PDF Resmi
              </a>
            </div>
          </iframe>
        </object>
      </div>
    </div>
  );
};

export default PDFViewer;
