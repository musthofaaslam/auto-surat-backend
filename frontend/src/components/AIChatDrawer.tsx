import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import suratService from '../services/suratService';
import {
  Send,
  Bot,
  User as UserIcon,
  CheckCircle2,
  Circle,
  ArrowRight,
  RefreshCw,
  Sparkles,
  HelpCircle,
  Layers,
  ChevronDown,
  ChevronUp,
  MessageSquare,
  Zap,
  Mail,
  X,
} from 'lucide-react';
import type { DynamicFieldDef, ChatActionOption } from '../types';

interface Message {
  id?: string;
  sender: 'user' | 'assistant' | 'system';
  text: string;
  timestamp: string;
  action_required?: 'delivery_method' | 'switch_confirmation' | string | null;
  action_options?: ChatActionOption[];
}

interface AIChatDrawerProps {
  initialDocumentType?: string;
  onDraftReady?: (data: {
    kode_surat: string;
    collected_slots: Record<string, any>;
    promptContext: string;
  }) => void;
}

// Architectural Note:
// Stateful conversational agent interface. Real-time slot extraction telemetry,
// quick-start prompt suggestions, and seamless transition to official document drafting.

export const AIChatDrawer: React.FC<AIChatDrawerProps> = ({
  initialDocumentType,
  onDraftReady,
}) => {
  const navigate = useNavigate();
  const [threadId, setThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [detectedIntent, setDetectedIntent] = useState<string | null>(initialDocumentType || null);
  const [collectedSlots, setCollectedSlots] = useState<Record<string, any>>({});
  const [requiredFields, setRequiredFields] = useState<DynamicFieldDef[]>([]);
  const [isReadyToDraft, setIsReadyToDraft] = useState(false);
  const [mobileSlotsOpen, setMobileSlotsOpen] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const promptSuggestions = [
    'Saya butuh surat keterangan aktif kuliah untuk beasiswa PT Pertamina semester ini.',
    'Mohon buatkan surat rekomendasi magang di PT Telkom Indonesia divisi Backend.',
    'Pengantar izin riset skripsi di Rumah Sakit Umum Daerah selama 3 bulan.',
  ];

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    initChatThread();
  }, [initialDocumentType]);

  const initChatThread = async () => {
    setIsLoading(true);
    try {
      const initRes = await suratService.initChat(
        'Konsultasi Pengajuan Surat',
        initialDocumentType || null
      );
      setThreadId(initRes.thread_id);
      setMessages([
        {
          sender: 'assistant',
          text:
            'Halo! Saya asisten cerdas persuratan dinas akademik. ' +
            'Silakan jelaskan surat dinas yang Anda perlukan beserta tujuannya dalam bahasa alami. ' +
            'Saya akan mengekstrak atribut wajib dan memvalidasi kelengkapannya secara otomatis.',
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
      setCollectedSlots({});
      setRequiredFields([]);
      setIsReadyToDraft(false);
    } catch {
      setMessages([
        {
          sender: 'system',
          text: 'Gagal menginisialisasi sesi percakapan dengan agen AI. Pastikan server backend aktif.',
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSendMessage = async (textToSend?: string) => {
    const message = textToSend || inputMessage;
    if (!message.trim() || !threadId || isLoading) return;

    const userText = message.trim();
    setInputMessage('');

    const userMsgObj: Message = {
      sender: 'user',
      text: userText,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };
    setMessages((prev) => [...prev, userMsgObj]);
    setIsLoading(true);

    try {
      const response = await suratService.sendChatMessage(threadId, userText);

      if (response.detected_intent) {
        setDetectedIntent(response.detected_intent);
      }
      if (response.kode_surat) {
        setDetectedIntent(response.kode_surat);
      }
      if (response.collected_slots) {
        setCollectedSlots(response.collected_slots);
      }
      if (response.required_fields) {
        setRequiredFields(response.required_fields);
      }

      if (response.is_ready_to_draft !== undefined) {
        setIsReadyToDraft(response.is_ready_to_draft);
      } else {
        const isReady =
          response.state === 'READY_TO_DRAFT' || response.status === 'ready_to_draft';
        setIsReadyToDraft(isReady);
      }

      const botMsgObj: Message = {
        id: `bot-${Date.now()}`,
        sender: 'assistant',
        text: response.reply,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        action_required: response.action_required || null,
        action_options: response.action_options || [],
      };
      setMessages((prev) => [...prev, botMsgObj]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          sender: 'system',
          text: 'Terjadi gangguan komunikasi dengan agen Gemini. Silakan coba kirim ulang.',
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const getActionOptionsForMessage = (msg: Message): ChatActionOption[] => {
    if (msg.action_options && msg.action_options.length > 0) {
      return msg.action_options;
    }
    if (msg.action_required === 'delivery_method') {
      return [
        { label: 'Email', value: 'Email' },
        { label: 'Telegram', value: 'Telegram' },
      ];
    }
    if (msg.action_required === 'switch_confirmation') {
      return [
        { label: 'Ya, Beralih Surat', value: 'Ya' },
        { label: 'Tidak, Lanjutkan Sebelumnya', value: 'Tidak' },
      ];
    }
    if (msg.action_required === 'intent_clarification') {
      return [
        { label: 'Surat Pengantar Magang (SP-MAG)', value: 'SP-MAG' },
        { label: 'Surat Rekomendasi Magang (SR-MAG)', value: 'SR-MAG' },
        { label: 'Surat Izin Magang (SI-MAG)', value: 'SI-MAG' },
      ];
    }
    const lowerText = msg.text.toLowerCase();
    if (
      lowerText.includes('apakah anda ingin membatalkan') ||
      lowerText.includes('beralih membuat') ||
      lowerText.includes("ketik 'ya'") ||
      lowerText.includes("ketik **'ya'**")
    ) {
      return [
        { label: 'Ya, Beralih Surat', value: 'Ya' },
        { label: 'Tidak, Lanjutkan Sebelumnya', value: 'Tidak' },
      ];
    }
    return [];
  };

  const handleProceedToForm = () => {
    const promptSummary = messages
      .filter((m) => m.sender === 'user')
      .map((m) => m.text)
      .join('\n');

    if (onDraftReady && detectedIntent) {
      onDraftReady({
        kode_surat: detectedIntent,
        collected_slots: collectedSlots,
        promptContext: promptSummary,
      });
      return;
    }

    navigate('/surat/new', {
      state: {
        prefilledKodeSurat: detectedIntent,
        prefilledPayload: collectedSlots,
        prefilledPrompt: promptSummary,
      },
    });
  };

  const filledCount = requiredFields.filter((f) => {
    const val = collectedSlots[f.field];
    return val !== undefined && val !== null && val !== '';
  }).length;

  const progressPercent = requiredFields.length > 0 ? Math.round((filledCount / requiredFields.length) * 100) : 0;

  return (
    <div className="ts-card flex flex-col h-[700px] bg-white overflow-hidden shadow-md">
      {/* 1. HEADER */}
      <div className="flex items-center justify-between px-6 py-4 bg-slate-900 text-white">
        <div className="flex items-center space-x-3">
          <div className="w-8 h-8 rounded-lg bg-slate-800 flex items-center justify-center text-blue-400 shadow-2xs">
            <Bot className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h3 className="text-sm font-bold tracking-tight">
                AutoSurat Intelligent Assistant
              </h3>
              <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-blue-900/60 text-blue-300 border border-blue-700/50">
                Gemini 3.1 Flash Lite
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              {detectedIntent
                ? `Jenis Surat Terdeteksi: [${detectedIntent}]`
                : 'Menunggu penjelasan kebutuhan surat dinas Anda'}
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          {requiredFields.length > 0 && (
            <button
              onClick={() => setMobileSlotsOpen(!mobileSlotsOpen)}
              className="md:hidden inline-flex items-center text-xs bg-slate-800 text-slate-200 px-2.5 py-1 rounded"
            >
              <Layers className="w-3.5 h-3.5 mr-1" />
              <span>{filledCount}/{requiredFields.length}</span>
              {mobileSlotsOpen ? <ChevronUp className="w-3.5 h-3.5 ml-1" /> : <ChevronDown className="w-3.5 h-3.5 ml-1" />}
            </button>
          )}

          <button
            onClick={initChatThread}
            title="Mulai sesi baru"
            className="p-2 rounded-md text-slate-400 hover:text-white hover:bg-slate-800 transition ts-btn"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* 2. CHAT HISTORY & SLOT SIDEBAR */}
      <div className="flex-1 flex flex-col md:flex-row overflow-hidden relative">
        {/* Chat History Panel */}
        <div className="flex-1 flex flex-col p-6 overflow-y-auto bg-slate-50/60 space-y-4">
          {(() => {
            const latestAssistantIdx = messages.map((m, i) => m.sender === 'assistant' ? i : -1).filter((i) => i !== -1).pop();

            return messages.map((msg, idx) => {
              const actionOptions = msg.sender === 'assistant' ? getActionOptionsForMessage(msg) : [];
              const isLatestAssistant = idx === latestAssistantIdx;
              const isDeliveryAction = msg.action_required === 'delivery_method';
              const isDeliveryAlreadyChosen = isDeliveryAction && Boolean(collectedSlots.chosen_destination);
              const isButtonsDisabled = isLoading || !isLatestAssistant || isDeliveryAlreadyChosen;

              return (
                <div
                  key={idx}
                  className={`flex items-start space-x-3 max-w-[85%] ${
                    msg.sender === 'user' ? 'ml-auto flex-row-reverse space-x-reverse' : ''
                  }`}
                >
                  <div
                    className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 ${
                      msg.sender === 'user'
                        ? 'bg-slate-900 text-white'
                        : msg.sender === 'assistant'
                        ? 'bg-blue-600 text-white'
                        : 'bg-amber-100 text-amber-800'
                    }`}
                  >
                    {msg.sender === 'user' ? (
                      <UserIcon className="w-4 h-4" />
                    ) : (
                      <Bot className="w-4 h-4" />
                    )}
                  </div>

                  <div
                    className={`rounded-xl px-4 py-3 text-sm leading-relaxed ${
                      msg.sender === 'user'
                        ? 'bg-slate-900 text-white shadow-xs'
                        : msg.sender === 'assistant'
                        ? 'bg-white border border-slate-200 text-slate-900 shadow-2xs'
                        : 'bg-amber-50 border border-amber-200 text-amber-900'
                    }`}
                  >
                    <p className="whitespace-pre-wrap">{msg.text}</p>

                    {/* Interactive Option Buttons */}
                    {actionOptions.length > 0 && (
                      <div className="mt-3.5 pt-3 border-t border-slate-100 flex flex-wrap gap-2">
                        {actionOptions.map((opt) => {
                          const valLower = opt.value.toLowerCase();
                          const isEmail = valLower === 'email';
                          const isTelegram = valLower === 'telegram';
                          const isYes = valLower === 'ya' || valLower.startsWith('ya');
                          const isNo = valLower === 'tidak' || valLower.startsWith('tidak');

                          let buttonStyle = 'border-slate-300 bg-white hover:bg-slate-50 text-slate-800';
                          if (isYes) {
                            buttonStyle = 'border-emerald-300 bg-emerald-50 hover:bg-emerald-100 text-emerald-800 font-semibold';
                          } else if (isNo) {
                            buttonStyle = 'border-slate-300 bg-slate-50 hover:bg-slate-100 text-slate-700';
                          }

                          return (
                            <button
                              key={opt.value}
                              type="button"
                              disabled={isButtonsDisabled}
                              onClick={() => handleSendMessage(opt.value)}
                              className={`px-3 py-1 rounded-lg border text-xs font-medium shadow-2xs transition flex items-center space-x-1.5 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ${buttonStyle}`}
                            >
                              {isEmail && <Mail className="w-3.5 h-3.5 text-blue-600" />}
                              {isTelegram && <Send className="w-3.5 h-3.5 text-sky-600" />}
                              {isYes && <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />}
                              {isNo && <X className="w-3.5 h-3.5 text-slate-500" />}
                              {!isEmail && !isTelegram && !isYes && !isNo && (
                                <ArrowRight className="w-3.5 h-3.5 text-slate-600" />
                              )}
                              <span>{opt.label}</span>
                            </button>
                          );
                        })}
                      </div>
                    )}

                    <span
                      className={`block text-[10px] font-mono mt-1.5 ${
                        msg.sender === 'user' ? 'text-slate-400 text-right' : 'text-slate-400'
                      }`}
                    >
                      {msg.timestamp}
                    </span>
                  </div>
                </div>
              );
            });
          })()}

          {isLoading && (
            <div className="flex items-center space-x-3 max-w-[70%]">
              <div className="w-7 h-7 rounded-full bg-blue-600 text-white flex items-center justify-center shrink-0">
                <Bot className="w-4 h-4" />
              </div>
              <div className="bg-white border border-slate-200 rounded-xl px-4 py-3 text-xs text-slate-600 shadow-2xs flex items-center space-x-2">
                <span className="w-2 h-2 rounded-full bg-blue-600 animate-pulse" />
                <span className="w-2 h-2 rounded-full bg-blue-600 animate-pulse delay-150" />
                <span className="w-2 h-2 rounded-full bg-blue-600 animate-pulse delay-300" />
                <span className="text-xs font-medium ml-1">Menganalisis konteks percakapan & mengekstrak data...</span>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Dynamic Slot Checklist Sidebar */}
        <div
          className={`${
            mobileSlotsOpen ? 'flex' : 'hidden md:flex'
          } w-full md:w-72 border-t md:border-t-0 md:border-l border-slate-200 bg-white p-5 flex-col overflow-y-auto max-h-72 md:max-h-full`}
        >
          <div className="pb-3 border-b border-slate-200">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-1.5 text-xs font-bold uppercase tracking-wider text-slate-900">
                <Sparkles className="w-4 h-4 text-blue-600" />
                <span>Atribut Surat Dinas</span>
              </div>
              {requiredFields.length > 0 && (
                <span className="text-xs font-mono font-bold text-slate-800 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
                  {filledCount}/{requiredFields.length}
                </span>
              )}
            </div>

            {requiredFields.length > 0 && (
              <div className="mt-2.5 w-full bg-slate-100 h-1.5 rounded-full overflow-hidden">
                <div
                  className="bg-emerald-600 h-full transition-all duration-300"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
            )}
          </div>

          <div className="mt-4 flex-1 space-y-2.5">
            {requiredFields.length > 0 ? (
              requiredFields.map((field) => {
                const isFilled =
                  collectedSlots[field.field] !== undefined &&
                  collectedSlots[field.field] !== null &&
                  collectedSlots[field.field] !== '';

                return (
                  <div
                    key={field.field}
                    className={`p-3 rounded-lg border text-xs transition-all ${
                      isFilled
                        ? 'border-emerald-200 bg-emerald-50/50 text-emerald-950'
                        : 'border-slate-200 bg-slate-50/50 text-slate-600'
                    }`}
                  >
                    <div className="flex items-center justify-between font-semibold">
                      <span className="truncate pr-1">{field.label}</span>
                      {isFilled ? (
                        <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                      ) : (
                        <Circle className="w-4 h-4 text-slate-300 shrink-0" />
                      )}
                    </div>
                    {isFilled ? (
                      <div className="text-[11px] text-slate-800 font-mono mt-1 truncate font-medium">
                        {String(collectedSlots[field.field])}
                      </div>
                    ) : (
                      <div className="text-[10px] text-slate-400 mt-0.5 truncate">
                        {field.description}
                      </div>
                    )}
                  </div>
                );
              })
            ) : (
              <div className="flex flex-col items-center justify-center p-8 text-center text-slate-400">
                <HelpCircle className="w-8 h-8 mb-2 text-slate-300" />
                <p className="text-xs leading-relaxed">
                  Tuliskan jenis surat dan tujuan Anda pada kotak pesan untuk mendeteksi atribut dinas secara otomatis.
                </p>
              </div>
            )}
          </div>

          {/* Quick Action when ready */}
          {isReadyToDraft && (
            <div className="pt-4 border-t border-slate-200 mt-3">
              <button
                onClick={handleProceedToForm}
                className="w-full inline-flex items-center justify-center px-4 py-2.5 text-xs font-bold text-white bg-emerald-600 hover:bg-emerald-500 rounded-lg transition shadow-xs ts-btn"
              >
                <span>Proses Draf Surat Resmi</span>
                <ArrowRight className="w-4 h-4 ml-2" />
              </button>
            </div>
          )}
        </div>
      </div>

      {/* 3. PROMPT SUGGESTIONS (VISIBLE WHEN FEW MESSAGES) */}
      {messages.length <= 2 && (
        <div className="px-6 py-2 bg-slate-50 border-t border-slate-200 flex items-center space-x-2 overflow-x-auto">
          <Zap className="w-3.5 h-3.5 text-amber-500 shrink-0" />
          <span className="text-[11px] font-semibold text-slate-500 shrink-0">Contoh:</span>
          {promptSuggestions.map((suggestion, idx) => (
            <button
              key={idx}
              onClick={() => handleSendMessage(suggestion)}
              className="text-xs text-slate-700 bg-white hover:bg-slate-100 px-3 py-1 rounded-full border border-slate-200 whitespace-nowrap transition ts-btn shrink-0"
            >
              {suggestion}
            </button>
          ))}
        </div>
      )}

      {/* 4. INPUT COMPOSER */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          handleSendMessage();
        }}
        className="p-4 bg-white border-t border-slate-200 flex items-center space-x-3"
      >
        <input
          type="text"
          value={inputMessage}
          onChange={(e) => setInputMessage(e.target.value)}
          placeholder="Ketik konteks pengajuan surat dinas Anda di sini..."
          disabled={isLoading}
          className="flex-1 px-4 py-2.5 text-sm bg-slate-50 border border-slate-300 rounded-lg focus:bg-white focus:outline-none focus:ring-1 focus:ring-slate-900 focus:border-slate-900 transition"
        />
        <button
          type="submit"
          disabled={isLoading || !inputMessage.trim()}
          className="h-10 px-5 text-sm font-semibold text-white bg-slate-900 hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg shadow-xs transition ts-btn"
        >
          <Send className="w-4 h-4 mr-2" />
          Kirim
        </button>
      </form>
    </div>
  );
};

export default AIChatDrawer;
