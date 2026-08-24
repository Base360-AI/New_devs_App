/**
 * Robust Bootstrap Data Fetcher
 *
 * This module provides a bulletproof mechanism for fetching bootstrap data
 * with multiple fallback strategies to ensure the app always loads.
 */

import { supabase } from '../lib/supabase';

export interface BootstrapFetchResult {
  data: any;
  source: 'api' | 'cache' | 'fallback' | 'minimal';
  error?: string;
  responseTime: number;
}

/**
 * Determines the correct backend URL based on environment
 */
function getBackendUrl(): string {
  // Check if we're in development
  if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    return 'http://localhost:8000';
  }

  // For production, use relative URL first (most likely to work)
  // This avoids CORS issues and works with any domain
  return '';
}

/**
 * Creates minimal fallback data to ensure app can render
 */
function createMinimalFallbackData(session: any): any {
  const user = session?.user;
  // Don't assume tenant_id is in app_metadata - let backend resolve it
  return {
    user: {
      id: user?.id || '',
      email: user?.email || 'unknown@example.com',
      role: user?.app_metadata?.role || 'user',
      is_admin: user?.email === 'sid@theflexliving.com' || user?.app_metadata?.role === 'admin'
    },
    tenant: null, // Don't provide default - let backend resolve
    company_settings: null, // Don't provide default - let backend resolve
    permissions: user?.app_metadata?.role === 'admin'
      ? [{ section: '*', action: '*' }]
      : [],
    modules: [],
    smart_views: {},
    subsections: [],
    metadata: {
      tenant_id: null, // Don't assume - let backend resolve
      timestamp: new Date().toISOString(),
      version: '1.0.0'
    },
    cache_info: {
      cache_hit: false,
      cache_level: 'minimal-fallback',
      response_time_ms: 0,
      cache_age_seconds: 0
    }
  };
}

/**
 * Attempts to fetch from a single endpoint with timeout
 */
async function fetchFromEndpoint(
  url: string,
  token: string,
  timeoutMs: number = 5000
): Promise<Response | null> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const timestamp = new Date().toISOString();
    console.log(`[BOOTSTRAP API] ${timestamp} - Attempting to fetch from: ${url}`);
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
        'X-Request-Priority': 'high'
      },
      signal: controller.signal
    });

    clearTimeout(timeoutId);

    if (response.ok) {
      console.log(`[BootstrapFetcher] ✅ Success from: ${url}`);
      return response;
    } else {
      console.warn(`[BootstrapFetcher] ❌ Failed (${response.status}) from: ${url}`);
      return null;
    }
  } catch (error: any) {
    clearTimeout(timeoutId);
    if (error.name === 'AbortError') {
      console.warn(`[BootstrapFetcher] ⏱️ Timeout from: ${url}`);
    } else {
      console.error(`[BootstrapFetcher] ❌ Error from ${url}:`, error.message);
    }
    return null;
  }
}

/**
 * Try multiple backend URLs - prioritize most likely to work
 */
async function tryMultipleEndpoints(token: string): Promise<any | null> {
  const baseUrl = getBackendUrl();

  // Order endpoints by likelihood of success
  // Relative URLs work best in production to avoid CORS
  const endpoints = baseUrl
    ? [
        // Development - try configured URL first
        `${baseUrl}/api/v1/bootstrap`,
        `${baseUrl}/api/v1/auth/bootstrap`
      ]
    : [
        // Production - relative URLs first (no CORS issues)
        '/api/v1/bootstrap',
        '/api/v1/auth/bootstrap',
        // Then try absolute URLs as fallback
        'https://pms.base360.ai/api/v1/bootstrap',
        'https://pms.base360.ai/api/v1/auth/bootstrap'
      ];

  // Try first endpoint with longer timeout
  const firstResponse = await fetchFromEndpoint(endpoints[0], token, 8000);
  if (firstResponse) {
    try {
      const data = await firstResponse.json();
      console.log(`[BootstrapFetcher] Successfully got data from: ${endpoints[0]}`);
      return data;
    } catch (error) {
      console.error(`[BootstrapFetcher] Failed to parse JSON from: ${endpoints[0]}`, error);
    }
  }

  // Try remaining endpoints with shorter timeout
  for (let i = 1; i < endpoints.length; i++) {
    const response = await fetchFromEndpoint(endpoints[i], token, 3000);
    if (response) {
      try {
        const data = await response.json();
        console.log(`[BootstrapFetcher] Successfully got data from: ${endpoints[i]}`);
        return data;
      } catch (error) {
        console.error(`[BootstrapFetcher] Failed to parse JSON from: ${endpoints[i]}`, error);
      }
    }
  }

  return null;
}

/**
 * Load data from cache if available
 */
