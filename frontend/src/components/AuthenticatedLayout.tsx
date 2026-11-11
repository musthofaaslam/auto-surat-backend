import React, { useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import DashboardSidebar from './DashboardSidebar';
import { Menu, User as UserIcon } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export const AuthenticatedLayout: React.FC = () => {
  // Mobile drawer responsive state: strictly closed by default on entry
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const { user } = useAuth();
  const location = useLocation();

  // DashboardPage manages its own integrated studio container with DashboardSidebar
  if (location.pathname === '/dashboard' || location.pathname === '/buat-surat') {
    return <Outlet />;
  }

  return (
    <div className="flex h-screen bg-slate-100/70 overflow-hidden font-sans">
      {/* Persistent Left Sidebar: Always on the left for desktop, off-canvas drawer on mobile */}
      <DashboardSidebar
        isOpen={isSidebarOpen}
        onClose={() => setIsSidebarOpen(false)}
      />

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
            <span className="font-semibold text-sm tracking-tight text-slate-900">AutoSurat</span>
          </div>

          <div className="flex items-center space-x-2">
            <div className="w-7 h-7 rounded-full bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-700 text-xs font-semibold">
              <UserIcon className="w-3.5 h-3.5" />
            </div>
          </div>
        </header>

        {/* Scrollable Sub-Page Area with Smooth Route Transition Motion */}
        <div key={location.pathname} className="flex-1 overflow-y-auto motion-view-pane">
          <Outlet />
        </div>
      </div>
    </div>
  );
};

export default AuthenticatedLayout;
