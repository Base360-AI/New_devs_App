// API base URL utilities

export const getApiBase = (): string => {
  return import.meta.env.VITE_API_URL || import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';
};

export const getApiUrl = (path: string): string => {
  const base = getApiBase();
  return `${base}${path}`;
};