async function loadFromCache(userId: string): Promise<any | null> {
  try {
    const cacheKey = `app_bootstrap_data_${userId}`;
    const cached = localStorage.getItem(cacheKey);

    if (cached) {
      const parsed = JSON.parse(cached);
      const age = Date.now() - parsed.timestamp;

      // Accept cache up to 30 minutes old (data doesn't change frequently)
      // This ensures instant loading on page refresh
      if (age < 30 * 60 * 1000) {
        console.log(`[BootstrapFetcher] Found valid cache (${Math.round(age / 1000)}s old)`);
        return parsed.data;
      } else {
        console.log(`[BootstrapFetcher] Cache expired (${Math.round(age / 1000)}s old)`);
      }
    }
  } catch (error) {
    console.error('[BootstrapFetcher] Failed to load from cache:', error);
  }

  return null;
}

/**
 * Save data to cache
 */
function saveToCache(userId: string, data: any): void {
  try {
    const cacheKey = `app_bootstrap_data_${userId}`;
    localStorage.setItem(cacheKey, JSON.stringify({
      data,
      timestamp: Date.now()
    }));
    console.log('[BootstrapFetcher] Saved to cache');
  } catch (error) {
    console.error('[BootstrapFetcher] Failed to save to cache:', error);
  }
}

/**
 * Main function to fetch bootstrap data with multiple fallback strategies
 */
export async function fetchBootstrapDataRobust(): Promise<BootstrapFetchResult> {
  const startTime = performance.now();

  try {
    // Step 1: Get session
    console.log('[BootstrapFetcher] Starting robust bootstrap fetch...');
    const { data: { session }, error: sessionError } = await supabase.auth.getSession();

    if (sessionError || !session) {
      console.warn('[BootstrapFetcher] No session available, using minimal fallback');
      return {
        data: createMinimalFallbackData(null),
        source: 'minimal',
        error: 'No active session',
        responseTime: performance.now() - startTime
      };
    }

    // Step 2: Try to load from cache, keyed strictly on this user's id.
    // Without an id there is nothing safe to key on, so we skip the cache
    // entirely rather than falling back to a key every user would share.
    const userId = session.user?.id || null;
    const cachedData = userId ? await loadFromCache(userId) : null;
    if (cachedData) {
      console.log('[BootstrapFetcher] Using cached data for instant load');

      // Fire background refresh without blocking
      setTimeout(() => {
        tryMultipleEndpoints(session.access_token).then(freshData => {
          if (freshData && userId) {
            saveToCache(userId, freshData);
            console.log('[BootstrapFetcher] Background refresh completed');
          }
        }).catch(err => {
          console.error('[BootstrapFetcher] Background refresh failed:', err);
        });
      }, 100);

      return {
        data: cachedData,
        source: 'cache',
        responseTime: performance.now() - startTime
      };
    }

    // Step 3: Try multiple API endpoints
    const apiData = await tryMultipleEndpoints(session.access_token);
    if (apiData) {
      if (userId) {
        saveToCache(userId, apiData);
      }
      return {
        data: apiData,
        source: 'api',
        responseTime: performance.now() - startTime
      };
    }

    // Step 4: Try to construct data from individual endpoints
    console.log('[BootstrapFetcher] Bootstrap endpoint failed, trying individual endpoints...');
    const fallbackData = createMinimalFallbackData(session);

    // Try to get user profile
    try {
      const profileResponse = await fetchFromEndpoint(
        `${getBackendUrl()}/api/v1/profile`,
        session.access_token,
        3000
      );
      if (profileResponse) {
        const profile = await profileResponse.json();
        fallbackData.user = { ...fallbackData.user, ...profile };
        fallbackData.permissions = profile.permissions || [];
      }
    } catch (error) {
      console.error('[BootstrapFetcher] Failed to get profile:', error);
    }

    // Try to get modules
    try {
      const modulesResponse = await fetchFromEndpoint(
        `${getBackendUrl()}/api/v1/modules/enabled`,
        session.access_token,
        3000
      );
      if (modulesResponse) {
        const modules = await modulesResponse.json();
        fallbackData.modules = modules.modules || [];
      }
    } catch (error) {
      console.error('[BootstrapFetcher] Failed to get modules:', error);
    }

    // Save partial data to cache using the same user-scoped key as the read
    if (userId) {
      saveToCache(userId, fallbackData);
    }

    return {
      data: fallbackData,
      source: 'fallback',
      error: 'Bootstrap endpoint unavailable, using fallback data',
      responseTime: performance.now() - startTime
    };

  } catch (error: any) {
    console.error('[BootstrapFetcher] Unexpected error:', error);

    // Last resort: return absolute minimum data
    return {
      data: createMinimalFallbackData(null),
      source: 'minimal',
      error: error.message,
      responseTime: performance.now() - startTime
    };
  }
}

/**
 * Prefetch bootstrap data for faster initial load
 */
export async function prefetchBootstrapData(token?: string): Promise<void> {
  try {
    if (!token) {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) return;
      token = session.access_token;
    }

    // Fire and forget - don't wait for response
    tryMultipleEndpoints(token).then(async data => {
      if (data && token) {
        const { data: { session } } = await supabase.auth.getSession();
        if (session) {
          if (session.user?.id) {
            saveToCache(session.user.id, data);
          }
        }
      }
    });
  } catch (error) {
    console.error('[BootstrapFetcher] Prefetch error:', error);
  }
}
