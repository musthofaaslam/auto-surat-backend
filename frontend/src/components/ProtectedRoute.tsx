import React from 'react';
import { Navigate, useLocation, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import type { UserRole } from '../types';
import { ShieldAlert, ArrowLeft } from 'lucide-react';

interface ProtectedRouteProps {
  children: React.ReactElement;
  allowedRoles?: UserRole[];
}

// Architectural Note:
// Declarative route-guarding mechanism supporting granular role-based access control (RBAC).
// Prevents unauthenticated access and gracefully displays 403 status for unauthorized roles.

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children, allowedRoles }) => {
  const { user, isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <div className="flex flex-col items-center space-y-3">
          <div className="w-8 h-8 border-2 border-slate-300 border-t-slate-900 rounded-full animate-spin"></div>
          <span className="text-xs font-medium text-slate-500">Memuat sesi pengguna...</span>
        </div>
      </div>
    );
  }

  if (!isAuthenticated || !user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 p-6">
        <div className="max-w-md w-full bg-white border border-slate-200 rounded-lg p-8 shadow-xs text-center tactile-card">
          <div className="inline-flex p-3 bg-rose-50 text-rose-600 rounded-full mb-4 border border-rose-200">
            <ShieldAlert className="w-8 h-8" />
          </div>
          <h2 className="text-lg font-bold text-slate-900">Akses Ditolak (403)</h2>
          <p className="text-xs text-slate-600 mt-2 leading-relaxed">
            Halaman ini membutuhkan hak akses khusus ({allowedRoles.join(', ')}).
            Akun Anda saat ini memiliki peran <span className="font-mono font-semibold text-slate-800">{user.role}</span>.
          </p>
          <div className="mt-6">
            <Link
              to="/dashboard"
              className="inline-flex items-center px-4 py-2 text-xs font-medium text-slate-700 bg-white border border-slate-300 hover:bg-slate-50 rounded shadow-2xs transition tactile-btn"
            >
              <ArrowLeft className="w-3.5 h-3.5 mr-1.5" />
              Kembali ke Dasbor
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return children;
};

export default ProtectedRoute;

