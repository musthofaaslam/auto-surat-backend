import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import suratService from '../services/suratService';
import type { SuratType, SuratRequestListItem, MainViewType } from '../types';
import DashboardSidebar from '../components/DashboardSidebar';
import MetricCards from '../components/dashboard/MetricCards';
import QuickActionCard from '../components/dashboard/QuickActionCard';
import RequestHistoryTable from '../components/dashboard/RequestHistoryTable';
import VerifikasiTTE from '../components/dashboard/VerifikasiTTE';
import BuatSurat from '../components/buatsurat/BuatSurat';
import { Menu, User as UserIcon } from 'lucide-react';

interface DashboardPageProps {
  initialView?: MainViewType;
}

export const DashboardPage: React.FC<DashboardPageProps> = ({ initialView }) => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();

  // Mobile drawer state: strictly false by default so mobile users land directly on main content
  const [isSidebarOpen, setIsSidebarOpen] = useState<boolean>(false);

  // Main Active View State: 'dashboard' (Monitoring), 'buat-surat' (Action), or 'verify'
  const [activeMainView, setActiveMainView] = useState<MainViewType>(() => {
    if (initialView) return initialView;
    if (location.pathname === '/buat-surat') return 'buat-surat';
    const viewParam = searchParams.get('view');
    if (viewParam === 'buat-surat' || viewParam === 'verify' || viewParam === 'dashboard') {
      return viewParam;
    }
    return 'dashboard';
  });

  // Selected letter code for BuatSurat action view
  const [selectedKodeSurat, setSelectedKodeSurat] = useState<string>(() => {
    return searchParams.get('surat') || 'SK-KUL';
  });

  // Shared Data States
  const [suratTypes, setSuratTypes] = useState<SuratType[]>([]);
  const [requests, setRequests] = useState<SuratRequestListItem[]>([]);
  const [isLoadingRequests, setIsLoadingRequests] = useState<boolean>(true);

  // Fetch all requests
  const fetchRequests = async () => {
    setIsLoadingRequests(true);
    try {
      const data = await suratService.getSuratRequests();
      setRequests(data);
    } catch {
      // Handled gracefully with fallback empty state
    } finally {
      setIsLoadingRequests(false);
    }
  };

  // Synchronize state with URL parameters
  useEffect(() => {
    const viewParam = searchParams.get('view');
    if (viewParam === 'buat-surat' || viewParam === 'verify' || viewParam === 'dashboard') {
      setActiveMainView(viewParam);
    } else if (location.pathname === '/buat-surat') {
      setActiveMainView('buat-surat');
    } else if (location.pathname === '/dashboard' && !viewParam) {
      setActiveMainView('dashboard');
    }

    const suratParam = searchParams.get('surat');
    if (suratParam) {
      setSelectedKodeSurat(suratParam);
      setActiveMainView('buat-surat');
    }
  }, [searchParams, location.pathname]);

  // Initial data loading: master surat types & user requests
  useEffect(() => {
    let isMounted = true;

    const loadInitialData = async () => {
      try {
        const [typesData, requestsData] = await Promise.all([
          suratService.getSuratTypes(),
          suratService.getSuratRequests(),
        ]);
        if (isMounted) {
          setSuratTypes(typesData);
          setRequests(requestsData);
        }
      } catch {
        // Handled gracefully
      } finally {
        if (isMounted) {
          setIsLoadingRequests(false);
        }
      }
    };

    loadInitialData();

    return () => {
      isMounted = false;
    };
  }, []);

  const handleSelectMainView = (view: MainViewType) => {
    setActiveMainView(view);
    navigate(`/dashboard?view=${view}`, { replace: true });
  };

  const handleSelectLetterInForm = (kodeSurat: string) => {
    setSelectedKodeSurat(kodeSurat);
    setActiveMainView('buat-surat');
    navigate(`/dashboard?view=buat-surat&surat=${kodeSurat}`, { replace: true });
  };

  const handleSubmissionSuccess = (requestId: number) => {
    fetchRequests();
    navigate(`/surat/${requestId}`);
  };

  return (
    <div className="flex h-screen bg-slate-100/70 overflow-hidden font-sans">
      {/* 1. PERSISTENT SIDEBAR NAVIGATION (Desktop persistent, Mobile off-canvas drawer) */}
      <DashboardSidebar
        isOpen={isSidebarOpen}
        onClose={() => setIsSidebarOpen(false)}
        activeMainView={activeMainView}
        onSelectMainView={handleSelectMainView}
        onSelectLetterInForm={handleSelectLetterInForm}
        suratTypes={suratTypes}
        selectedKodeSurat={selectedKodeSurat}
      />

      {/* 2. CENTRAL WORKSPACE AREA */}
      <div className="flex-1 flex flex-col h-full min-w-0 overflow-hidden">
        {/* Mobile Header Bar */}
        <header className="lg:hidden h-14 bg-white border-b border-slate-200 px-4 flex items-center justify-between shrink-0 z-20">
          <div className="flex items-center space-x-3">
            <button
              onClick={() => setIsSidebarOpen(true)}
              className="p-1.5 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition cursor-pointer"
              aria-label="Buka menu navigasi"
            >
              <Menu className="w-5 h-5" />
            </button>
            <span className="font-semibold text-sm tracking-tight text-slate-900">AutoSurat</span>
          </div>

          <div className="flex items-center space-x-2">
            <div className="w-7 h-7 rounded-full bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-700 text-xs font-semibold">
              <UserIcon className="w-3.5 h-3.5" />
            </div>
          </div>
        </header>

        {/* Scrollable Content Container with Smooth View Transitions */}
        <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8 space-y-6">
          {/* ========================================================================= */}
          {/* VIEW 1: DASHBOARD (MONITORING OVERVIEW)                                    */}
          {/* STRICT 3-TIER STRUCTURE:                                                  */}
          {/* 1. Metric Cards (Total Surat, Menunggu Persetujuan, Terbit - NO REVISI)   */}
          {/* 2. Shortcut Navigation CTA (Quick Action to Buat Surat)                   */}
          {/* 3. Riwayat Permohonan (Requests Ledger at the very bottom)                 */}
          {/* ========================================================================= */}
          {activeMainView === 'dashboard' && (
            <div key="dashboard-view" className="space-y-6 motion-view-pane">
              {/* Structure Tier 1: Kartu Metrik Ringkasan Status */}
              <MetricCards requests={requests} isLoading={isLoadingRequests} />

              {/* Structure Tier 2: Shortcut Call to Action ke Halaman Buat Surat */}
              <QuickActionCard
                onNavigateToBuatSurat={() => handleSelectMainView('buat-surat')}
              />

              {/* Structure Tier 3: Riwayat Permohonan Naskah Dinas */}
              <RequestHistoryTable
                requests={requests}
                isLoading={isLoadingRequests}
                onRefresh={fetchRequests}
              />
            </div>
          )}

          {/* ========================================================================= */}
          {/* VIEW 2: BUAT SURAT (ACTION STUDIO)                                        */}
          {/* ISOLATED VIEW: Form Input Surat & Sesi Chat AI                             */}
          {/* Metric Cards and Riwayat Permohonan are strictly excluded                 */}
          {/* ========================================================================= */}
          {activeMainView === 'buat-surat' && (
            <div key="buat-surat-view" className="motion-view-pane">
              <BuatSurat
                suratTypes={suratTypes}
                preSelectedKodeSurat={selectedKodeSurat}
                onSubmissionSuccess={handleSubmissionSuccess}
              />
            </div>
          )}

          {/* ========================================================================= */}
          {/* VIEW 3: VERIFIKASI TTE (VALIDATION WORKSPACE)                              */}
          {/* ========================================================================= */}
          {activeMainView === 'verify' && (
            <div key="verify-view" className="motion-view-pane">
              <VerifikasiTTE />
            </div>
          )}
        </main>
      </div>
    </div>
  );
};

export default DashboardPage;
