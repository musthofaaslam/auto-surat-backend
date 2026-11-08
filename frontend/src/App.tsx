import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, Link } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import Navbar from './components/Navbar';
import ProtectedRoute from './components/ProtectedRoute';

import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import SuratCreatePage from './pages/SuratCreatePage';
import SuratDetailPage from './pages/SuratDetailPage';
import ApprovalQueuePage from './pages/ApprovalQueuePage';
import VerifySuratPage from './pages/VerifySuratPage';

// Architectural Note:
// Centralized React Router configuration encapsulating declarative route protection,
// role validation, and global authentication provider state.

export const App: React.FC = () => {
  return (
    <AuthProvider>
      <BrowserRouter>
        <div className="min-h-screen bg-slate-50 flex flex-col font-sans">
          <Navbar />

          <main className="flex-1">
            <Routes>
              {/* Public Routes */}
              <Route path="/login" element={<LoginPage />} />
              <Route path="/verify" element={<VerifySuratPage />} />
              <Route path="/verify/:token" element={<VerifySuratPage />} />

              {/* Protected Routes */}
              <Route
                path="/dashboard"
                element={
                  <ProtectedRoute>
                    <DashboardPage />
                  </ProtectedRoute>
                }
              />

              <Route
                path="/surat/new"
                element={
                  <ProtectedRoute>
                    <SuratCreatePage />
                  </ProtectedRoute>
                }
              />

              <Route
                path="/surat/:id"
                element={
                  <ProtectedRoute>
                    <SuratDetailPage />
                  </ProtectedRoute>
                }
              />

              <Route
                path="/approvals"
                element={
                  <ProtectedRoute allowedRoles={['LECTURER', 'STAFF', 'ADMIN']}>
                    <ApprovalQueuePage />
                  </ProtectedRoute>
                }
              />

              {/* Default Redirect */}
              <Route path="/" element={<Navigate to="/dashboard" replace />} />

              {/* 404 Fallback */}
              <Route
                path="*"
                element={
                  <div className="min-h-[70vh] flex flex-col items-center justify-center p-6 text-center">
                    <h1 className="text-3xl font-bold text-slate-900 font-mono">404</h1>
                    <p className="text-xs text-slate-500 mt-2">Halaman tidak ditemukan.</p>
                    <Link
                      to="/dashboard"
                      className="mt-4 px-4 py-2 text-xs font-medium text-slate-700 bg-white border border-slate-300 rounded hover:bg-slate-50 shadow-2xs transition tactile-btn"
                    >
                      Kembali ke Dasbor
                    </Link>
                  </div>
                }
              />
            </Routes>
          </main>

          {/* Clean Academic Footer */}
          <footer className="border-t border-slate-200 bg-white py-4 mt-auto">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between text-[11px] text-slate-400 gap-2">
              <div>
                AutoSurat Agentic AI System &copy; {new Date().getFullYear()} - Layanan Persuratan
                Akademik Resmi.
              </div>
              <div className="flex items-center space-x-4">
                <span>Standar Tata Naskah Dinas Kampus</span>
                <span>Enkripsi TTE SHA-256</span>
              </div>
            </div>
          </footer>
        </div>
      </BrowserRouter>
    </AuthProvider>
  );
};

export default App;
