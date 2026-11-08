import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import suratService from '../services/suratService';
import { extractErrorMessage } from '../services/api';
import type { SuratType, DynamicFieldDef } from '../types';
import { REQUIRED_FIELDS_BY_KODE, DEFAULT_REQUIRED_FIELDS } from '../data/requiredFields';
import {
  FileText,
  Sparkles,
  Send,
  ArrowLeft,
  Paperclip,
  X,
  AlertCircle,
  CheckCircle2,
  Calendar,
  Radio,
  FileCheck,
} from 'lucide-react';

// Architectural Note (Taste-Skill 2.5 - Dynamic Creation Studio):
// Form studio supporting dynamic schema generation for 10 official Indonesian academic letters.
// Features 16px legible typography, tactile input controls, and multimodal attachment ingestion.

export const SuratCreatePage: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();

  const prefillState = (location.state as any) || {};

  const [suratTypes, setSuratTypes] = useState<SuratType[]>([]);
  const [selectedKodeSurat, setSelectedKodeSurat] = useState<string>(
    prefillState.prefilledKodeSurat || ''
  );
  const [promptContext, setPromptContext] = useState<string>(
    prefillState.prefilledPrompt || ''
  );
  const [payloadData, setPayloadData] = useState<Record<string, any>>(
    prefillState.prefilledPayload || {}
  );
  const [chosenDestination, setChosenDestination] = useState<'email' | 'telegram' | ''>('');
  const [targetDestinationAddress, setTargetDestinationAddress] = useState<string>('');
  const [attachments, setAttachments] = useState<File[]>([]);

  const [isLoadingTypes, setIsLoadingTypes] = useState<boolean>(true);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  useEffect(() => {
    const loadTypes = async () => {
      try {
        const types = await suratService.getSuratTypes();
        setSuratTypes(types);
        if (!selectedKodeSurat && types.length > 0) {
          setSelectedKodeSurat(types[0].kode_surat);
        }
      } catch {
        setErrorMsg('Gagal memuat master daftar jenis surat dari server backend.');
      } finally {
        setIsLoadingTypes(false);
      }
    };
    loadTypes();
  }, []);

  const activeFields: DynamicFieldDef[] = selectedKodeSurat
    ? REQUIRED_FIELDS_BY_KODE[selectedKodeSurat] || DEFAULT_REQUIRED_FIELDS
    : DEFAULT_REQUIRED_FIELDS;

  const handleFieldChange = (fieldName: string, value: any) => {
    setPayloadData((prev) => ({
      ...prev,
      [fieldName]: value,
    }));
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const filesArray = Array.from(e.target.files);
      setAttachments((prev) => [...prev, ...filesArray]);
    }
  };

  const handleRemoveFile = (index: number) => {
    setAttachments((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedKodeSurat) {
      setErrorMsg('Pilih jenis surat yang ingin diajukan.');
      return;
    }

    setErrorMsg(null);
    setIsSubmitting(true);

    try {
      const result = await suratService.createSuratRequest({
        kode_surat: selectedKodeSurat,
        user_prompt_context: promptContext,
        payload_data: payloadData,
        chosen_destination: chosenDestination || undefined,
        target_destination_address: targetDestinationAddress || undefined,
        attachments: attachments.length > 0 ? attachments : undefined,
      });

      setSuccessMsg(result.message || 'Permohonan surat dinas berhasil dikirim ke agen AI.');

      const requestId = result.request_id || result.data?.request_id;
      setTimeout(() => {
        if (requestId) {
          navigate(`/surat/${requestId}`);
        } else {
          navigate('/dashboard');
        }
      }, 1500);
    } catch (err: any) {
      const parsedError = extractErrorMessage(
        err,
        'Terjadi kesalahan saat mengajukan permohonan surat.'
      );
      setErrorMsg(parsedError);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8">
      {/* Back button and page title */}
      <div>
        <Link
          to="/dashboard"
          className="inline-flex items-center text-xs font-semibold text-slate-500 hover:text-slate-800 mb-3 transition ts-btn"
        >
          <ArrowLeft className="w-3.5 h-3.5 mr-1" />
          Kembali ke Dasbor
        </Link>
        <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
          Formulir Permohonan Surat Resmi Kampus
        </h1>
        <p className="text-sm text-slate-600 mt-1 leading-relaxed">
          Pilih kategori dokumen dinas dan lengkapi atribut wajib. Agen AI akan memvalidasi integritas akademik dan menyusun naskah berstandar tata naskah dinas.
        </p>
      </div>

      {errorMsg && (
        <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 flex items-start space-x-3 text-xs sm:text-sm text-rose-800 whitespace-pre-line leading-relaxed shadow-xs">
          <AlertCircle className="w-5 h-5 shrink-0 text-rose-600 mt-0.5" />
          <span className="flex-1 font-medium">{errorMsg}</span>
        </div>
      )}

      {successMsg && (
        <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 flex items-start space-x-3 text-xs sm:text-sm text-emerald-800 shadow-xs">
          <CheckCircle2 className="w-5 h-5 shrink-0 text-emerald-600 mt-0.5" />
          <span className="font-semibold">{successMsg}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-8">
        {/* Section 1: Surat Type Selection */}
        <div className="ts-card p-6 sm:p-8 bg-white space-y-5">
          <div className="flex items-center space-x-2.5 pb-4 border-b border-slate-100">
            <FileText className="w-5 h-5 text-slate-800" />
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-900">
              1. Pilihan Dokumen Resmi Dinas
            </h2>
          </div>

          <div>
            <label
              htmlFor="kode_surat"
              className="block text-sm font-bold text-slate-800 mb-1.5"
            >
              Jenis Surat Akademik
            </label>
            <select
              id="kode_surat"
              value={selectedKodeSurat}
              onChange={(e) => setSelectedKodeSurat(e.target.value)}
              disabled={isLoadingTypes}
              className="block w-full px-4 py-3 text-sm border border-slate-300 rounded-lg bg-white focus:ring-2 focus:ring-slate-900 focus:border-slate-900 font-medium"
            >
              {suratTypes.map((type) => (
                <option key={type.kode_surat} value={type.kode_surat}>
                  [{type.kode_surat}] {type.nama_surat} — Kategori: {type.kategori}
                </option>
              ))}
            </select>
            <p className="text-xs text-slate-500 mt-1.5">
              Setiap jenis surat memiliki alur persetujuan (DPA, Kaprodi, Dekan) dan format blangko resmi tersendiri.
            </p>
          </div>
        </div>

        {/* Section 2: Dynamic Fields */}
        <div className="ts-card p-6 sm:p-8 bg-white space-y-5">
          <div className="flex items-center justify-between pb-4 border-b border-slate-100">
            <div className="flex items-center space-x-2.5">
              <Sparkles className="w-5 h-5 text-blue-600" />
              <h2 className="text-sm font-bold uppercase tracking-wider text-slate-900">
                2. Atribut Wajib Jenis Dokumen ({selectedKodeSurat})
              </h2>
            </div>
            <span className="text-xs text-slate-500 font-mono font-semibold bg-slate-100 px-2.5 py-1 rounded">
              {activeFields.length} Atribut Wajib
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {activeFields.map((field) => {
              const val = payloadData[field.field] || '';
              return (
                <div
                  key={field.field}
                  className={field.field === 'alasan_pengajuan' ? 'md:col-span-2' : ''}
                >
                  <label
                    htmlFor={field.field}
                    className="block text-xs font-bold uppercase tracking-wider text-slate-800 mb-1.5"
                  >
                    {field.label}
                  </label>
                  {field.type === 'date' ? (
                    <div className="relative rounded-lg shadow-2xs">
                      <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                        <Calendar className="w-4 h-4" />
                      </div>
                      <input
                        type="date"
                        id={field.field}
                        value={val}
                        onChange={(e) => handleFieldChange(field.field, e.target.value)}
                        className="block w-full pl-10 pr-4 py-2.5 text-sm border border-slate-300 rounded-lg focus:ring-2 focus:ring-slate-900 focus:border-slate-900 bg-white"
                      />
                    </div>
                  ) : field.field === 'alasan_pengajuan' ? (
                    <textarea
                      id={field.field}
                      rows={3}
                      value={val}
                      onChange={(e) => handleFieldChange(field.field, e.target.value)}
                      placeholder={field.description}
                      className="block w-full p-3.5 text-sm border border-slate-300 rounded-lg focus:ring-2 focus:ring-slate-900 focus:border-slate-900 bg-white placeholder-slate-400 leading-relaxed"
                    />
                  ) : (
                    <input
                      type="text"
                      id={field.field}
                      value={val}
                      onChange={(e) => handleFieldChange(field.field, e.target.value)}
                      placeholder={field.description}
                      className="block w-full px-4 py-2.5 text-sm border border-slate-300 rounded-lg focus:ring-2 focus:ring-slate-900 focus:border-slate-900 bg-white placeholder-slate-400"
                    />
                  )}
                  <span className="block text-[11px] text-slate-500 mt-1">
                    {field.description}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Section 3: Context & Delivery Options */}
        <div className="ts-card p-6 sm:p-8 bg-white space-y-5">
          <div className="flex items-center space-x-2.5 pb-4 border-b border-slate-100">
            <Radio className="w-5 h-5 text-slate-800" />
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-900">
              3. Konteks Alami & Jalur Pengiriman
            </h2>
          </div>

          <div>
            <label
              htmlFor="promptContext"
              className="block text-xs font-bold uppercase tracking-wider text-slate-800 mb-1.5"
            >
              Konteks Alami / Keterangan Khusus Mahasiswa
            </label>
            <textarea
              id="promptContext"
              rows={4}
              value={promptContext}
              onChange={(e) => setPromptContext(e.target.value)}
              placeholder="Jelaskan kebutuhan pengajuan secara rinci. Contoh: Pengajuan surat keterangan aktif kuliah untuk keperluan pendaftaran beasiswa PT Pertamina semester ganjil."
              className="block w-full p-4 text-sm border border-slate-300 rounded-lg focus:ring-2 focus:ring-slate-900 focus:border-slate-900 bg-white placeholder-slate-400 leading-relaxed"
            />
            <span className="block text-xs text-slate-500 mt-1.5">
              Data ini akan diproses langsung oleh model Gemini untuk merumuskan kalimat surat resmi dinas.
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-5 pt-3">
            <div>
              <label
                htmlFor="chosen_destination"
                className="block text-xs font-bold uppercase tracking-wider text-slate-800 mb-1.5"
              >
                Kanal Distribusi Otomatis
              </label>
              <select
                id="chosen_destination"
                value={chosenDestination}
                onChange={(e) =>
                  setChosenDestination(e.target.value as 'email' | 'telegram' | '')
                }
                className="block w-full px-4 py-2.5 text-sm border border-slate-300 rounded-lg bg-white focus:ring-2 focus:ring-slate-900 font-medium"
              >
                <option value="">Pilih kanal pengiriman (Opsional)</option>
                <option value="email">Email Mahasiswa / Instansi (Brevo)</option>
                <option value="telegram">Telegram Bot Kampus</option>
              </select>
            </div>

            <div>
              <label
                htmlFor="target_destination_address"
                className="block text-xs font-bold uppercase tracking-wider text-slate-800 mb-1.5"
              >
                Alamat Tujuan (Email / Chat ID)
              </label>
              <input
                type="text"
                id="target_destination_address"
                value={targetDestinationAddress}
                onChange={(e) => setTargetDestinationAddress(e.target.value)}
                placeholder="nama@email.com atau Chat ID Telegram"
                className="block w-full px-4 py-2.5 text-sm border border-slate-300 rounded-lg focus:ring-2 focus:ring-slate-900 bg-white placeholder-slate-400 font-mono"
              />
            </div>
          </div>
        </div>

        {/* Section 4: Multimodal File Attachments */}
        <div className="ts-card p-6 sm:p-8 bg-white space-y-5">
          <div className="flex items-center space-x-2.5 pb-4 border-b border-slate-100">
            <Paperclip className="w-5 h-5 text-slate-800" />
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-900">
              4. Berkas Lampiran Pendukung (Multimodal AI Part)
            </h2>
          </div>

          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-800 mb-1.5">
              Unggah Dokumen (PDF, JPG, PNG)
            </label>
            <input
              type="file"
              multiple
              accept=".pdf,.jpg,.jpeg,.png"
              onChange={handleFileChange}
              className="block w-full text-sm text-slate-500 file:mr-4 file:py-2.5 file:px-4 file:rounded-md file:border-0 file:text-xs file:font-bold file:bg-slate-900 file:text-white hover:file:bg-slate-800 file:transition file:cursor-pointer"
            />
            <span className="block text-xs text-slate-500 mt-1.5">
              Mendukung LoA magang, sertifikat beasiswa, atau pengumuman resmi. Agen Gemini mampu membaca dan mengekstrak teks dokumen secara langsung.
            </span>
          </div>

          {attachments.length > 0 && (
            <div className="space-y-2 pt-3">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-700">
                Daftar Berkas Terpilih ({attachments.length}):
              </span>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                {attachments.map((file, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between p-3 rounded-lg bg-slate-50 border border-slate-200 text-xs"
                  >
                    <div className="flex items-center space-x-2 truncate">
                      <FileCheck className="w-4 h-4 text-emerald-600 shrink-0" />
                      <span className="truncate font-semibold text-slate-800">{file.name}</span>
                      <span className="text-[10px] text-slate-400 font-mono">
                        ({(file.size / 1024).toFixed(1)} KB)
                      </span>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleRemoveFile(idx)}
                      className="p-1 text-slate-400 hover:text-rose-600 rounded transition ts-btn"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Submit Actions */}
        <div className="flex items-center justify-end space-x-4 pt-4">
          <Link
            to="/dashboard"
            className="h-11 px-5 text-sm font-semibold text-slate-700 bg-white border border-slate-300 hover:bg-slate-50 rounded-lg shadow-2xs transition ts-btn"
          >
            Batalkan
          </Link>
          <button
            type="submit"
            disabled={isSubmitting}
            className="h-11 px-6 text-sm font-bold text-white bg-slate-900 hover:bg-slate-800 disabled:opacity-50 rounded-lg shadow-xs transition ts-btn"
          >
            {isSubmitting ? (
              <span>Mengirim & Menyusun Draf AI...</span>
            ) : (
              <>
                <Send className="w-4 h-4 mr-2" />
                <span>Kirim Permohonan Surat Resmi</span>
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
};

export default SuratCreatePage;
