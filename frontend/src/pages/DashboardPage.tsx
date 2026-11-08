import React, { useState, useEffect, useRef } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import suratService from '../services/suratService';
import { extractErrorMessage } from '../services/api';
import type {
  SuratType,
  SuratRequestListItem,
  DynamicFieldDef,
  VerificationData,
} from '../types';
import { REQUIRED_FIELDS_BY_KODE, DEFAULT_REQUIRED_FIELDS } from '../data/requiredFields';
import StatusBadge from '../components/StatusBadge';
import DashboardSidebar from '../components/DashboardSidebar';
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
  Menu,
  ShieldCheck,
  ShieldAlert,
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

export const DashboardPage: React.FC = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // Sidebar responsive state: strictly FALSE by default so mobile users land directly on main content
  const [isSidebarOpen, setIsSidebarOpen] = useState<boolean>(false);

  // Main View: 'dashboard' vs 'verify' (unified single-workspace architecture)
  const [activeMainView, setActiveMainView] = useState<'dashboard' | 'verify'>('dashboard');

  // Dashboard Sub-Mode: 'form' vs 'chat'
  const [activeDashboardTab, setActiveDashboardTab] = useState<'form' | 'chat'>('form');

  // Sync with URL query parameters (?view=verify, ?surat=SK-KUL)
  useEffect(() => {
    const viewParam = searchParams.get('view');
    if (viewParam === 'verify') {
      setActiveMainView('verify');
    } else if (viewParam === 'dashboard') {
      setActiveMainView('dashboard');
    }

    const suratParam = searchParams.get('surat');
    if (suratParam) {
      setActiveMainView('dashboard');
      setActiveDashboardTab('form');
      setSelectedKodeSurat(suratParam);
    }
  }, [searchParams]);

  // Shared Master Data
  const [suratTypes, setSuratTypes] = useState<SuratType[]>([]);
  const [requests, setRequests] = useState<SuratRequestListItem[]>([]);
  const [isLoadingRequests, setIsLoadingRequests] = useState<boolean>(true);

  // =========================================================================
  // FORM SURAT STATE (WITH DROPDOWN SELECTOR)
  // =========================================================================
  const [selectedKodeSurat, setSelectedKodeSurat] = useState<string>('SK-KUL');
  const [formPromptContext, setFormPromptContext] = useState<string>('');
  const [formPayloadData, setFormPayloadData] = useState<Record<string, any>>({});
  const [formChosenDestination, setFormChosenDestination] = useState<'email' | 'telegram' | ''>('email');
  const [formTargetDestination, setFormTargetDestination] = useState<string>('');
  const [formAttachments, setFormAttachments] = useState<File[]>([]);
  const [isSubmittingForm, setIsSubmittingForm] = useState<boolean>(false);
  const [formErrorMsg, setFormErrorMsg] = useState<string | null>(null);
  const [formSuccessMsg, setFormSuccessMsg] = useState<string | null>(null);

  // =========================================================================
  // CHAT AI STATE (MODELED ON AGENTIC IDE REFERENCE)
  // =========================================================================
  const [chatThreadId, setChatThreadId] = useState<string | null>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessageItem[]>([]);
  const [chatInput, setChatInput] = useState<string>('');
  const [isChatLoading, setIsChatLoading] = useState<boolean>(false);
  const [chatDetectedIntent, setChatDetectedIntent] = useState<string | null>(null);
  const [chatCollectedSlots, setChatCollectedSlots] = useState<Record<string, any>>({});
  const [chatRequiredFields, setChatRequiredFields] = useState<DynamicFieldDef[]>([]);
  const [chatIsReadyToDraft, setChatIsReadyToDraft] = useState<boolean>(false);
  const [chatAttachments, setChatAttachments] = useState<File[]>([]);
  const [showMentionMenu, setShowMentionMenu] = useState<boolean>(false);

  const chatEndRef = useRef<HTMLDivElement>(null);
  const chatInputRef = useRef<HTMLTextAreaElement>(null);

  // Prompt suggestions for Chat AI
  const promptSuggestions = [
    'Saya ingin mengajukan surat keterangan aktif kuliah untuk keperluan beasiswa.',
    'Permohonan surat rekomendasi magang di PT Telekomunikasi Indonesia divisi Backend.',
    'Izin pelaksanaan survei observasi mata kuliah selama 2 pekan.',
  ];

  // =========================================================================
  // VERIFIKASI TTE STATE (EMBEDDED IN SINGLE WORKSPACE)
  // =========================================================================
  const [verifyTokenInput, setVerifyTokenInput] = useState<string>('');
  const [verifyResult, setVerifyResult] = useState<VerificationData | null>(null);
  const [isVerifying, setIsVerifying] = useState<boolean>(false);
  const [verifyErrorMsg, setVerifyErrorMsg] = useState<string | null>(null);

  // Initial Data Load
  useEffect(() => {
    const loadInitialData = async () => {
      try {
        const types = await suratService.getSuratTypes();
        setSuratTypes(types);
        if (types.length > 0 && !selectedKodeSurat) {
          setSelectedKodeSurat(types[0].kode_surat);
        }
      } catch {
        // Fallback
      }

      try {
        const reqs = await suratService.getSuratRequests();
        setRequests(reqs);
      } catch {
        // Fallback
      } finally {
        setIsLoadingRequests(false);
      }
    };

    loadInitialData();
  }, []);

  // Initialize Chat Session when chat tab is opened
  useEffect(() => {
    if (activeMainView === 'dashboard' && activeDashboardTab === 'chat' && !chatThreadId) {
      initChatSession();
    }
  }, [activeMainView, activeDashboardTab]);

  // Auto-scroll chat to bottom
  useEffect(() => {
    if (activeMainView === 'dashboard' && activeDashboardTab === 'chat') {
      chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [chatMessages, isChatLoading, activeDashboardTab]);

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
      setChatRequiredFields([]);
      setChatIsReadyToDraft(false);
      setChatDetectedIntent(docType || null);
    } catch {
      setChatMessages([
        {
          id: 'err-init',
          sender: 'system',
          text: 'Gagal menginisialisasi sesi percakapan dengan agen AI. Pastikan server aktif.',
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    } finally {
      setIsChatLoading(false);
    }
  };

  const handleSendChatMessage = async (textToSend?: string) => {
    const message = textToSend || chatInput;
    if (!message.trim() || !chatThreadId || isChatLoading) return;

    const userText = message.trim();
    setChatInput('');
    setShowMentionMenu(false);

    const userMsgObj: ChatMessageItem = {
      id: `user-${Date.now()}`,
      sender: 'user',
      text: userText,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };
    setChatMessages((prev) => [...prev, userMsgObj]);
    setIsChatLoading(true);

    try {
      const response = await suratService.sendChatMessage(chatThreadId, userText);

      if (response.detected_intent) {
        setChatDetectedIntent(response.detected_intent);
      }
      if (response.kode_surat) {
        setChatDetectedIntent(response.kode_surat);
      }
      if (response.collected_slots) {
        setChatCollectedSlots(response.collected_slots);
      }
      if (response.required_fields) {
        setChatRequiredFields(response.required_fields);
      }
      if (response.state === 'READY_TO_DRAFT' || response.status === 'ready_to_draft') {
        setChatIsReadyToDraft(true);
      }

      const botMsgObj: ChatMessageItem = {
        id: `assistant-${Date.now()}`,
        sender: 'assistant',
        text: response.reply,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setChatMessages((prev) => [...prev, botMsgObj]);
    } catch {
      setChatMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          sender: 'system',
          text: 'Terjadi gangguan komunikasi dengan agen AI. Silakan coba kirim ulang.',
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    } finally {
      setIsChatLoading(false);
    }
  };

  const handleProceedFromChatToSubmission = async () => {
    const finalKodeSurat = chatDetectedIntent || selectedKodeSurat || 'SK-KUL';
    setIsChatLoading(true);

    try {
      const promptSummary = chatMessages
        .filter((m) => m.sender === 'user')
        .map((m) => m.text)
        .join('\n');

      const result = await suratService.createSuratRequest({
        kode_surat: finalKodeSurat,
        user_prompt_context: promptSummary || 'Permohonan melalui sesi dialog AI Chat',
        payload_data: chatCollectedSlots,
        chosen_destination: chatCollectedSlots.chosen_destination || 'email',
        target_destination_address: chatCollectedSlots.target_destination_address || '',
        attachments: chatAttachments.length > 0 ? chatAttachments : undefined,
      });

      const reqId = result.request_id || result.data?.request_id;
      if (reqId) {
        navigate(`/surat/${reqId}`);
      } else {
        setActiveDashboardTab('form');
      }
    } catch (err: any) {
      alert(extractErrorMessage(err, 'Gagal meneruskan draf dari sesi chat.'));
    } finally {
      setIsChatLoading(false);
    }
  };

  // =========================================================================
  // FORM SURAT ACTIONS
  // =========================================================================
  const activeFields: DynamicFieldDef[] = selectedKodeSurat
    ? REQUIRED_FIELDS_BY_KODE[selectedKodeSurat] || DEFAULT_REQUIRED_FIELDS
    : DEFAULT_REQUIRED_FIELDS;

  const handleFormFieldChange = (fieldName: string, value: any) => {
    setFormPayloadData((prev) => ({
      ...prev,
      [fieldName]: value,
    }));
  };

  const handleFormFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const filesArr = Array.from(e.target.files);
      setFormAttachments((prev) => [...prev, ...filesArr]);
    }
  };

  const handleFormRemoveFile = (index: number) => {
    setFormAttachments((prev) => prev.filter((_, i) => i !== index));
  };

  const handleFormSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedKodeSurat) {
      setFormErrorMsg('Pilih jenis surat dinas yang akan diajukan.');
      return;
    }

    setFormErrorMsg(null);
    setFormSuccessMsg(null);
    setIsSubmittingForm(true);

    try {
      const result = await suratService.createSuratRequest({
        kode_surat: selectedKodeSurat,
        user_prompt_context: formPromptContext,
        payload_data: formPayloadData,
        chosen_destination: formChosenDestination || undefined,
        target_destination_address: formTargetDestination || undefined,
        attachments: formAttachments.length > 0 ? formAttachments : undefined,
      });

      setFormSuccessMsg(result.message || 'Permohonan surat dinas berhasil dikirim ke agen AI.');

      const reqId = result.request_id || result.data?.request_id;
      setTimeout(() => {
        if (reqId) {
          navigate(`/surat/${reqId}`);
        } else {
          suratService.getSuratRequests().then(setRequests);
        }
      }, 1200);
    } catch (err: any) {
      setFormErrorMsg(
        extractErrorMessage(err, 'Terjadi kesalahan saat memproses permohonan surat.')
      );
    } finally {
      setIsSubmittingForm(false);
    }
  };

  // =========================================================================
  // VERIFIKASI TTE ACTIONS
  // =========================================================================
  const handleVerifySubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const token = verifyTokenInput.trim();
    if (!token) return;

    setIsVerifying(true);
    setVerifyErrorMsg(null);
    setVerifyResult(null);

    try {
      const res = await suratService.verifySurat(token);
      setVerifyResult(res);
    } catch (err: any) {
      if (err.response?.status === 404) {
        setVerifyResult({
          status: 'INVALID',
          message:
            'Dokumen Surat tidak valid atau palsu. Token verifikasi tidak terdaftar pada repositori persuratan dinas resmi.',
        });
      } else {
        setVerifyErrorMsg(
          err.response?.data?.message || 'Gagal menghubungi server verifikasi dokumen persuratan.'
        );
      }
    } finally {
      setIsVerifying(false);
    }
  };

  const currentSelectedSuratObj = suratTypes.find((s) => s.kode_surat === selectedKodeSurat);

  return (
    <div className="flex h-screen bg-slate-100/70 overflow-hidden font-sans">
      {/* 1. PERSISTENT LEFT SIDEBAR (REPLACES NAVBAR ON DESKTOP & MOBILE DRAWER) */}
      <DashboardSidebar
        isOpen={isSidebarOpen}
        onClose={() => setIsSidebarOpen(false)}
        activeMainView={activeMainView}
        onSelectMainView={(view) => setActiveMainView(view)}
        onSelectLetterInForm={(kode) => {
          setActiveMainView('dashboard');
          setActiveDashboardTab('form');
          setSelectedKodeSurat(kode);
          setFormPayloadData({});
        }}
        suratTypes={suratTypes}
        selectedKodeSurat={selectedKodeSurat}
      />

      {/* 2. CENTRAL WORKSPACE AREA */}
      <div className="flex-1 flex flex-col h-full min-w-0 overflow-hidden">
        {/* Mobile Header Bar (Only visible on screens < lg) */}
        <header className="lg:hidden h-14 bg-white border-b border-slate-200 px-4 flex items-center justify-between shrink-0 z-20">
          <div className="flex items-center space-x-3">
            <button
              onClick={() => setIsSidebarOpen(true)}
              className="p-1.5 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition"
              aria-label="Buka menu navigasi"
            >
              <Menu className="w-5 h-5" />
            </button>
            <div className="flex items-center space-x-1.5">
              <span className="font-semibold text-sm tracking-tight text-slate-900">AutoSurat</span>
              <span className="text-[10px] px-1 rounded bg-blue-50 text-blue-700 border border-blue-200">
                v2.0
              </span>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <div className="w-7 h-7 rounded-full bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-700 text-xs font-semibold">
              <UserIcon className="w-3.5 h-3.5" />
            </div>
          </div>
        </header>

        {/* Central Dedicated Rounded Container (`rounded-2xl`) */}
        <main className="flex-1 p-3 sm:p-5 md:p-6 overflow-hidden flex flex-col">
          <div className="w-full h-full bg-white border border-slate-200/90 rounded-2xl shadow-xs flex flex-col overflow-hidden">
            {/* ========================================================================= */}
            {/* VIEW A: DASBOR (FORMULIR SURAT & SESI CHAT AI)                            */}
            {/* ========================================================================= */}
            {activeMainView === 'dashboard' && (
              <>
                {/* CONTAINER TOP BAR: SEGMENTED CONTROL */}
                <div className="h-14 px-4 sm:px-6 border-b border-slate-100 flex items-center justify-between shrink-0 bg-white">
                  {/* Segmented Control / Dual-Mode Switcher */}
                  <div className="bg-slate-100/90 p-1 rounded-xl inline-flex items-center space-x-1">
                    <button
                      type="button"
                      onClick={() => setActiveDashboardTab('form')}
                      className={`inline-flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-xs transition-all ${
                        activeDashboardTab === 'form'
                          ? 'bg-white text-slate-900 font-semibold shadow-2xs'
                          : 'text-slate-600 hover:text-slate-900 font-normal'
                      }`}
                    >
                      <FileText className="w-3.5 h-3.5" />
                      <span>Formulir Surat</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => setActiveDashboardTab('chat')}
                      className={`inline-flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-xs transition-all ${
                        activeDashboardTab === 'chat'
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
                    {activeDashboardTab === 'form' && currentSelectedSuratObj && (
                      <span className="text-[11px] px-2 py-0.5 rounded font-normal bg-slate-100 text-slate-700 border border-slate-200 truncate max-w-[140px] sm:max-w-none">
                        {currentSelectedSuratObj.kode_surat}
                      </span>
                    )}
                    {activeDashboardTab === 'chat' && chatDetectedIntent && (
                      <span className="text-[11px] px-2 py-0.5 rounded font-normal bg-blue-50 text-blue-700 border border-blue-200">
                        {chatDetectedIntent}
                      </span>
                    )}
                  </div>
                </div>

                {/* CONTAINER CONTENT AREA */}
                <div className="flex-1 overflow-hidden relative flex flex-col">
                  {/* SUB-VIEW 1: FORMULIR SURAT WORKSPACE (DROPDOWN SELECTION) */}
                  {activeDashboardTab === 'form' && (
                    <div className="flex-1 overflow-y-auto p-4 sm:p-7 space-y-6">
                      {/* Form Header */}
                      <div className="border-b border-slate-100 pb-4">
                        <h1 className="text-base sm:text-lg font-semibold text-slate-900 tracking-tight">
                          Pengajuan Surat Resmi Akademik
                        </h1>
                        <p className="text-xs font-normal text-slate-500 mt-1">
                          Pilih jenis surat dari dropdown dan lengkapi atribut wajib. Agen AI akan memvalidasi tata naskah dinas sebelum diteruskan ke dosen.
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
                        {/* 1. DROPDOWN SELECTION FOR SURAT TYPES */}
                        <div className="space-y-2">
                          <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider">
                            Pilih Jenis Surat Resmi Kampus
                          </label>

                          <div className="relative">
                            <select
                              value={selectedKodeSurat}
                              onChange={(e) => {
                                setSelectedKodeSurat(e.target.value);
                                setFormPayloadData({});
                              }}
                              className="w-full px-3.5 py-2.5 text-xs font-normal border border-slate-300 rounded-lg bg-white text-slate-900 focus:border-slate-900 focus:ring-1 focus:ring-slate-900 focus:outline-none transition appearance-none cursor-pointer"
                            >
                              <optgroup label="Surat Keterangan">
                                <option value="SK-KUL">
                                  Surat Keterangan Aktif Kuliah (SK-KUL)
                                </option>
                                <option value="SK-BEA">
                                  Surat Keterangan Beasiswa (SK-BEA)
                                </option>
                              </optgroup>

                              <optgroup label="Surat Pengantar">
                                <option value="SP-MAG">
                                  Surat Pengantar Magang (SP-MAG)
                                </option>
                                <option value="SP-TAS">
                                  Surat Pengantar Tugas Akhir / Skripsi (SP-TAS)
                                </option>
                                <option value="SP-TRA">
                                  Surat Pengantar Transkrip Nilai (SP-TRA)
                                </option>
                                <option value="SP-SKC">
                                  Surat Pengantar SKCK (SP-SKC)
                                </option>
                              </optgroup>

                              <optgroup label="Surat Rekomendasi & Izin">
                                <option value="SR-BEA">
                                  Surat Rekomendasi Beasiswa (SR-BEA)
                                </option>
                                <option value="SR-MAG">
                                  Surat Rekomendasi Magang (SR-MAG)
                                </option>
                                <option value="SI-MAG">
                                  Surat Izin Magang (SI-MAG)
                                </option>
                                <option value="SI-SUR">
                                  Surat Izin Survei & Riset Observasi (SI-SUR)
                                </option>
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

                        {/* 2. Context Natural Language */}
                        <div className="space-y-1.5">
                          <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider">
                            Konteks Permohonan (Bahasa Alami)
                          </label>
                          <textarea
                            rows={3}
                            value={formPromptContext}
                            onChange={(e) => setFormPromptContext(e.target.value)}
                            placeholder="Contoh: Saya membutuhkan surat pengantar magang di PT Telekomunikasi Indonesia untuk posisi Software Engineer selama 6 bulan..."
                            className="w-full p-3 rounded-lg border border-slate-200 bg-slate-50/50 text-xs font-normal text-slate-900 focus:bg-white focus:border-slate-900 focus:outline-none transition leading-relaxed"
                          />
                        </div>

                        {/* 3. Dynamic Mandatory Parameters Form */}
                        <div className="space-y-3 pt-2 border-t border-slate-100">
                          <div className="flex items-center justify-between">
                            <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider">
                              Parameter Wajib Dokumen ({selectedKodeSurat})
                            </label>
                            <span className="text-[11px] font-normal text-slate-400">
                              {activeFields.length} atribut wajib
                            </span>
                          </div>

                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                            {activeFields.map((fieldDef) => {
                              const val = formPayloadData[fieldDef.field] ?? '';
                              return (
                                <div key={fieldDef.field} className="space-y-1">
                                  <label className="block text-xs font-semibold text-slate-800">
                                    {fieldDef.label} <span className="text-rose-500">*</span>
                                  </label>
                                  {fieldDef.type === 'date' ? (
                                    <input
                                      type="date"
                                      value={val}
                                      onChange={(e) =>
                                        handleFormFieldChange(fieldDef.field, e.target.value)
                                      }
                                      className="w-full px-3 py-2 text-xs font-normal border border-slate-200 rounded-lg bg-white text-slate-900 focus:border-slate-900 focus:outline-none"
                                      required
                                    />
                                  ) : (
                                    <input
                                      type="text"
                                      value={val}
                                      onChange={(e) =>
                                        handleFormFieldChange(fieldDef.field, e.target.value)
                                      }
                                      placeholder={fieldDef.description || fieldDef.label}
                                      className="w-full px-3 py-2 text-xs font-normal border border-slate-200 rounded-lg bg-white text-slate-900 focus:border-slate-900 focus:outline-none"
                                      required
                                    />
                                  )}
                                  <p className="text-[10px] font-normal text-slate-400 truncate">
                                    {fieldDef.description}
                                  </p>
                                </div>
                              );
                            })}
                          </div>
                        </div>

                        {/* 4. Delivery Channel (Email vs Telegram) */}
                        <div className="space-y-3 pt-2 border-t border-slate-100">
                          <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider">
                            Kanal Pengiriman PDF Resmi
                          </label>
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <label
                              className={`p-3 rounded-lg border text-xs cursor-pointer flex items-center space-x-3 transition ${
                                formChosenDestination === 'email'
                                  ? 'border-slate-900 bg-slate-50 font-semibold'
                                  : 'border-slate-200 hover:bg-slate-50 font-normal'
                              }`}
                            >
                              <input
                                type="radio"
                                name="destination"
                                value="email"
                                checked={formChosenDestination === 'email'}
                                onChange={() => setFormChosenDestination('email')}
                                className="sr-only"
                              />
                              <div className="w-4 h-4 rounded-full border border-slate-400 flex items-center justify-center shrink-0">
                                {formChosenDestination === 'email' && (
                                  <div className="w-2 h-2 rounded-full bg-slate-900" />
                                )}
                              </div>
                              <div>
                                <div className="text-slate-900">Email Pribadi Mahasiswa</div>
                                <div className="text-[11px] text-slate-500 font-normal">
                                  Dokumen dikirimkan via inbox surel
                                </div>
                              </div>
                            </label>

                            <label
                              className={`p-3 rounded-lg border text-xs cursor-pointer flex items-center space-x-3 transition ${
                                formChosenDestination === 'telegram'
                                  ? 'border-slate-900 bg-slate-50 font-semibold'
                                  : 'border-slate-200 hover:bg-slate-50 font-normal'
                              }`}
                            >
                              <input
                                type="radio"
                                name="destination"
                                value="telegram"
                                checked={formChosenDestination === 'telegram'}
                                onChange={() => setFormChosenDestination('telegram')}
                                className="sr-only"
                              />
                              <div className="w-4 h-4 rounded-full border border-slate-400 flex items-center justify-center shrink-0">
                                {formChosenDestination === 'telegram' && (
                                  <div className="w-2 h-2 rounded-full bg-slate-900" />
                                )}
                              </div>
                              <div>
                                <div className="text-slate-900">Bot Notifikasi Telegram</div>
                                <div className="text-[11px] text-slate-500 font-normal">
                                  Dikirim langsung ke Chat ID Telegram
                                </div>
                              </div>
                            </label>
                          </div>

                          <input
                            type="text"
                            value={formTargetDestination}
                            onChange={(e) => setFormTargetDestination(e.target.value)}
                            placeholder={
                              formChosenDestination === 'email'
                                ? 'Masukkan alamat email penerima (opsional jika sesuai akun)'
                                : 'Masukkan nomor Chat ID Telegram Anda'
                            }
                            className="w-full px-3 py-2 text-xs font-normal border border-slate-200 rounded-lg bg-white text-slate-900 focus:border-slate-900 focus:outline-none"
                          />
                        </div>

                        {/* 5. Multimodal Attachments */}
                        <div className="space-y-2 pt-2 border-t border-slate-100">
                          <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider">
                            Lampiran Dokumen Multimodal (Opsional)
                          </label>
                          <div className="flex flex-wrap items-center gap-2">
                            <label className="inline-flex items-center px-3 py-2 border border-slate-300 rounded-lg text-xs font-normal text-slate-700 hover:bg-slate-50 cursor-pointer transition shadow-2xs">
                              <Paperclip className="w-3.5 h-3.5 mr-1.5 text-slate-500" />
                              <span>Pilih Berkas PDF / Gambar</span>
                              <input
                                type="file"
                                multiple
                                accept=".pdf,image/*"
                                onChange={handleFormFileChange}
                                className="hidden"
                              />
                            </label>
                            <span className="text-[11px] font-normal text-slate-400">
                              Mendukung LoA magang, transkrip, SK beasiswa (diekstrak langsung oleh Gemini Multimodal).
                            </span>
                          </div>

                          {formAttachments.length > 0 && (
                            <div className="flex flex-wrap gap-2 mt-2">
                              {formAttachments.map((f, i) => (
                                <span
                                  key={i}
                                  className="inline-flex items-center px-2.5 py-1 rounded bg-slate-100 text-xs font-normal text-slate-800 border border-slate-200"
                                >
                                  <span className="truncate max-w-[200px]">{f.name}</span>
                                  <button
                                    type="button"
                                    onClick={() => handleFormRemoveFile(i)}
                                    className="ml-1.5 text-slate-400 hover:text-rose-600"
                                  >
                                    <X className="w-3 h-3" />
                                  </button>
                                </span>
                              ))}
                            </div>
                          )}
                        </div>

                        {/* Submit Button */}
                        <div className="pt-4 border-t border-slate-100 flex items-center justify-between">
                          <div className="text-xs font-normal text-slate-500">
                            Status awal permohonan: <span className="font-semibold text-slate-800">SUBMITTED</span>
                          </div>

                          <button
                            type="submit"
                            disabled={isSubmittingForm}
                            className="px-5 py-2.5 rounded-lg bg-slate-900 text-white text-xs font-semibold hover:bg-slate-800 disabled:opacity-50 transition shadow-xs flex items-center space-x-2"
                          >
                            {isSubmittingForm ? (
                              <>
                                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                                <span>Mendelegasikan ke Agen AI...</span>
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

                      {/* Riwayat Permohonan Terkini */}
                      {requests.length > 0 && (
                        <div className="pt-8 border-t border-slate-200 space-y-3">
                          <div className="flex items-center justify-between">
                            <h2 className="text-xs font-semibold text-slate-900 uppercase tracking-wider">
                              Riwayat Permohonan Terkini ({requests.length})
                            </h2>
                          </div>

                          <div className="border border-slate-200 rounded-xl overflow-hidden divide-y divide-slate-100 bg-white">
                            {requests.slice(0, 5).map((req) => (
                              <div
                                key={req.id}
                                className="p-3 sm:p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 hover:bg-slate-50/70 transition"
                              >
                                <div className="space-y-1">
                                  <div className="flex items-center space-x-2">
                                    <span className="text-[11px] px-1.5 py-0.2 rounded bg-slate-100 text-slate-700 font-semibold">
                                      {req.kode_surat}
                                    </span>
                                    <span className="text-xs font-semibold text-slate-900">
                                      {req.nama_surat}
                                    </span>
                                  </div>
                                  <div className="text-[11px] font-normal text-slate-400">
                                    ID: #{req.id} • Dibuat:{' '}
                                    {new Date(req.created_at).toLocaleDateString('id-ID', {
                                      day: 'numeric',
                                      month: 'short',
                                      year: 'numeric',
                                    })}
                                  </div>
                                </div>

                                <div className="flex items-center space-x-3 self-end sm:self-center">
                                  <StatusBadge status={req.status} />
                                  <Link
                                    to={`/surat/${req.id}`}
                                    className="px-2.5 py-1 text-xs font-normal text-slate-700 bg-slate-100 hover:bg-slate-200 rounded transition"
                                  >
                                    Lihat Detail
                                  </Link>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* SUB-VIEW 2: CHAT AI WORKSPACE (MODELED ON AGENTIC IDE) */}
                  {activeDashboardTab === 'chat' && (
                    <div className="flex-1 flex flex-col h-full overflow-hidden bg-slate-50/40">
                      {/* Chat Session Sub-Header */}
                      <div className="h-10 px-4 sm:px-6 border-b border-slate-200/80 bg-white flex items-center justify-between shrink-0 text-xs">
                        <div className="flex items-center space-x-2 truncate">
                          <Sparkles className="w-3.5 h-3.5 text-blue-600 shrink-0" />
                          <span className="font-semibold text-slate-800 truncate">
                            Sesi Dialog Penentuan & Ekstraksi Draf Surat
                          </span>
                        </div>

                        <div className="flex items-center space-x-2 shrink-0">
                          <button
                            onClick={() => initChatSession()}
                            title="Mulai sesi baru"
                            className="px-2 py-1 rounded text-[11px] font-normal text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition flex items-center space-x-1"
                          >
                            <RefreshCw className="w-3 h-3" />
                            <span>Mulai Ulang Sesi</span>
                          </button>
                        </div>
                      </div>

                      {/* Chat Message Stream */}
                      <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
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
                                  className={`text-[10px] font-normal text-slate-400 px-1 ${
                                    isUser ? 'text-right' : 'text-left'
                                  }`}
                                >
                                  {msg.timestamp}
                                </div>
                              </div>
                            </div>
                          );
                        })}

                        {/* Chat AI Loading Indicator */}
                        {isChatLoading && (
                          <div className="flex items-start space-x-2.5 max-w-xl">
                            <div className="w-7 h-7 rounded-lg bg-blue-600 text-white flex items-center justify-center shrink-0">
                              <Bot className="w-3.5 h-3.5 animate-pulse" />
                            </div>
                            <div className="bg-white border border-slate-200 p-3 rounded-2xl rounded-tl-none shadow-2xs text-xs font-normal text-slate-500 flex items-center space-x-2">
                              <RefreshCw className="w-3 h-3 animate-spin text-blue-600" />
                              <span>Agen AI sedang menganalisa maksud dan mengekstrak slot...</span>
                            </div>
                          </div>
                        )}

                        {/* Prompt Suggestions */}
                        {chatMessages.length <= 2 && (
                          <div className="pt-2 space-y-2">
                            <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                              Contoh Panduan Pengajuan Cepat
                            </div>
                            <div className="flex flex-wrap gap-2">
                              {promptSuggestions.map((suggestion, idx) => (
                                <button
                                  key={idx}
                                  onClick={() => handleSendChatMessage(suggestion)}
                                  className="text-left p-2.5 rounded-lg border border-slate-200 bg-white hover:border-slate-400 text-xs font-normal text-slate-800 transition shadow-2xs"
                                >
                                  {suggestion}
                                </button>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* ARTIFACT CARD: LIVE EXTRACTED SLOTS CHECKLIST TELEMETRY */}
                        {chatRequiredFields.length > 0 && (
                          <div className="border border-slate-200 rounded-xl bg-white p-4 shadow-xs space-y-3 max-w-2xl">
                            <div className="flex items-center justify-between border-b border-slate-100 pb-2.5">
                              <div className="flex items-center space-x-2">
                                <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-blue-50 text-blue-800 border border-blue-200">
                                  {chatDetectedIntent || 'SLOT'}
                                </span>
                                <span className="text-xs font-semibold text-slate-900">
                                  Status Kelengkapan Atribut Surat
                                </span>
                              </div>
                              <span className="text-[11px] font-normal text-slate-500">
                                {
                                  chatRequiredFields.filter(
                                    (f) =>
                                      chatCollectedSlots[f.field] &&
                                      String(chatCollectedSlots[f.field]).trim() !== ''
                                  ).length
                                }{' '}
                                / {chatRequiredFields.length} Terpenuhi
                              </span>
                            </div>

                            <div className="space-y-1.5 text-xs">
                              {chatRequiredFields.map((field) => {
                                const val = chatCollectedSlots[field.field];
                                const isFilled = val && String(val).trim() !== '';
                                return (
                                  <div
                                    key={field.field}
                                    className={`p-2 rounded-md border flex items-center justify-between ${
                                      isFilled
                                        ? 'border-emerald-200 bg-emerald-50/40 text-emerald-950'
                                        : 'border-slate-200 bg-slate-50/60 text-slate-600'
                                    }`}
                                  >
                                    <div className="flex items-center space-x-2 truncate">
                                      {isFilled ? (
                                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                                      ) : (
                                        <Clock className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                                      )}
                                      <span className="font-semibold text-slate-900 truncate">
                                        {field.label}:
                                      </span>
                                      <span className="font-normal text-slate-600 truncate">
                                        {isFilled ? String(val) : 'Belum disebutkan'}
                                      </span>
                                    </div>
                                    <span className="text-[10px] font-normal text-slate-400 shrink-0 ml-2">
                                      {field.field}
                                    </span>
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        )}

                        {/* READY TO DRAFT ACTION CARD */}
                        {chatIsReadyToDraft && (
                          <div className="border border-emerald-300 bg-emerald-50/60 rounded-xl p-4 shadow-xs space-y-3 max-w-2xl">
                            <div className="flex items-center space-x-2">
                              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                              <span className="text-xs font-semibold text-emerald-950">
                                Semua Atribut Surat Lengkap & Tervalidasi
                              </span>
                            </div>
                            <p className="text-xs font-normal text-emerald-900 leading-relaxed">
                              Seluruh data wajib untuk jenis surat{' '}
                              <span className="font-semibold">{chatDetectedIntent}</span> telah
                              berhasil diekstrak. Tekan tombol di bawah untuk meneruskan draf ini ke
                              sistem administrasi.
                            </p>
                            <button
                              type="button"
                              onClick={handleProceedFromChatToSubmission}
                              disabled={isChatLoading}
                              className="px-4 py-2 rounded-lg bg-slate-900 text-white text-xs font-semibold hover:bg-slate-800 transition flex items-center space-x-2 shadow-xs"
                            >
                              <span>Lanjutkan & Simpan Draf Permohonan</span>
                              <ArrowRight className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        )}

                        <div ref={chatEndRef} />
                      </div>

                      {/* DOCKED FLOATING PROMPT CAPSULE AT BOTTOM */}
                      <div className="p-3 sm:p-5 border-t border-slate-200/80 bg-white shrink-0">
                        <div className="max-w-4xl mx-auto space-y-2">
                          {/* Floating Rounded Input Box */}
                          <div className="border border-slate-300 rounded-2xl p-2.5 bg-white shadow-xs focus-within:border-slate-900 focus-within:ring-1 focus-within:ring-slate-900 transition-all">
                            {/* Textarea */}
                            <textarea
                              ref={chatInputRef}
                              rows={2}
                              value={chatInput}
                              onChange={(e) => setChatInput(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter' && !e.shiftKey) {
                                  e.preventDefault();
                                  handleSendChatMessage();
                                }
                              }}
                              placeholder="Ketik kebutuhan surat Anda atau jelaskan informasi tambahan..."
                              className="w-full px-2 py-1 text-xs font-normal text-slate-900 placeholder:text-slate-400 focus:outline-none resize-none leading-relaxed"
                            />

                            {/* Input Controls Bar */}
                            <div className="flex items-center justify-between pt-1 border-t border-slate-100">
                              {/* Left Controls: File Attachment & Mention */}
                              <div className="flex items-center space-x-1">
                                <label className="p-1.5 rounded-md text-slate-500 hover:text-slate-900 hover:bg-slate-100 cursor-pointer transition">
                                  <Plus className="w-3.5 h-3.5" />
                                  <input
                                    type="file"
                                    multiple
                                    accept=".pdf,image/*"
                                    onChange={(e) => {
                                      if (e.target.files) {
                                        const filesArr = Array.from(e.target.files);
                                        setChatAttachments((prev) => [...prev, ...filesArr]);
                                      }
                                    }}
                                    className="hidden"
                                  />
                                </label>

                                <button
                                  type="button"
                                  onClick={() => setShowMentionMenu(!showMentionMenu)}
                                  className="p-1.5 rounded-md text-slate-500 hover:text-slate-900 hover:bg-slate-100 transition relative"
                                  title="Pilih jenis surat dinas"
                                >
                                  <AtSign className="w-3.5 h-3.5" />
                                </button>

                                <span className="hidden sm:inline-flex items-center text-[10px] font-normal px-2 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">
                                  <ShieldCheck className="w-2.5 h-2.5 mr-1 text-blue-600" />
                                  Level 2 Guardrail: Zero-Hallucination
                                </span>
                              </div>

                              {/* Right Controls: Submit Button */}
                              <div className="flex items-center space-x-2">
                                <button
                                  type="button"
                                  onClick={() => handleSendChatMessage()}
                                  disabled={!chatInput.trim() || isChatLoading}
                                  className="w-7 h-7 rounded-full bg-slate-900 text-white flex items-center justify-center hover:bg-slate-800 disabled:opacity-30 transition shadow-2xs"
                                  aria-label="Kirim pesan"
                                >
                                  <ArrowUp className="w-3.5 h-3.5" />
                                </button>
                              </div>
                            </div>
                          </div>

                          {/* Mention Popup Menu */}
                          {showMentionMenu && (
                            <div className="p-2 bg-white border border-slate-200 rounded-xl shadow-lg max-h-48 overflow-y-auto space-y-1">
                              <div className="text-[10px] font-semibold text-slate-400 px-2 py-1 uppercase">
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
                                  className="w-full text-left px-2.5 py-1.5 rounded text-xs font-normal text-slate-700 hover:bg-slate-100 flex items-center justify-between"
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
              </>
            )}

            {/* ========================================================================= */}
            {/* VIEW B: VERIFIKASI KEASLIAN TTE (EMBEDDED INSIDE CENTRAL CONTAINER)       */}
            {/* ========================================================================= */}
            {activeMainView === 'verify' && (
              <div className="flex-1 overflow-y-auto p-4 sm:p-8 space-y-6">
                {/* Header */}
                <div className="border-b border-slate-100 pb-4">
                  <div className="flex items-center space-x-2.5 mb-1.5">
                    <ShieldCheck className="w-5 h-5 text-emerald-600" />
                    <h1 className="text-base sm:text-lg font-semibold text-slate-900 tracking-tight">
                      Verifikasi Keaslian TTE Dokumen
                    </h1>
                  </div>
                  <p className="text-xs font-normal text-slate-500 leading-relaxed">
                    Pusat validasi keabsahan dokumen persuratan dinas akademik. Masukkan kode token verifikasi atau nomor dokumen surat yang tertera pada naskah fisik maupun digital.
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
                      className="px-5 py-2.5 rounded-lg bg-slate-900 text-white text-xs font-semibold hover:bg-slate-800 disabled:opacity-50 transition shadow-xs flex items-center justify-center space-x-2 shrink-0"
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
                                Penandatangan: <span className="text-white font-semibold">{verifyResult.tte_info.penandatangan}</span>
                              </div>
                              <div className="text-[10px] font-normal text-slate-400 truncate">
                                Hash SHA-256: <span className="text-emerald-400 font-normal">{verifyResult.tte_info.hash_sha256}</span>
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
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
};

export default DashboardPage;
