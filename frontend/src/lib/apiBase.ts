// API base URL utilities

export const getApiBase = (): string => {
  if (typeof window !== 'undefined') {
    const isLocalhost =
      window.location.hostname === 'localhost' ||
      window.location.hostname === '127.0.0.1';

    if (isLocalhost) {
      return (
        import.meta.env.VITE_API_URL ||
        import.meta.env.VITE_BACKEND_URL ||
        'http://localhost:8000'
      );
    }
  }

  return import.meta.env.VITE_API_URL || import.meta.env.VITE_BACKEND_URL || '';
};

export const getApiUrl = (path: string): string => {
  const base = getApiBase();
  return `${base}${path}`;
};
