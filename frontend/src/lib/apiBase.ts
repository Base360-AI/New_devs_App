// API base URL utilities

import { getBackendUrl } from '../utils/getBackendUrl';

export const getApiBase = (): string => {
  return getBackendUrl();
};

export const getApiUrl = (path: string): string => {
  const base = getApiBase();
  return `${base}${path}`;
};