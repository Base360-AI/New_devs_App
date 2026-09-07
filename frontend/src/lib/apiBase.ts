// API base URL utilities

// frontend/src/lib/apiBase.ts
export const getApiBase = (): string => {
  if (typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')) {
    return import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';
  }
  return import.meta.env.VITE_BACKEND_URL || '';
};


export const getApiUrl = (path: string): string => {
  const base = getApiBase();
  return `${base}${path}`;
};