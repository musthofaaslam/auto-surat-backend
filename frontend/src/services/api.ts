import axios from 'axios';
import type { AxiosError, InternalAxiosRequestConfig } from 'axios';

// Architectural Note:
// Centralized Axios instance with Bearer token injection and global error interceptor.
// In production or cross-origin setups, VITE_API_BASE_URL can point to the backend domain.
// In development, empty string defaults to Vite's reverse-proxy to avoid CORS issues.

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem('access_token');
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response && error.response.status === 401) {
      // Architectural Note:
      // When the token is invalid or expired, automatically clear local credentials
      // and redirect to the login page without crashing application state.
      const currentPath = window.location.pathname;
      if (!currentPath.includes('/login') && !currentPath.includes('/verify')) {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user_info');
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

/**
 * Mengekstrak rincian pesan kesalahan dari respon backend Django / DRF secara cerdas.
 * Memprioritaskan pesan penolakan spesifik pada atribut `errors`, `non_field_errors`,
 * atau validator akademik daripada sekadar label umum seperti "Validasi gagal".
 */
export function extractErrorMessage(
  error: any,
  fallbackMessage: string = 'Terjadi kesalahan saat memproses permintaan.'
): string {
  if (!error) return fallbackMessage;

  const data = error.response?.data;
  if (!data) {
    return error.message || fallbackMessage;
  }

  // 1. Ekstraksi dari data.errors (format standar controller backend)
  if (data.errors) {
    if (typeof data.errors === 'string') {
      return data.errors;
    }
    if (Array.isArray(data.errors)) {
      return data.errors
        .map((item) => (typeof item === 'object' ? JSON.stringify(item) : String(item)))
        .join('\n');
    }
    if (typeof data.errors === 'object') {
      const messages: string[] = [];
      Object.entries(data.errors).forEach(([key, val]) => {
        const valStr = Array.isArray(val)
          ? val.map((v) => (typeof v === 'object' ? JSON.stringify(v) : String(v))).join(', ')
          : String(val);
        if (key === 'non_field_errors' || key === 'detail') {
          messages.push(valStr);
        } else {
          messages.push(`${key}: ${valStr}`);
        }
      });
      if (messages.length > 0) {
        return messages.join('\n');
      }
    }
  }

  // 2. Format standar DRF: { detail: "..." }
  if (data.detail) {
    return typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
  }

  // 3. Format error tunggal: { error: "..." }
  if (data.error) {
    return typeof data.error === 'string' ? data.error : JSON.stringify(data.error);
  }

  // 4. Jika pesan spesifik ada dan bukan sekadar "Validasi gagal"
  if (data.message && data.message !== 'Validasi gagal') {
    return data.message;
  }

  // 5. Format field error langsung tanpa pembungkus errors: { [field]: [...] }
  if (typeof data === 'object') {
    const messages: string[] = [];
    Object.entries(data).forEach(([key, val]) => {
      if (key !== 'status' && key !== 'message') {
        const valStr = Array.isArray(val)
          ? val.map((v) => (typeof v === 'object' ? JSON.stringify(v) : String(v))).join(', ')
          : String(val);
        messages.push(key === 'non_field_errors' ? valStr : `${key}: ${valStr}`);
      }
    });
    if (messages.length > 0) {
      return messages.join('\n');
    }
  }

  // 6. Terakhir, gunakan data.message jika tidak ada detail lain
  if (data.message) {
    return data.message;
  }

  return fallbackMessage;
}

export default api;
