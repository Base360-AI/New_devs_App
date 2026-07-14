// API base URL utilities

export const getApiBase = (): string => {
  if (import.meta.env.VITE_BACKEND_URL) {
    return import.meta.env.VITE_BACKEND_URL;
  }

  if (typeof window !== 'undefined') {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }

  return 'http://localhost:8000';
};

export const getApiUrl = (path: string): string => {
  const base = getApiBase();
  return `${base}${path}`;
};