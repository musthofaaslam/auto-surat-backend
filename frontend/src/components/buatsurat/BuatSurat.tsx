import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import suratService from '../../services/suratService';
import { extractErrorMessage } from '../../services/api';
import type { SuratType, DynamicFieldDef } from '../../types';
import { REQUIRED_FIELDS_BY_KODE, DEFAULT_REQUIRED_FIELDS } from '../../data/requiredFields';
import {
  FileText,
  Sparkles,
  Paperclip,
  X,
  AlertCircle,
  CheckCircle2,
  Clock,
  ArrowRight,
  ArrowUp,
  RefreshCw,
  User as UserIcon,
  Bot,
  Plus,
  AtSign,
  Search,
  Hash,
  Calendar,
  Building2,
  GraduationCap,
  ChevronDown,
} from 'lucide-react';

interface ChatMessageItem {
  id: string;
  sender: 'user' | 'assistant' | 'system';
  text: string;
  timestamp: string;
}

interface BuatSuratProps {
  suratTypes: SuratType[];
  preSelectedKodeSurat?: string;
  onSubmissionSuccess?: (requestId: number) => void;
}

export const BuatSurat: React.FC<BuatSuratProps> = ({
  suratTypes,
  preSelectedKodeSurat,
  onSubmissionSuccess,
}) => {
  const { user } = useAuth();
  const navigate = useNavigate();

  // Internal Dual-Mode Switcher: 'form' vs 'chat'
  const [activeTab, setActiveTab] = useState<'form' | 'chat'>('form');

  // =========================================================================
  // 1. FORM SURAT STATE
  // =========================================================================
  const [selectedKodeSurat, setSelectedKodeSurat] = useState<string>(
    preSelectedKodeSurat || 'SK-KUL'
  );
  const [formPromptContext, setFormPromptContext] = useState<string>('');
  const [formPayloadData, setFormPayloadData] = useState<Record<string, any>>({});
  const [formChosenDestination, setFormChosenDestination] = useState<'email' | 'telegram' | ''>('email');
  const [formTargetDestination, setFormTargetDestination] = useState<string>('');
  const [formAttachments, setFormAttachments] = useState<File[]>([]);
  const [isSubmittingForm, setIsSubmittingForm] = useState<boolean>(false);
  const [formErrorMsg, setFormErrorMsg] = useState<string | null>(null);
  const [formSuccessMsg, setFormSuccessMsg] = useState<string | null>(null);

  // Sync with preSelectedKodeSurat if changed from props
  useEffect(() => {
    if (preSelectedKodeSurat) {
      setSelectedKodeSurat(preSelectedKodeSurat);
      setActiveTab('form');
    }
  }, [preSelectedKodeSurat]);

  // Set default email from authenticated user
  useEffect(() => {
    if (user?.email && !formTargetDestination && formChosenDestination === 'email') {
      setFormTargetDestination(user.email);
    }
  }, [user, formChosenDestination]);

  // =========================================================================
  // 2. CHAT AI STATE
  // =========================================================================
  const [chatThreadId, setChatThreadId] = useState<string | null>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessageItem[]>([]);
  const [chatInput, setChatInput] = useState<string>('');
  const [isChatLoading, setIsChatLoading] = useState<boolean>(false);
  const [chatDetectedIntent, setChatDetectedIntent] = useState<string | null>(null);
  const [chatCollectedSlots, setChatCollectedSlots] = useState<Record<string, any>>({});
  const [chatMissingFields, setChatMissingFields] = useState<string[]>([]);
  const [chatRequiredFields, setChatRequiredFields] = useState<DynamicFieldDef[]>([]);
  const [chatIsReadyToDraft, setChatIsReadyToDraft] = useState<boolean>(false);
  const [chatAttachments, setChatAttachments] = useState<File[]>([]);
  const [showMentionMenu, setShowMentionMenu] = useState<boolean>(false);

  const chatMessagesContainerRef = useRef<HTMLDivElement>(null);
  const chatInputRef = useRef<HTMLTextAreaElement>(null);

  const promptSuggestions = [
    'Saya ingin mengajukan surat keterangan aktif kuliah untuk keperluan beasiswa.',
    'Permohonan surat rekomendasi magang di PT Telekomunikasi Indonesia divisi Backend.',
    'Izin pelaksanaan survei observasi mata kuliah selama 2 pekan.',
  ];

  // Initialize Chat Session when chat tab is opened
  useEffect(() => {
    if (activeTab === 'chat' && !chatThreadId) {
      initChatSession();
    }
  }, [activeTab]);

  // Auto-scroll strictly inside chat message box when new messages arrive without shifting the page
  useEffect(() => {
    if (chatMessagesContainerRef.current) {
      chatMessagesContainerRef.current.scrollTop = chatMessagesContainerRef.current.scrollHeight;
    }
  }, [chatMessages]);

  const initChatSession = async (docType?: string) => {
    setIsChatLoading(true);
    try {
      const res = await suratService.initChat('Sesi Permohonan Surat', docType || null);
      setChatThreadId(res.thread_id);
      setChatMessages([
        {
          id: 'welcome',
          sender: 'assistant',
          text:
            'Halo. Saya Asisten Cerdas Persuratan Dinas Akademik (Agentic AI Level 2). ' +
            'Silakan jelaskan surat dinas yang Anda perlukan beserta tujuannya dalam bahasa alami. ' +
            'Saya akan mengekstrak atribut wajib dan memvalidasi kelengkapannya secara otomatis.',
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
      setChatCollectedSlots({});
      setChatMissingFields([]);
      setChatIsReadyToDraft(false);
      setChatDetectedIntent(docType || null);
    } catch {
      setChatMessages([
        {
          id: 'err-init',
          sender: 'assistant',
          text: 'Gagal menginisialisasi sesi AI. Anda tetap dapat menggunakan tab Formulir Surat.',
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    } finally {
      setIsChatLoading(false);
    }
  };

  const handleSendChatMessage = async () => {
    if (!chatInput.trim() && chatAttachments.length === 0) return;
    if (!chatThreadId) return;

    const userText = chatInput.trim();
    const userMsgId = `user-${Date.now()}`;
    const newMsg: ChatMessageItem = {
      id: userMsgId,
      sender: 'user',
      text: userText,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setChatMessages((prev) => [...prev, newMsg]);
    setChatInput('');
    setIsChatLoading(true);

    try {
      const resp = await suratService.sendChatMessage(
        chatThreadId,
        userText,
        chatAttachments.length > 0 ? chatAttachments : undefined
      );

      setChatAttachments([]);

      if (resp.intent) setChatDetectedIntent(resp.intent);
      if (resp.collected_slots) setChatCollectedSlots(resp.collected_slots);
      if (resp.missing_fields) setChatMissingFields(resp.missing_fields);
      if (resp.required_fields) setChatRequiredFields(resp.required_fields);
      if (typeof resp.is_ready_to_draft === 'boolean') {
        setChatIsReadyToDraft(resp.is_ready_to_draft);
      }

      const botMsg: ChatMessageItem = {
        id: `assistant-${Date.now()}`,
        sender: 'assistant',
        text: resp.reply,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setChatMessages((prev) => [...prev, botMsg]);
    } catch (err: any) {
      const errMsg: ChatMessageItem = {
        id: `err-${Date.now()}`,
        sender: 'system',
        text: extractErrorMessage(err, 'Kendala jaringan pada komunikasi agen AI.'),
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setChatMessages((prev) => [...prev, errMsg]);
    } finally {
      setIsChatLoading(false);
    }
  };

  const handleProceedFromChatToSubmission = async () => {
    const finalKodeSurat = chatDetectedIntent || selectedKodeSurat || 'SK-KUL';
    setIsChatLoading(true);

    try {
      const payload: Record<string, any> = {
        kode_surat: finalKodeSurat,
        user_prompt_context: chatMessages
          .filter((m) => m.sender === 'user')
          .map((m) => m.text)
          .join('\n'),
        payload_data: chatCollectedSlots,
        chosen_destination: formChosenDestination || 'email',
        target_destination_address: formTargetDestination || user?.email || '',
        attachments: chatAttachments,
      };

      const result = await suratService.createSuratRequest(payload);
      const reqId = result.request_id || result.data?.request_id;
      if (reqId) {
        if (onSubmissionSuccess) {
          onSubmissionSuccess(reqId);
        } else {
          navigate(`/surat/${reqId}`);
        }
      } else {
        setActiveTab('form');
      }
    } catch (err: any) {
      const errMsg: ChatMessageItem = {
        id: `err-sub-${Date.now()}`,
        sender: 'system',
        text: extractErrorMessage(err, 'Gagal meneruskan draf dari percakapan AI.'),
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setChatMessages((prev) => [...prev, errMsg]);
    } finally {
      setIsChatLoading(false);
    }
  };

  // =========================================================================
  // 3. FORM HANDLERS
  // =========================================================================
  const currentSelectedSuratObj = suratTypes.find((s) => s.kode_surat === selectedKodeSurat);

  const activeRequiredFields: DynamicFieldDef[] =
    REQUIRED_FIELDS_BY_KODE[selectedKodeSurat] || DEFAULT_REQUIRED_FIELDS;

  const handleFormFieldChange = (field: string, value: string) => {
    setFormPayloadData((prev) => ({
      ...prev,
      [field]: value,
    }));
  };

  const handleFormFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setFormAttachments(Array.from(e.target.files));
    }
  };

  const handleFormSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormErrorMsg(null);
    setFormSuccessMsg(null);

    if (!selectedKodeSurat) {
      setFormErrorMsg('Silakan pilih salah satu jenis surat yang ingin diajukan.');
      return;
    }

    const missingFields: string[] = [];
    activeRequiredFields.forEach((f) => {
      if (!formPayloadData[f.field] || !String(formPayloadData[f.field]).trim()) {
        missingFields.push(f.label);
      }
    });

    if (missingFields.length > 0) {
      setFormErrorMsg(
        `Kolom wajib berikut belum dilengkapi:\n- ${missingFields.join('\n- ')}`
      );
      return;
    }

    if (!formPromptContext.trim()) {
      setFormErrorMsg('Penjelasan konteks/keperluan permohonan surat wajib diisi.');
      return;
    }

    if (formChosenDestination && !formTargetDestination.trim()) {
      setFormErrorMsg(
        `Alamat tujuan pengiriman ${formChosenDestination === 'email' ? 'Email' : 'Telegram'} wajib diisi.`
      );
      return;
    }

    setIsSubmittingForm(true);

    try {
      const result = await suratService.createSuratRequest({
        kode_surat: selectedKodeSurat,
        user_prompt_context: formPromptContext,
        payload_data: formPayloadData,
        chosen_destination: formChosenDestination,
        target_destination_address: formTargetDestination,
        attachments: formAttachments,
      });

      setFormSuccessMsg('Permohonan surat berhasil dibuat. Mengarahkan ke rincian dokumen...');
      const reqId = result.request_id || result.data?.request_id;
      setTimeout(() => {
        if (reqId) {
          if (onSubmissionSuccess) {
            onSubmissionSuccess(reqId);
          } else {
            navigate(`/surat/${reqId}`);
          }
        }
      }, 1000);
    } catch (err: any) {
      setFormErrorMsg(
        extractErrorMessage(err, 'Terjadi kesalahan saat memproses permohonan surat.')
      );
    } finally {
      setIsSubmittingForm(false);
    }
  };

  const getFieldIcon = (field: string) => {
    if (field.includes('nama') || field.includes('dosen') || field.includes('pembimbing')) {
      return <UserIcon className="w-3.5 h-3.5 text-slate-400" />;
    }
    if (field.includes('nim') || field.includes('nip') || field.includes('semester')) {
      return <Hash className="w-3.5 h-3.5 text-slate-400" />;
    }
    if (field.includes('tgl') || field.includes('tanggal') || field.includes('tahun')) {
      return <Calendar className="w-3.5 h-3.5 text-slate-400" />;
    }
    if (field.includes('perusahaan') || field.includes('mitra') || field.includes('tempat')) {
      return <Building2 className="w-3.5 h-3.5 text-slate-400" />;
    }
    return <GraduationCap className="w-3.5 h-3.5 text-slate-400" />;
  };

  return (
    <div className="w-full bg-white border border-slate-200/90 rounded-2xl shadow-xs flex flex-col overflow-hidden motion-stagger-1">
      {/* 1. CONTAINER TOP BAR: DUAL-MODE SEGMENTED CONTROL */}
      <div className="h-14 px-4 sm:px-6 border-b border-slate-100 flex items-center justify-between shrink-0 bg-white">
        {/* Segmented Control */}
        <div className="bg-slate-100/90 p-1 rounded-xl inline-flex items-center space-x-1">
          <button
            type="button"
            onClick={() => setActiveTab('form')}
            className={`inline-flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-xs transition-all duration-200 cursor-pointer ${
              activeTab === 'form'
                ? 'bg-white text-slate-900 font-semibold shadow-2xs'
                : 'text-slate-600 hover:text-slate-900 font-normal'
            }`}
          >
            <FileText className="w-3.5 h-3.5" />
            <span>Formulir Surat</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('chat')}
            className={`inline-flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-xs transition-all duration-200 cursor-pointer ${
              activeTab === 'chat'
                ? 'bg-white text-slate-900 font-semibold shadow-2xs'
                : 'text-slate-600 hover:text-slate-900 font-normal'
            }`}
          >
            <Sparkles className="w-3.5 h-3.5 text-blue-600" />
            <span>Sesi Chat AI</span>
          </button>
        </div>

        {/* Status Indicator & Quick Metadata */}
        <div className="flex items-center space-x-3 text-xs text-slate-500">
          <div className="hidden sm:flex items-center space-x-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className="font-normal">Sistem Siap</span>
          </div>
          {activeTab === 'form' && currentSelectedSuratObj && (
            <span className="text-[11px] px-2 py-0.5 rounded font-normal bg-slate-100 text-slate-700 border border-slate-200 truncate max-w-[140px] sm:max-w-none">
              {currentSelectedSuratObj.kode_surat}
            </span>
          )}
          {activeTab === 'chat' && chatDetectedIntent && (
            <span className="text-[11px] px-2 py-0.5 rounded font-normal bg-blue-50 text-blue-700 border border-blue-200">
              {chatDetectedIntent}
            </span>
          )}
        </div>
      </div>

      {/* 2. TAB VIEW A: FORMULIR SURAT WORKSPACE */}
      {activeTab === 'form' && (
        <div key="form-pane" className="p-4 sm:p-7 space-y-6 motion-tab-pane">
          {/* Header */}
          <div className="border-b border-slate-100 pb-4">
            <h1 className="text-base sm:text-lg font-semibold text-slate-900 tracking-tight">
              Pengajuan Surat Resmi Akademik
            </h1>
            <p className="text-xs font-normal text-slate-500 mt-1">
              Pilih jenis naskah dinas dari dropdown dan lengkapi atribut wajib. Agen AI akan memvalidasi tata naskah dinas sebelum diteruskan ke dosen penandatangan.
            </p>
          </div>

          {formErrorMsg && (
            <div className="p-3.5 rounded-lg bg-rose-50 border border-rose-200 text-xs font-normal text-rose-800 flex items-start space-x-2.5">
              <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
              <div className="whitespace-pre-line leading-relaxed">{formErrorMsg}</div>
            </div>
          )}

          {formSuccessMsg && (
            <div className="p-3.5 rounded-lg bg-emerald-50 border border-emerald-200 text-xs font-normal text-emerald-800 flex items-start space-x-2.5">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
              <div>{formSuccessMsg}</div>
            </div>
          )}

          <form onSubmit={handleFormSubmit} className="space-y-6">
            {/* Section 1: Dropdown Selection */}
            <div className="space-y-2">
              <label className="block text-xs font-semibold text-slate-900 uppercase tracking-wider">
                1. Pilih Jenis Naskah Dinas Resmi
              </label>
              <div className="relative max-w-xl">
                <select
                  value={selectedKodeSurat}
                  onChange={(e) => {
                    setSelectedKodeSurat(e.target.value);
                    setFormPayloadData({});
                  }}
                  className="w-full px-3.5 py-2.5 text-xs font-normal border border-slate-300 rounded-lg bg-white text-slate-900 focus:border-slate-900 focus:ring-1 focus:ring-slate-900 focus:outline-none transition appearance-none cursor-pointer"
                >
                  <optgroup label="Surat Keterangan">
                    <option value="SK-KUL">Surat Keterangan Kuliah (SK-KUL)</option>
                    <option value="SK-AKT">Surat Keterangan Aktif Mahasiswa (SK-AKT)</option>
                    <option value="SK-LUL">Surat Keterangan Lulus Sementara (SK-LUL)</option>
                    <option value="SK-BKL">Surat Keterangan Berkelakuan Baik (SK-BKL)</option>
                  </optgroup>
                  <optgroup label="Surat Pengantar">
                    <option value="SP-MAG">Surat Pengantar Kerja Praktik / Magang (SP-MAG)</option>
                    <option value="SP-PEN">Surat Pengantar Penelitian Skripsi (SP-PEN)</option>
                    <option value="SP-TUG">Surat Tugas Akademik (SP-TUG)</option>
                  </optgroup>
                  <optgroup label="Surat Rekomendasi & Izin">
                    <option value="SR-BEA">Surat Rekomendasi Beasiswa (SR-BEA)</option>
                    <option value="SR-MAG">Surat Rekomendasi Magang (SR-MAG)</option>
                    <option value="SI-MAG">Surat Izin Magang (SI-MAG)</option>
                    <option value="SI-SUR">Surat Izin Survei & Riset Observasi (SI-SUR)</option>
                  </optgroup>
                </select>

                <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-3 text-slate-500">
                  <ChevronDown className="w-4 h-4" />
                </div>
              </div>

              {currentSelectedSuratObj && (
                <p className="text-[11px] font-normal text-slate-500">
                  Format terpilih: <span className="font-semibold text-slate-800">{currentSelectedSuratObj.nama_surat}</span> ({currentSelectedSuratObj.kode_surat})
                </p>
              )}
            </div>

            {/* Section 2: Context Natural Language */}
            <div className="space-y-1.5">
              <label className="block text-xs font-semibold text-slate-900 uppercase tracking-wider">
                2. Keperluan & Penjelasan Konteks Permohonan
              </label>
              <p className="text-[11px] font-normal text-slate-500">
                Tuliskan latar belakang, tujuan penggunaan surat, atau institusi yang dituju.
              </p>
              <textarea
                rows={3}
                value={formPromptContext}
                onChange={(e) => setFormPromptContext(e.target.value)}
                placeholder="Contoh: Saya membutuhkan surat pengantar magang di PT Telekomunikasi Indonesia untuk posisi Software Engineer selama 6 bulan..."
                className="w-full p-3 rounded-lg border border-slate-200 bg-slate-50/50 text-xs font-normal text-slate-900 focus:bg-white focus:border-slate-900 focus:outline-none transition leading-relaxed"
              />
            </div>

            {/* Section 3: Dynamic Required Fields */}
            <div className="space-y-3 pt-2 border-t border-slate-100">
              <div>
                <label className="block text-xs font-semibold text-slate-900 uppercase tracking-wider">
                  3. Kelengkapan Atribut Format Naskah Dinas ({selectedKodeSurat})
                </label>
                <p className="text-[11px] font-normal text-slate-500 mt-0.5">
                  Kolom berikut wajib diisi sesuai standar tata naskah dinas resmi kampus.
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {activeRequiredFields.map((fieldDef) => (
                  <div key={fieldDef.field} className="space-y-1">
                    <label className="flex items-center space-x-1.5 text-xs font-semibold text-slate-700">
                      {getFieldIcon(fieldDef.field)}
                      <span>{fieldDef.label}</span>
                      <span className="text-rose-500 text-xs">*</span>
                    </label>

                    {fieldDef.type === 'textarea' ? (
                      <textarea
                        rows={2}
                        value={formPayloadData[fieldDef.field] || ''}
                        onChange={(e) =>
                          handleFormFieldChange(fieldDef.field, e.target.value)
                        }
                        className="w-full px-3 py-2 text-xs font-normal border border-slate-200 rounded-lg bg-white text-slate-900 focus:border-slate-900 focus:outline-none"
                        required
                      />
                    ) : (
                      <input
                        type={fieldDef.type === 'number' ? 'number' : 'text'}
                        value={formPayloadData[fieldDef.field] || ''}
                        onChange={(e) =>
                          handleFormFieldChange(fieldDef.field, e.target.value)
                        }
                        placeholder={fieldDef.description || fieldDef.label}
                        className="w-full px-3 py-2 text-xs font-normal border border-slate-200 rounded-lg bg-white text-slate-900 focus:border-slate-900 focus:outline-none"
                        required
                      />
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Section 4: Saluran Distribusi & Lampiran */}
            <div className="space-y-4 pt-2 border-t border-slate-100">
              <label className="block text-xs font-semibold text-slate-900 uppercase tracking-wider">
                4. Saluran Pengiriman Dokumen & Berkas Pendukung
              </label>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {/* Saluran Pengiriman */}
                <div className="space-y-2">
                  <span className="block text-xs font-semibold text-slate-700">
                    Opsi Saluran Penerbitan Otomatis
                  </span>
                  <div className="flex items-center space-x-4">
                    <label className="inline-flex items-center space-x-2 text-xs font-normal text-slate-700 cursor-pointer">
                      <input
                        type="radio"
                        name="distDestination"
                        value="email"
                        checked={formChosenDestination === 'email'}
                        onChange={() => setFormChosenDestination('email')}
                        className="text-slate-900 focus:ring-slate-900"
                      />
                      <span>Email Resmi</span>
                    </label>
                    <label className="inline-flex items-center space-x-2 text-xs font-normal text-slate-700 cursor-pointer">
                      <input
                        type="radio"
                        name="distDestination"
                        value="telegram"
                        checked={formChosenDestination === 'telegram'}
                        onChange={() => setFormChosenDestination('telegram')}
                        className="text-slate-900 focus:ring-slate-900"
                      />
                      <span>Telegram Bot</span>
                    </label>
                  </div>

                  {formChosenDestination && (
                    <input
                      type={formChosenDestination === 'email' ? 'email' : 'text'}
                      value={formTargetDestination}
                      onChange={(e) => setFormTargetDestination(e.target.value)}
                      placeholder={
                        formChosenDestination === 'email'
                          ? 'contoh@student.kampus.ac.id'
                          : 'Masukkan nomor Chat ID Telegram Anda'
                      }
                      className="w-full px-3 py-2 text-xs font-normal border border-slate-200 rounded-lg bg-white text-slate-900 focus:border-slate-900 focus:outline-none"
                    />
                  )}
                </div>

                {/* Lampiran Berkas */}
                <div className="space-y-2">
                  <span className="block text-xs font-semibold text-slate-700">
                    Lampiran Berkas Resmi (Opsional)
                  </span>
                  <div className="flex items-center space-x-2">
                    <label className="px-3 py-2 bg-slate-100 hover:bg-slate-200 border border-slate-300 rounded-lg text-xs font-normal text-slate-700 cursor-pointer flex items-center space-x-2 transition">
                      <Paperclip className="w-3.5 h-3.5" />
                      <span>Pilih Berkas Lampiran</span>
                      <input
                        type="file"
                        multiple
                        onChange={handleFormFileChange}
                        className="hidden"
                      />
                    </label>
                    {formAttachments.length > 0 && (
                      <span className="text-xs font-normal text-emerald-600">
                        {formAttachments.length} berkas dipilih
                      </span>
                    )}
                  </div>
                  <p className="text-[10px] font-normal text-slate-400">
                    Format: PDF, PNG, JPG (Maks. 5MB per berkas).
                  </p>
                </div>
              </div>
            </div>

            {/* Submit Action Button */}
            <div className="pt-4 border-t border-slate-100 flex justify-end">
              <button
                type="submit"
                disabled={isSubmittingForm}
                className="w-full sm:w-auto px-6 py-2.5 rounded-lg bg-slate-900 text-white text-xs font-semibold hover:bg-slate-800 disabled:opacity-50 transition shadow-xs flex items-center justify-center space-x-2 ts-btn cursor-pointer"
              >
                {isSubmittingForm ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Memproses Draf Naskah...</span>
                  </>
                ) : (
                  <>
                    <span>Kirim Permohonan Surat</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </>
                )}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* 3. TAB VIEW B: CHAT AI WORKSPACE */}
      {activeTab === 'chat' && (
        <div key="chat-pane" className="flex flex-col h-[580px] sm:h-[620px] overflow-hidden bg-slate-50/40 motion-tab-pane">
          {/* Sub-Header */}
          <div className="h-10 px-4 sm:px-6 border-b border-slate-200/80 bg-white flex items-center justify-between shrink-0 text-xs">
            <div className="flex items-center space-x-2 truncate">
              <Sparkles className="w-3.5 h-3.5 text-blue-600 shrink-0" />
              <span className="font-semibold text-slate-800 truncate">
                Sesi Dialog Penentuan & Ekstraksi Draf Surat
              </span>
            </div>

            <button
              onClick={() => initChatSession()}
              title="Mulai sesi baru"
              className="px-2 py-1 rounded text-[11px] font-normal text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition flex items-center space-x-1 cursor-pointer"
            >
              <RefreshCw className="w-3 h-3" />
              <span>Mulai Ulang Sesi</span>
            </button>
          </div>

          {/* Chat Message Stream */}
          <div ref={chatMessagesContainerRef} className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
            {chatMessages.map((msg) => {
              const isUser = msg.sender === 'user';
              const isSystem = msg.sender === 'system';

              if (isSystem) {
                return (
                  <div
                    key={msg.id}
                    className="text-center py-2 text-[11px] font-normal text-rose-600"
                  >
                    {msg.text}
                  </div>
                );
              }

              return (
                <div
                  key={msg.id}
                  className={`flex items-start space-x-2.5 max-w-3xl ${
                    isUser ? 'ml-auto flex-row-reverse space-x-reverse' : ''
                  }`}
                >
                  <div
                    className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 text-xs font-semibold ${
                      isUser
                        ? 'bg-slate-900 text-white'
                        : 'bg-blue-600 text-white shadow-2xs'
                    }`}
                  >
                    {isUser ? <UserIcon className="w-3.5 h-3.5" /> : <Bot className="w-3.5 h-3.5" />}
                  </div>

                  <div className="space-y-1 max-w-[85%] sm:max-w-xl">
                    <div
                      className={`p-3.5 rounded-2xl text-xs font-normal leading-relaxed whitespace-pre-wrap ${
                        isUser
                          ? 'bg-slate-900 text-white rounded-tr-none'
                          : 'bg-white border border-slate-200/90 text-slate-900 rounded-tl-none shadow-2xs'
                      }`}
                    >
                      {msg.text}
                    </div>
                    <div
                      className={`text-[10px] text-slate-400 font-normal px-1 ${
                        isUser ? 'text-right' : 'text-left'
                      }`}
                    >
                      {msg.timestamp}
                    </div>
                  </div>
                </div>
              );
            })}

            {isChatLoading && (
              <div className="flex items-center space-x-2 text-xs font-normal text-slate-500 py-2">
                <RefreshCw className="w-3.5 h-3.5 animate-spin text-blue-600" />
                <span>Agen AI menganalisa naskah dinas...</span>
              </div>
            )}

            {/* Slot Memory Telemetry Checklist */}
            {Object.keys(chatCollectedSlots).length > 0 && (
              <div className="p-3.5 rounded-xl bg-white border border-slate-200 shadow-2xs space-y-2 max-w-xl">
                <div className="text-[11px] font-semibold text-slate-700 uppercase tracking-wider flex items-center justify-between">
                  <span>Atribut Yang Telah Terdeteksi</span>
                  <span className="text-[10px] text-slate-400 font-normal">
                    Format: {chatDetectedIntent || selectedKodeSurat}
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  {Object.entries(chatCollectedSlots).map(([key, val]) => (
                    <div key={key} className="p-2 rounded bg-slate-50 border border-slate-100">
                      <span className="text-[10px] font-semibold text-slate-500 block uppercase">
                        {key.replace(/_/g, ' ')}
                      </span>
                      <span className="font-normal text-slate-800 truncate block">
                        {String(val)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Ready to draft banner */}
            {chatIsReadyToDraft && (
              <div className="p-3.5 rounded-xl bg-emerald-50 border border-emerald-200 text-xs font-normal text-emerald-950 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 shadow-2xs">
                <div className="flex items-center space-x-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                  <span>Seluruh atribut naskah dinas telah lengkap dan tervalidasi.</span>
                </div>
                <button
                  type="button"
                  onClick={handleProceedFromChatToSubmission}
                  disabled={isChatLoading}
                  className="px-4 py-2 rounded-lg bg-slate-900 text-white text-xs font-semibold hover:bg-slate-800 transition flex items-center space-x-2 shadow-xs cursor-pointer"
                >
                  <span>Lanjutkan & Simpan Draf Permohonan</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </button>
              </div>
            )}
          </div>

          {/* DOCKED FLOATING PROMPT CAPSULE AT BOTTOM */}
          <div className="p-3 sm:p-5 border-t border-slate-200/80 bg-white shrink-0">
            <div className="max-w-4xl mx-auto space-y-2">
              <div className="border border-slate-300 rounded-2xl p-2.5 bg-white shadow-xs focus-within:border-slate-900 focus-within:ring-1 focus-within:ring-slate-900 transition-all">
                <textarea
                  ref={chatInputRef}
                  rows={2}
                  value={chatInput}
                  onChange={(e) => {
                    setChatInput(e.target.value);
                    if (e.target.value.endsWith('@')) {
                      setShowMentionMenu(true);
                    } else if (!e.target.value.includes('@')) {
                      setShowMentionMenu(false);
                    }
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      handleSendChatMessage();
                    }
                  }}
                  placeholder="Ketik kebutuhan surat Anda atau jelaskan informasi tambahan..."
                  className="w-full px-2 py-1 text-xs font-normal text-slate-900 placeholder:text-slate-400 focus:outline-none resize-none leading-relaxed"
                />

                <div className="flex items-center justify-between pt-2 border-t border-slate-100">
                  <div className="flex items-center space-x-1 text-slate-400">
                    <button
                      type="button"
                      onClick={() => setShowMentionMenu(!showMentionMenu)}
                      className="p-1 rounded hover:bg-slate-100 hover:text-slate-700 transition cursor-pointer"
                      title="Sebutkan jenis surat (@)"
                    >
                      <AtSign className="w-3.5 h-3.5" />
                    </button>
                    <label className="p-1 rounded hover:bg-slate-100 hover:text-slate-700 transition cursor-pointer">
                      <Paperclip className="w-3.5 h-3.5" />
                      <input
                        type="file"
                        multiple
                        onChange={(e) => {
                          if (e.target.files) {
                            setChatAttachments(Array.from(e.target.files));
                          }
                        }}
                        className="hidden"
                      />
                    </label>
                    {chatAttachments.length > 0 && (
                      <span className="text-[10px] font-normal text-slate-600">
                        {chatAttachments.length} lampiran
                      </span>
                    )}
                  </div>

                  <button
                    type="button"
                    onClick={handleSendChatMessage}
                    disabled={isChatLoading || (!chatInput.trim() && chatAttachments.length === 0)}
                    className="w-7 h-7 rounded-full bg-slate-900 text-white flex items-center justify-center hover:bg-slate-800 disabled:opacity-30 transition shadow-2xs cursor-pointer"
                    aria-label="Kirim pesan"
                  >
                    <ArrowUp className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>

              {/* Mention Popup Menu */}
              {showMentionMenu && (
                <div className="p-2 bg-white border border-slate-200 rounded-xl shadow-lg max-h-48 overflow-y-auto space-y-1">
                  <div className="text-[10px] font-normal text-slate-400 px-2 py-1 uppercase">
                    Pilih Referensi Jenis Surat
                  </div>
                  {suratTypes.map((item) => (
                    <button
                      key={item.kode_surat}
                      type="button"
                      onClick={() => {
                        setChatInput(
                          (prev) => `${prev} [${item.kode_surat}: ${item.nama_surat}] `
                        );
                        setShowMentionMenu(false);
                        chatInputRef.current?.focus();
                      }}
                      className="w-full text-left px-2.5 py-1.5 rounded text-xs font-normal text-slate-700 hover:bg-slate-100 flex items-center justify-between cursor-pointer"
                    >
                      <span className="truncate">{item.nama_surat}</span>
                      <span className="text-[10px] font-normal text-slate-500 ml-2">
                        {item.kode_surat}
                      </span>
                    </button>
                  ))}
                </div>
              )}

              {/* Status Telemetry Strip at Bottom */}
              <div className="flex items-center justify-between text-[10px] font-normal text-slate-400 px-1">
                <div className="flex items-center space-x-2 truncate">
                  <span>NIM: {user?.nip_nim}</span>
                  <span>•</span>
                  <span>Model: Gemini 3.1 Flash Lite</span>
                </div>
                <div className="flex items-center space-x-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                  <span>Streaming Aktif</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default BuatSurat;
