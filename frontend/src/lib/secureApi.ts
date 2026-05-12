/**
 * SECURE MULTI-TENANT API CLIENT
 * 
 * This module provides a centralized, secure API client that ensures ALL database
 * queries go through the backend with proper tenant isolation.
 * 
 * Always use this SecureAPI client instead.
 * 
 * @security This prevents cross-tenant data leakage by enforcing backend-only database access
 */

import { supabase } from './supabase';
import { sessionManager } from '../utils/sessionManager';
import { withRetry, handleApiError, classifyError } from '../utils/apiErrorHandler';

// Get backend URL with fallback for misconfigured production environments
const getBackendUrl = () => {
  // For production/staging (non-localhost), use relative URLs to avoid CORS
  if (typeof window !== 'undefined' &&
    window.location.hostname !== 'localhost' &&
    window.location.hostname !== '127.0.0.1') {
    console.log(`[SecureAPI] Using relative URLs for ${window.location.hostname}`);
    return ''; // Empty string means relative URLs - the browser will use the same domain
  }

  // For local development, check for configured URL
  const configuredUrl = import.meta.env.VITE_BACKEND_URL;
  if (configuredUrl && !configuredUrl.includes('localhost')) {
    // If it's not localhost but we're in development, it might be a remote backend
    return configuredUrl;
  }

  // Default to localhost for development
  return configuredUrl || 'http://localhost:8000';
};

const BACKEND_URL = getBackendUrl();

export class TenantIsolationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'TenantIsolationError';
  }
}

export class SecureAPIClient {
  private static instance: SecureAPIClient;
  private backendUrl: string;
  private requestCount = 0;
  private securityViolations: string[] = [];
  private cachedToken: string | null = null;
  private cachedTenantId: string | null = null;

  // Request deduplication
  private pendingRequests = new Map<string, Promise<any>>();
  private requestCache = new Map<string, { data: any; timestamp: number }>();
  private CACHE_TTL = 5000; // 5 seconds cache for GET requests

  private constructor() {
    this.backendUrl = BACKEND_URL;
    this.interceptDirectQueries();
  }

  static getInstance(): SecureAPIClient {
    if (!SecureAPIClient.instance) {
      SecureAPIClient.instance = new SecureAPIClient();
    }
    return SecureAPIClient.instance;
  }

  /**
   * Intercepts and blocks direct Supabase queries in development
   */
  private interceptDirectQueries() {
    if (import.meta.env.DEV) {
      const ENFORCE = (import.meta.env as any).VITE_ENFORCE_SECURE_API === 'true';
      const originalFrom = supabase.from;
      // Temporary dev allowlist for legacy direct queries while migrating to SecureAPI
      const DEV_ALLOWLIST = new Set([
        'user_permissions',
        'users_city',
        'user_preferences',
        'access_logs',
        'landlord_details'
      ]);

      supabase.from = (table: string) => {
        const stack = new Error().stack || '';
        const violation = `SECURITY VIOLATION: Direct Supabase query to table '${table}'`;

        if (DEV_ALLOWLIST.has(table) || !ENFORCE) {
          // Allow in development with a clear warning when not enforcing strict mode
          console.warn(`⚠️ Legacy direct query allowed in DEV${ENFORCE ? ' (allowlist)' : ''}:`, table);
          if (!DEV_ALLOWLIST.has(table) && !ENFORCE) {
            // Record violation for later review, but don't block
            this.securityViolations.push(violation + ' (allowed in DEV)');
          }
          return originalFrom.call(supabase, table);
        }

        // Strict enforcement in DEV when VITE_ENFORCE_SECURE_API=true
        console.error('🚨🚨🚨 ' + violation);
        console.error('Stack trace:', stack);
        this.securityViolations.push(violation);
        throw new TenantIsolationError(
          `Direct database access is forbidden! Use SecureAPI.${table}() instead. ` +
          `This query would expose data from ALL tenants.`
        );
      };
    }
  }

  /**
   * Gets authentication headers for backend requests
   */
  private async getAuthHeaders(): Promise<HeadersInit> {
    // Try cached token first for performance
    let token = this.cachedToken;

    // If no cached token, get a validated session
    if (!token) {
      console.log('[SecureAPI] No cached token, waiting for session or validating...');
      // First, wait briefly for a session to appear to avoid racing login
      const waited = await this.waitForSession(5000);
      const session = waited || await sessionManager.ensureValidSession();

      if (!session || !session.access_token) {
        throw new TenantIsolationError('No valid authentication token available');
      }

      token = session.access_token;
      // Update cached token for next request
      this.cachedToken = token;
    }

    return {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
      'X-Request-ID': `req_${Date.now()}_${++this.requestCount}`,
      'X-Client-Version': '2.0.0-secure'
    };
  }

  /**
   * Allows the app (AuthProvider) to proactively provide an access token
   * to avoid timing issues when the session is still initializing.
   */
  public setAccessToken(token: string | null) {
    // Clear cached tenant ID when token changes to prevent cross-tenant contamination
    if (this.cachedToken !== token) {
      const previousTenant = this.cachedTenantId;
      this.cachedTenantId = null;
      // Clear cache when switching tenants
      this.clearCache();

      // Log tenant changes for security monitoring
      if (previousTenant && token) {
        console.log('[SecureAPI SECURITY] Tenant context changed - cache cleared', {
          previousTenant: previousTenant,
          timestamp: new Date().toISOString()
        });
      }
    }
    this.cachedToken = token || null;
  }

  /**
   * Get tenant ID for cache isolation
   */
  private async getTenantId(): Promise<string | null> {
    // Try cached tenant ID first for performance
    if (this.cachedTenantId) {
      return this.cachedTenantId;
    }

    try {
      // Extract tenant ID from JWT token if available
      const token = this.cachedToken;
      if (token) {
        let extractedTenantId = null;

        // Handle static local token.
        if (token === "mock-token-123") {
          extractedTenantId = "tenant-a";
        }
        // Check if it's a valid JWT
        else if (token.includes('.') && token.split('.').length === 3) {
          const payload = JSON.parse(atob(token.split('.')[1]));
          extractedTenantId = payload.user_metadata?.tenant_id || payload.tenant_id;
        }

        if (extractedTenantId) {
          // Validate tenant ID format (should be UUID)
          if (this.isValidTenantId(extractedTenantId)) {
            this.cachedTenantId = extractedTenantId;
            return this.cachedTenantId;
          } else {
            console.error('[SecureAPI] Invalid tenant ID format:', extractedTenantId);
            // Clear invalid session to force re-authentication
            this.cachedToken = null;
            this.cachedTenantId = null;
          }
        }
      }
    } catch (error) {
      console.error('[SecureAPI] JWT parsing failed - clearing session:', error);
      // Clear potentially corrupted session data
      this.cachedToken = null;
      this.cachedTenantId = null;
      this.clearCache();
    }

    // Return null instead of dangerous 'default' fallback
    // This will disable caching for users without valid tenant IDs
    return null;
  }

  /**
   * This prevents conflicts between different user sessions making identical requests
   */
  private async getUserSessionKey(): Promise<string | null> {
    try {
      const token = this.cachedToken;
      if (token) {
        const payload = JSON.parse(atob(token.split('.')[1]));
        // Use user sub (unique ID) + email as session key for isolation
        const userSub = payload.sub;
        const userEmail = payload.email;

        if (userSub && userEmail) {
          // Create short hash to avoid very long cache keys
          const sessionKey = `${userSub.substring(0, 8)}-${userEmail.split('@')[0]}`;
          return sessionKey;
        }
      }
    } catch (error) {
      console.error('[SecureAPI] Failed to extract user session key:', error);
    }
    return null;
  }

  /**
   * Validate tenant ID format for security
   */
  private isValidTenantId(tenantId: string): boolean {
    // Check for UUID format (basic validation)
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    return typeof tenantId === 'string' && tenantId.length > 0 && uuidRegex.test(tenantId);
  }

  /**
   * Clear request cache (useful when tenant changes)
   */
  public clearCache(): void {
    this.requestCache.clear();
    this.pendingRequests.clear();
    console.log('[SecureAPI] Cache cleared due to tenant/token change');
  }

  /**
   * Clear cache for specific endpoint patterns (e.g., cleaning endpoints)
   */
  public clearEndpointCache(endpointPattern: string): number {
    let cleared = 0;
    const keysToDelete: string[] = [];

    for (const [key, value] of this.requestCache.entries()) {
      if (key.includes(endpointPattern)) {
        keysToDelete.push(key);
        cleared++;
      }
    }

    keysToDelete.forEach(key => {
      this.requestCache.delete(key);
    });

    // Also clear pending requests
    const pendingKeysToDelete: string[] = [];
    for (const [key, promise] of this.pendingRequests.entries()) {
      if (key.includes(endpointPattern)) {
        pendingKeysToDelete.push(key);
      }
    }

    pendingKeysToDelete.forEach(key => {
      this.pendingRequests.delete(key);
    });

    if (cleared > 0) {
      console.log(`[SecureAPI] Cleared ${cleared} cache entries for pattern: ${endpointPattern}`);
    }

    return cleared;
  }

  /**
   * Get cache diagnostics for debugging
   */
  public getCacheDiagnostics(): {
    totalCacheEntries: number;
    totalPendingRequests: number;
    cleaningCacheEntries: number;
    oldestCacheAge: number;
    newestCacheAge: number;
    suspiciousEntries: Array<{ key: string; age: number; data: any }>;
  } {
    const now = Date.now();
    let cleaningEntries = 0;
    let oldestAge = 0;
    let newestAge = Infinity;
    const suspiciousEntries: Array<{ key: string; age: number; data: any }> = [];

    for (const [key, value] of this.requestCache.entries()) {
      const age = now - value.timestamp;

      if (age > oldestAge) oldestAge = age;
      if (age < newestAge) newestAge = age;

      if (key.includes('secure/cleaning/reports')) {
        cleaningEntries++;

        // Check for suspicious cleaning cache entries
        const items = value.data?.items || value.data?.data || [];
        const total = value.data?.total || 0;

        if (total === 0 && key.includes('overdue')) {
          suspiciousEntries.push({ key, age, data: { total, itemsCount: items.length } });
        }
      }
    }

    return {
      totalCacheEntries: this.requestCache.size,
      totalPendingRequests: this.pendingRequests.size,
      cleaningCacheEntries: cleaningEntries,
      oldestCacheAge: oldestAge,
      newestCacheAge: newestAge === Infinity ? 0 : newestAge,
      suspiciousEntries
    };
  }

  /**
   */
  public emergencySecurityClear(): void {
    console.warn('[SecureAPI EMERGENCY] Security clear - all cache and session data cleared');
    this.cachedToken = null;
    this.cachedTenantId = null;
    this.requestCache.clear();
    this.pendingRequests.clear();
    this.securityViolations = [];
  }

  /**
   * Generate cache key that includes query parameters to prevent cache collisions
   * between different API calls to the same endpoint with different parameters
   */
  private async generateCacheKey(method: string, endpoint: string, tenantId: string): Promise<string> {
    // This ensures different users don't share cached/pending requests
    const userSessionKey = await this.getUserSessionKey();
    const sessionPart = userSessionKey ? `:${userSessionKey}` : '';

    // For endpoints with query parameters, include them in the cache key
    // to prevent cache collisions (e.g., different cleaning tabs)

    let cacheKey: string;

    if (endpoint.includes('?')) {
      // Parse the endpoint to extract base path and query parameters
      const [basePath, queryString] = endpoint.split('?');

      // Sort query parameters for consistent cache keys
      const params = new URLSearchParams(queryString);
      const sortedParams = Array.from(params.entries())
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([key, value]) => `${key}=${encodeURIComponent(value)}`)
        .join('&');

      // Include sorted parameters, tenant ID, and user session in cache key
      cacheKey = `${method}:${basePath}?${sortedParams}:${tenantId}${sessionPart}`;
    } else {
      // No query parameters, use original format with session isolation
      cacheKey = `${method}:${endpoint}:${tenantId}${sessionPart}`;
    }

    // Debug logging for cache key generation
    if (endpoint.includes('secure/cleaning/reports') || endpoint.includes('properties')) {
      console.log('[SecureAPI] Generated cache key:', {
        endpoint,
        cacheKey: cacheKey.length > 100 ? cacheKey.substring(0, 100) + '...' : cacheKey,
        hasQueryParams: endpoint.includes('?')
      });
    }

    return cacheKey;
  }

  /**
   * Validates if a result should be cached for cleaning endpoints
   * Prevents caching of empty/suspicious results that could be due to race conditions
   */
  private shouldCacheCleaningResult(endpoint: string, data: any): boolean {
    // Only apply validation to cleaning endpoints (both secure and legacy)
    if (!endpoint.includes('/cleaning/reports')) {
      return true; // Cache all other endpoints normally
    }

    // Check if result looks valid for cleaning data
    const items = data?.items || data?.data || [];
    const total = data?.total || 0;

    // Always cache properly structured responses, even if empty
    // Empty results can be legitimate for users without tenant access or specific date ranges
    if (data && typeof data === 'object' && (data.hasOwnProperty('items') || data.hasOwnProperty('data') || data.hasOwnProperty('total'))) {
      return true; // Cache all properly structured responses
    }

    // Only skip caching for malformed responses
    if (data === null || data === undefined) {
      console.warn('[SecureAPI] Not caching null/undefined cleaning result');
      return false;
    }

    return true;
  }

  /**
   * Validates if a cached result is still valid and hasn't become stale
   * Helps detect and clear corrupted cache entries
   */
  private isCacheResultValid(endpoint: string, cachedData: any, cacheAge: number): boolean {
    // For non-cleaning endpoints, use normal cache validation
    if (!endpoint.includes('/cleaning/reports')) {
      return cacheAge < this.CACHE_TTL;
    }

    // during rapid tab switching. The 3-second invalidation was causing cache thrashing.
    const CLEANING_CACHE_TTL = 30000; // 30 seconds instead of 3 seconds

    // For cleaning endpoints, use extended cache time but validate content
    const items = cachedData?.items || cachedData?.data || [];
    const total = cachedData?.total || 0;

    // Primary validation: check cache age with more reasonable timeout
    if (cacheAge > CLEANING_CACHE_TTL) {
      return false;
    }

    // Empty overdue results can be valid (no overdue cleanings), so don't invalidate them
    // unless they're really old or clearly corrupted

    // Only invalidate if data structure is clearly malformed
    if (cachedData === null || cachedData === undefined) {
      return false;
    }

    // Validate that we have expected data structure
    if (typeof cachedData !== 'object' || (!('items' in cachedData) && !('data' in cachedData))) {
      console.warn('[SecureAPI] Invalidating malformed cached cleaning result');
      return false;
    }

    return true; // Cache is valid
  }

  /**
   * Wait for a valid Supabase session (with timeout) so API calls don't race login.
   */
  private async waitForSession(timeoutMs: number = 7000): Promise<import('@supabase/supabase-js').Session | null> {
    // Helper to read token from Supabase storage as last resort
    const getTokenFromStorage = (): string | null => {
      try {
        if (typeof localStorage === 'undefined') return null;
        for (let i = 0; i < localStorage.length; i++) {
          const key = localStorage.key(i) || '';
          if (key.startsWith('sb-') && key.endsWith('-auth-token')) {
            const raw = localStorage.getItem(key);
            if (!raw) continue;
            const parsed = JSON.parse(raw);
            const token = parsed?.access_token || parsed?.currentSession?.access_token;
            if (token) return token;
          }
        }
      } catch { }
      return null;
    };

    const nowHasToken = async () => {
      const current = await supabase.auth.getSession();
      return current.data.session?.access_token || getTokenFromStorage();
    };

    // Fast path
    const initial = await supabase.auth.getSession();
    if (initial.data.session?.access_token) return initial.data.session;
    const storageToken = getTokenFromStorage();
    if (storageToken) {
      // Construct a minimal session object shape with access_token
      return { access_token: storageToken } as any;
    }

    // Listen + poll concurrently
    let unsubscribe: (() => void) | null = null;
    let resolved = false;
    const sessionPromise = new Promise<import('@supabase/supabase-js').Session | null>((resolve) => {
      const { data } = supabase.auth.onAuthStateChange((_event, session) => {
        if (!resolved && session?.access_token) {
          resolved = true;
          if (unsubscribe) unsubscribe();
          resolve(session);
        }
      });
      unsubscribe = () => data.subscription.unsubscribe();
    });

    const pollingPromise = new Promise<import('@supabase/supabase-js').Session | null>(async (resolve) => {
      const start = Date.now();
      while (Date.now() - start < timeoutMs) {
        const token = await nowHasToken();
        if (token) {
          resolved = true;
          if (unsubscribe) unsubscribe();
          resolve({ access_token: token } as any);
          return;
        }
        await new Promise(r => setTimeout(r, 200));
      }
      resolve(null);
    });

    const timeoutPromise = new Promise<null>((resolve) => setTimeout(() => resolve(null), timeoutMs));
    const result = await Promise.race([sessionPromise, pollingPromise, timeoutPromise]);
    if (unsubscribe) unsubscribe();
    return result;
  }

  /**
   * Makes a secure request to the backend with deduplication
   */
  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const method = options.method || 'GET';
    const isGetRequest = method === 'GET';

    // Log ALL API requests to track order
    const timestamp = new Date().toISOString();
    console.log(`[API REQUEST] ${timestamp} - ${method} ${endpoint}`);

    // Create a tenant-isolated unique key for this request
    const tenantId = await this.getTenantId();

    if (!tenantId) {
      console.warn(`[API SECURITY] No valid tenant ID - bypassing cache for ${endpoint}`);
      return this.executeRequest<T>(endpoint, options, null, false);
    }

    // Generate cache key that includes query parameters to prevent cache collisions
    // between different filters (e.g., different cleaning tabs)
    const requestKey = await this.generateCacheKey(method, endpoint, tenantId);

    // For GET requests, check cache first (only with valid tenant)
    if (isGetRequest) {
      const cached = this.requestCache.get(requestKey);
      if (cached) {
        const cacheAge = Date.now() - cached.timestamp;
        if (this.isCacheResultValid(endpoint, cached.data, cacheAge)) {
          console.log(`[API CACHE HIT] ${endpoint} (tenant: ${tenantId}) age: ${cacheAge}ms`);
          return cached.data;
        } else {
          // Remove invalid cache entry
          console.log(`[API CACHE INVALID] ${endpoint} - removing stale/suspicious entry`);
          this.requestCache.delete(requestKey);
        }
      }

      // Check if request is already pending
      const pending = this.pendingRequests.get(requestKey);
      if (pending) {
        console.log(`[API DEDUP] ${endpoint} - waiting for pending request (tenant: ${tenantId})`);
        try {
          const result = await Promise.race([
            pending,
            new Promise((_, reject) => {
              setTimeout(() => reject(new Error('Pending request timeout')), 10000); // 10 second timeout
            })
          ]);

          // Empty overdue results are valid and should be returned from deduplication
          console.log(`[API DEDUP SUCCESS] ${endpoint} - returned cached result`);
          return result;
        } catch (error) {
          console.warn('[SecureAPI] Pending request failed or timed out, making fresh request:', error);
          this.pendingRequests.delete(requestKey);
          // Continue to make fresh request
        }
      }
    }

    // Create the request promise
    const requestPromise = this.executeRequest<T>(endpoint, options, requestKey, isGetRequest);

    // Store pending request for deduplication (only with valid cache key)
    if (isGetRequest && requestKey) {
      this.pendingRequests.set(requestKey, requestPromise);
    }

    return requestPromise;
  }

  /**
   * Executes the actual request with retry logic
   */
  private async executeRequest<T>(
    endpoint: string,
    options: RequestInit,
    requestKey: string | null,
    isGetRequest: boolean
  ): Promise<T> {
    const MAX_RETRIES = 3; // Increased for better resilience
    const RETRY_DELAY_BASE = 1000; // Reasonable delay for retries
    let lastError: Error | null = null;

    for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
      try {
        const headers = await this.getAuthHeaders();
        const url = `${this.backendUrl}${endpoint}`;


        // Only show attempt number if this is a retry
        if (attempt === 1) {
          console.log(`🔒 Secure API Request: ${options.method || 'GET'} ${endpoint}`);
        } else {
          console.log(`🔒 Secure API Request: ${options.method || 'GET'} ${endpoint} (retry ${attempt - 1}/${MAX_RETRIES - 1})`);
        }

        const response = await fetch(url, {
          ...options,
          headers: {
            ...headers,
            ...options.headers
          }
        });

        if (!response.ok) {
          let bodyText = '';
          try { bodyText = await response.text(); } catch { }
          let detail = '';
          let errorData = null;

          try {
            errorData = JSON.parse(bodyText);
            detail = errorData?.detail || errorData?.message || '';
            console.error('🔴 API Error Details:', {
              status: response.status,
              statusText: response.statusText,
              errorData,
              bodyText,
              url: response.url
            });
          } catch (parseError) {
            console.error('🔴 Could not parse error response:', bodyText);
          }

          // Don't retry on 403 (forbidden) - it won't help
          if (response.status === 403) {
            throw new TenantIsolationError(
              detail || 'Access denied: You can only access data from your organization'
            );
          }

          // If we get 401, try to refresh the session before retrying
          if (response.status === 401) {
            console.log('[SecureAPI] Got 401, attempting to refresh session...');

            // Import sessionValidator dynamically to avoid circular dependency
            const { sessionValidator } = await import('../utils/sessionValidator');

            // Clear cached token
            this.cachedToken = null;

            // Try to validate/refresh the session
            const refreshedSession = await sessionValidator.validateSession();

            if (refreshedSession?.access_token) {
              console.log('[SecureAPI] Session refreshed, will retry with new token');
              this.cachedToken = refreshedSession.access_token;

              // Only retry if we haven't exceeded max attempts
              if (attempt < MAX_RETRIES) {
                throw new Error('Authentication refreshed, will retry with new token');
              }
            }

            // If we can't refresh or no more retries, fail with 401
            throw new Error('Authentication failed - please login again');
          }

          const msg = detail || bodyText || `${response.status} ${response.statusText}`;
          throw new Error(`API request failed: ${msg}`);
        }

        // Handle response parsing based on content type and status
        let data;
        const contentType = response.headers.get('content-type');

        // Check if response has content to parse
        if (response.status === 204 || response.status === 205) {
          // No Content responses - return null or empty object
          data = null;
        } else if (contentType && contentType.includes('application/json')) {
          // Only parse JSON if content-type indicates JSON
          const text = await response.text();
          if (text.trim()) {
            data = JSON.parse(text);
          } else {
            data = null; // Empty response body
          }
        } else {
          // For non-JSON responses, return the text or null
          const text = await response.text();
          data = text || null;
        }

        // Cache successful GET requests (with validation for cleaning endpoints)
        if (isGetRequest && data !== null && requestKey) {
          // Apply caching validation for cleaning endpoints to prevent race conditions
          const shouldCache = this.shouldCacheCleaningResult(endpoint, data);

          if (shouldCache) {
            this.requestCache.set(requestKey, {
              data,
              timestamp: Date.now()
            });
            console.log(`[API CACHE STORE] ${endpoint} (tenant: ${requestKey.split(':')[2]})`);
          } else {
            console.log(`[API CACHE SKIP] ${endpoint} - result validation failed`);
          }
        }

        // Success - clear any pending request tracking and return
        if (isGetRequest && requestKey) {
          this.pendingRequests.delete(requestKey);
        }

        return data;
      } catch (error) {
        lastError = error as Error;

        if (isGetRequest && requestKey) {
          this.pendingRequests.delete(requestKey);
        }

        // Don't retry on specific errors
        if (error instanceof TenantIsolationError) {
          throw error;
        }

        console.error(`[SecureAPI] Attempt ${attempt}/${MAX_RETRIES} failed:`, error);

        // If this isn't the last attempt, retry with exponential backoff
        if (attempt < MAX_RETRIES) {
          const delay = RETRY_DELAY_BASE * Math.pow(2, attempt - 1) + Math.random() * 500;
          console.log(`[SecureAPI] Retrying in ${Math.round(delay)}ms...`);
          await new Promise(resolve => setTimeout(resolve, delay));
        }
      }
    }

    // All retries failed - clean up and throw the last error
    if (isGetRequest && requestKey) {
      this.pendingRequests.delete(requestKey);
      // Also clear any potentially corrupted cache entry
      this.requestCache.delete(requestKey);
      console.log(`[API CACHE CLEAR] ${endpoint} - cleared due to failed request`);
    }

    console.error('[SecureAPI] All retry attempts failed');
    throw lastError || new Error('Request failed after all retries');
  }

  /**
   * Makes a public request to the backend without auth headers (for health checks, etc.)
   */
  private async requestPublic<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.backendUrl}${endpoint}`;
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'X-Request-ID': `req_${Date.now()}_${++this.requestCount}`,
        'X-Client-Version': '2.0.0-secure',
        ...(options.headers || {})
      }
    });
    if (!response.ok) {
      throw new Error(`API request failed: ${response.status} ${response.statusText}`);
    }
    return response.json();
  }

  // ============= RESERVATIONS API =============

  /**
   * Get all reservations (with tenant filtering)
   */
  async getAllReservations() {
    // Use new secure endpoint
    return this.request<any>('/api/v1/reservations/all');
  }

  /**
   * Get reservations with filters
   */
  async getReservations(filters?: {
    property_id?: string;
    status?: string;
    date_from?: string;
    date_to?: string;
    search?: string;
    limit?: number;
    offset?: number;
  }) {
    // Use a single, robust endpoint to avoid route collisions: cached reservations
    // Then filter client-side using reservations table semantics (guest_name, reservation_id, property_id)
    const cached = await this.getCachedReservations();
    const list: any[] = Array.isArray((cached as any)?.data)
      ? (cached as any).data
      : (Array.isArray(cached) ? cached : (cached?.items || []));
    const q = (filters?.search || '').toString().toLowerCase();
    const pid = filters?.property_id || '';
    const st = (filters?.status || '').toString().toLowerCase();
    const df = filters?.date_from ? new Date(filters.date_from) : null;
    const dt = filters?.date_to ? new Date(filters.date_to) : null;

    const filtered = list.filter((r: any) => {
      if (!r) return false;
      // property filter (UUID equality)
      if (pid && String(r.property_id) !== String(pid)) return false;
      // status filter
      if (st && String(r.status || '').toLowerCase() !== st) return false;
      // date filters
      if (df) {
        const ci = r.checkin_date ? new Date(r.checkin_date) : null;
        if (!ci || ci < df) return false;
      }
      if (dt) {
        const co = r.checkout_date ? new Date(r.checkout_date) : null;
        if (!co || co > dt) return false;
      }
      // search term in guest_name, guest_email, reservation_id
      if (q) {
        const gn = String(r.guest_name || '').toLowerCase();
        const ge = String(r.guest_email || '').toLowerCase();
        const rid = String(r.reservation_id || r.id || '').toLowerCase();
        if (!(gn.includes(q) || ge.includes(q) || rid.includes(q))) return false;
      }
      return true;
    });
    const limit = filters?.limit ?? 50;
    const offset = filters?.offset ?? 0;
    const sliced = filtered.slice(offset, offset + limit);
    return { data: sliced, total: filtered.length, limit, offset };
  }

  /**
   * Get reservation suggestions (single endpoint, reservations table semantics)
   */
  async getReservationSuggestions(search: string, limit: number = 10, opts?: { status?: string }) {
    const body = {
      search,
      limit: Math.max(1, Math.min(limit, 1000)),
      ...(opts?.status ? { status: opts.status } : {})
    };
    return this.request<any>(`/api/v1/reservations-suggest`, {
      method: 'POST',
      body: JSON.stringify(body)
    });
  }

  /**
   * Get a single reservation by ID
   */
  async getReservation(id: string) {
    return this.request<any>(`/api/v1/reservations/${id}`);
  }

  /**
   * Get cached reservations (faster)
   */
  async getCachedReservations(forceRefresh: boolean = false) {
    const endpoint = forceRefresh
      ? '/api/v1/reservations/all?force_refresh=true'
      : '/api/v1/reservations/all';
    return this.request<any>(endpoint);
  }

  /**
   * Get reservations progressively (paginated)
   * Fetches reservations in batches for progressive display
   */
  async getReservationsProgressive(offset: number, limit: number) {
    const params = new URLSearchParams();
    params.set('offset', offset.toString());
    params.set('limit', limit.toString());

    return this.request<{
      data: any[];
      total: number;
      offset: number;
      limit: number;
      has_more: boolean;
      cached: boolean;
      duration_ms: number;
      progressive: boolean;
    }>(`/api/v1/reservations/all?${params.toString()}`);
  }

  /**
   * Get filter options for reservations
   */
  async getReservationFilterOptions() {
    return this.request<{
      cities: string[];
      properties: any[];
      statuses: string[];
      channels: string[];
    }>('/api/v1/filter-options');
  }

  /**
   * Invalidate cached reservations for current tenant (optional property scope)
   */
  async invalidateReservationCache(propertyId?: string) {
    const params = new URLSearchParams();
    if (propertyId) {
      params.set('property_id', propertyId);
    }
    const query = params.toString() ? `?${params.toString()}` : '';
    return this.request<any>(`/api/v1/cache/invalidate${query}`, {
      method: 'POST'
    });
  }

  /**
   * Get distinct values for a reservation field
   */
  async getReservationDistinctValues(field: string) {
    return this.request<{
      field: string;
      values: string[];
    }>(`/api/v1/reservations/distinct-values/${field}`);
  }

  /**
   * Update a reservation
   */
  async updateReservation(id: string, updates: any) {
    return this.request<any>(`/api/v1/reservations/${id}`, {
      method: 'PUT',
      body: JSON.stringify(updates)
    });
  }

  /**
   * Create a new reservation
   */
  async createReservation(reservation: any) {
    return this.request<any>('/api/v1/reservations', {
      method: 'POST',
      body: JSON.stringify(reservation)
    });
  }

  /**
   * Delete a reservation
   */
  async deleteReservation(id: string) {
    return this.request<any>(`/api/v1/reservations/${id}`, {
      method: 'DELETE'
    });
  }

  /**
   * Bulk update reservations
   */
  async bulkUpdateReservations(ids: string[], updates: any) {
    return this.request<any>('/api/v1/reservations/bulk-update', {
      method: 'POST',
      body: JSON.stringify({ ids, updates })
    });
  }

  // ============= USERS API =============

  async createUser(payload: {
    email: string;
    password: string;
    name: string;
    phone?: string;
    department?: string;
    group?: string;
    isAdmin?: boolean;
    permissions?: Array<{ section: string; action: string }>;
    cities?: string[];
  }) {
    return this.request<any>('/api/v1/users', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  }

  async updateUser(userId: string, payload: {
    user_metadata?: Record<string, any>;
    app_metadata?: Record<string, any>;
    email?: string;
    phone?: string;
    password?: string;
  }) {
    return this.request<any>(`/api/v1/users/${userId}`, {
      method: 'PUT',
      body: JSON.stringify(payload)
    });
  }

  // ============= PROPERTIES API =============

  /**
   * Get properties with filters
   * Using the standard /properties/ endpoint which queries the properties table
   */
  async getProperties(filters?: {
    city?: string;
    portfolio?: string;
    status?: string;
    search?: string;
    page?: number;
    page_size?: number;
  }) {
    console.log('[SecureAPI.getProperties] Called with filters:', filters);
    const params = new URLSearchParams();
    if (filters) {
      Object.entries(filters).forEach(([key, value]) => {
        if (value !== undefined) params.append(key, String(value));
      });
    }
    // Default page_size to 1000 to get all properties
    if (!params.has('page_size')) {
      params.append('page_size', '1000');
    }

    // Use the standard properties endpoint that uses the properties table
    const endpoint = `/api/v1/properties?${params}`;
    console.log('[SecureAPI.getProperties] Requesting endpoint:', endpoint);

    try {
      const result = await this.request<any>(endpoint);
      console.log('[SecureAPI.getProperties] Request successful');
      console.log('[SecureAPI.getProperties] Result type:', typeof result);

      // The endpoint returns paginated results in format {items: [...], total: n}
      if (result && typeof result === 'object') {
        console.log('[SecureAPI.getProperties] Result keys:', Object.keys(result));

        // Return the result in a consistent format that components expect
        // SimpleReservationForm expects {data: [...]}
        if ('items' in result) {
          console.log('[SecureAPI.getProperties] Found items array with', result.items?.length || 0, 'properties');
          return { data: result.items || [], total: result.total || 0 };
        } else if ('data' in result) {
          console.log('[SecureAPI.getProperties] Found data array with', result.data?.length || 0, 'properties');
          return result; // Already in correct format
        } else if (Array.isArray(result)) {
          console.log('[SecureAPI.getProperties] Result is array with', result.length, 'properties');
          return { data: result, total: result.length };
        } else {
          console.warn('[SecureAPI.getProperties] Unexpected result format, returning empty data');
          return { data: [], total: 0 };
        }
      }

      console.log('[SecureAPI.getProperties] Returning empty data for null/undefined result');
      return { data: [], total: 0 };
    } catch (error) {
      console.error('[SecureAPI.getProperties] Request failed:', error);
      throw error;
    }
  }

  /**
   * Get a single property by ID
   */
  async getProperty(id: string) {
    return this.request<any>(`/api/v1/properties/${id}`);
  }

  /**
   * Update a property
   */
  async updateProperty(id: string, updates: any) {
    return this.request<any>(`/api/v1/properties/${id}`, {
      method: 'PUT',
      body: JSON.stringify(updates)
    });
  }

  /**
   * Get property notes with tenant isolation
   */
  async getPropertyNotes(propertyId: string) {
    return this.request<any>(`/api/v1/properties/${propertyId}/notes`);
  }

  /**
   * Create a new property note
   */
  async createPropertyNote(propertyId: string, note: string) {
    return this.request<any>(`/api/v1/properties/${propertyId}/notes`, {
      method: 'POST',
      body: JSON.stringify({ note })
    });
  }

  /**
   * Delete a property note
   */
  async deletePropertyNote(noteId: string) {
    return this.request<any>(`/api/v1/properties/notes/${noteId}`, {
      method: 'DELETE'
    });
  }

  /**
   * Get appliances for a property
   */
  async getPropertyAppliances(propertyId: string) {
    return this.request<any>(`/api/v1/properties/${propertyId}/appliances`);
  }

  /**
   * Create a new appliance for a property
   */
  async createPropertyAppliance(propertyId: string, applianceData: any) {
    return this.request<any>(`/api/v1/properties/${propertyId}/appliances`, {
      method: 'POST',
      body: JSON.stringify(applianceData)
    });
  }

  // Alias for compatibility
  async createAppliance(propertyId: string, applianceData: any) {
    return this.createPropertyAppliance(propertyId, applianceData);
  }

  /**
   * Update an appliance
   */
  async updatePropertyAppliance(propertyId: string, applianceId: string, updates: any) {
    return this.request<any>(`/api/v1/properties/${propertyId}/appliances/${applianceId}`, {
      method: 'PUT',
      body: JSON.stringify(updates)
    });
  }

  // Alias for compatibility
  async updateAppliance(propertyId: string, applianceId: string, updates: any) {
    return this.updatePropertyAppliance(propertyId, applianceId, updates);
  }

  /**
   * Delete an appliance
   */
  async deletePropertyAppliance(propertyId: string, applianceId: string) {
    return this.request<any>(`/api/v1/properties/${propertyId}/appliances/${applianceId}`, {
      method: 'DELETE',
      body: JSON.stringify({ property_id: propertyId })
    });
  }

  // Alias for compatibility  
  async deleteAppliance(propertyId: string, applianceId: string) {
    return this.deletePropertyAppliance(propertyId, applianceId);
  }

  /**
   * Get contracts for a property
   */
  async getPropertyContracts(propertyId: string) {
    return this.request<any>(`/api/v1/properties/${propertyId}/contracts`);
  }

  /**
   * Create a new contract for a property
   */
  async createPropertyContract(propertyId: string, contractData: any) {
    return this.request<any>(`/api/v1/properties/${propertyId}/contracts`, {
      method: 'POST',
      body: JSON.stringify(contractData)
    });
  }

  /**
   * Update a contract
   */
  async updatePropertyContract(propertyId: string, contractId: string, updates: any) {
    return this.request<any>(`/api/v1/properties/${propertyId}/contracts/${contractId}`, {
      method: 'PUT',
      body: JSON.stringify(updates)
    });
  }

  /**
   * Delete a contract
   */
  async deletePropertyContract(propertyId: string, contractId: string) {
    return this.request<any>(`/api/v1/properties/${propertyId}/contracts/${contractId}`, {
      method: 'DELETE'
    });
  }

  /**
   * Get a signed URL for a contract document
   */
  async getContractSignedUrl(propertyId: string, contractId: string) {
    return this.request<{
      signed_url: string;
      expires_in: number;
      document_name: string;
    }>(`/api/v1/properties/${propertyId}/contracts/${contractId}/signed-url`);
  }

  /**
   * Create a new property
   */
  async createProperty(property: any) {
    return this.request<any>('/api/v1/properties', {
      method: 'POST',
      body: JSON.stringify(property)
    });
  }

  /**
   * Get property availability
   */
  async getPropertyAvailability(propertyId: string, startDate: string, endDate: string) {
    return this.request<any>(
      `/api/v1/properties/${propertyId}/availability?start=${startDate}&end=${endDate}`
    );
  }

  /**
   * Availability checks (tenant-scoped)
   */
  async getAvailabilityChecks() {
    return this.request<any>('/api/v1/availability-checks');
  }

  // ============= REPUTATION NOTES =============
  /**
   * Get properties for reputation management (uses properties table)
   */
  async getReputationProperties(filters?: {
    city?: string;
    status?: string;
  }) {
    const params = new URLSearchParams();
    if (filters) {
      Object.entries(filters).forEach(([key, value]) => {
        if (value !== undefined) params.append(key, String(value));
      });
    }
    return this.request<any>(`/api/v1/reputation/properties?${params}`);
  }

  async getReputationNotes(propertyIds: string[]) {
    const params = new URLSearchParams();
    if (propertyIds && propertyIds.length) params.append('property_ids', propertyIds.join(','));
    return this.request<any>(`/api/v1/reputation/notes?${params}`);
  }

  async createReputationNote(payload: { property_id: string; content: string }) {
    return this.request<any>('/api/v1/reputation/notes', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  }

  async deleteReputationNote(id: string) {
    return this.request<any>(`/api/v1/reputation/notes/${id}`, {
      method: 'DELETE'
    });
  }

  // ============= LOCKBOXES =============
  async getLockboxes(filters?: {
    propertyId?: string;
    city?: string;
    page?: number;
    limit?: number;
    search?: string;
    status?: string;
    lockbox_type?: string;
  }) {
    const params = new URLSearchParams();
    if (filters?.propertyId) params.append('property_id', filters.propertyId);
    if (filters?.city) params.append('city', filters.city);
    if (filters?.page) params.append('page', filters.page.toString());
    if (filters?.limit) params.append('limit', filters.limit.toString());
    if (filters?.search) params.append('search', filters.search);
    if (filters?.status) params.append('status', filters.status);
    if (filters?.lockbox_type) params.append('lockbox_type', filters.lockbox_type);
    return this.request<any>(`/api/v1/lockboxes?${params}`);
  }

  async getLockbox(id: string) {
    return this.request<any>(`/api/v1/lockboxes/${id}`);
  }

  async createLockbox(payload: any) {
    return this.request<any>('/api/v1/lockboxes', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  }

  async updateLockbox(id: string, updates: any) {
    return this.request<any>(`/api/v1/lockboxes/${id}`, {
      method: 'PUT',
      body: JSON.stringify(updates)
    });
  }

  async deleteLockbox(id: string) {
    return this.request<any>(`/api/v1/lockboxes/${id}`, {
      method: 'DELETE'
    });
  }

  // ============= INTERNAL KEYS =============
  async getInternalKeys(filters?: {
    city?: string;
    page?: number;
    limit?: number;
    search?: string;
    status?: string;
  }) {
    const params = new URLSearchParams();
    if (filters?.city) params.append('city', filters.city);
    if (filters?.page) params.append('page', filters.page.toString());
    if (filters?.limit) params.append('limit', filters.limit.toString());
    if (filters?.search) params.append('search', filters.search);
    if (filters?.status) params.append('status', filters.status);
    return this.request<any>(`/api/v1/internal-keys?${params}`);
  }

  async createInternalKey(payload: any) {
    return this.request<any>('/api/v1/internal-keys', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  }

  async updateInternalKey(id: string, updates: any) {
    return this.request<any>(`/api/v1/internal-keys/${id}`, {
      method: 'PUT',
      body: JSON.stringify(updates)
    });
  }

  async deleteInternalKey(id: string) {
    return this.request<any>(`/api/v1/internal-keys/${id}`, {
      method: 'DELETE'
    });
  }

  async getInternalKey(id: string) {
    return this.request<any>(`/api/v1/internal-keys/${id}`);
  }

  // ============= KEYNEST =============
  async getKeynestKeys(filters?: { city?: string }) {
    const params = new URLSearchParams();
    if (filters?.city) params.append('city', filters.city);
    return this.request<any>(`/api/v1/keynest-keys?${params}`);
  }

  // ============= KEY ASSIGNMENTS =============
  async getActiveKeyAssignment(lockboxId: string) {
    const params = new URLSearchParams();
    params.append('lockbox_id', lockboxId);
    return this.request<any>(`/api/v1/key-assignments/active?${params}`);
  }

  async getBulkActiveKeyAssignments(lockboxIds: string[]) {
    return this.request<any>(`/api/v1/key-assignments/bulk-active`, {
      method: 'POST',
      body: JSON.stringify(lockboxIds)
    });
  }

  // ============= ACCESS LOGS =============
  async getAccessLogs(entityId: string, entityType: string, action?: string, limit: number = 10) {
    const params = new URLSearchParams();
    params.append('entity_id', entityId);
    params.append('entity_type', entityType);
    if (action) params.append('action', action);
    params.append('limit', limit.toString());
    return this.request<any>(`/api/v1/access-logs?${params}`);
  }

  async getBulkLastViewed(entityIds: string[], entityType: string) {
    return this.request<any>(`/api/v1/access-logs/bulk-last-viewed`, {
      method: 'POST',
      body: JSON.stringify({ entity_ids: entityIds, entity_type: entityType })
    });
  }

  async logAccess(entityId: string, entityType: string, action: string = 'view') {
    return this.request<any>('/api/v1/access-logs', {
      method: 'POST',
      body: JSON.stringify({ entity_id: entityId, entity_type: entityType, action })
    });
  }

  // ============= COMPANY SETTINGS API =============

  async getCompanySettings() {
    return this.request<any>('/api/v1/company-settings');
  }

  async updateCompanySettings(payload: Partial<{
    company_name: string;
    logo_url: string | null;
    domain: string | null;
    header_color: string;
    primary_color: string;
    secondary_color: string;
    accent_color: string;
    favicon_url: string | null;
  }>) {
    return this.request<any>('/api/v1/company-settings', {
      method: 'PUT',
      body: JSON.stringify(payload)
    });
  }

  // ============= DASHBOARD API =============
  /**
   * Get dashboard properties
   */
  async getDashboardProperties(options?: { simulatedTenant?: string, timestamp?: number }) {
    const queryParams = new URLSearchParams();
    if (options?.timestamp) {
      queryParams.append('_t', options.timestamp.toString());
    }

    const requestOptions: RequestInit = {};
    if (options?.simulatedTenant) {
      requestOptions.headers = {
        'X-Simulated-Tenant': options.simulatedTenant
      };
    }

    return this.request<any>(`/api/v1/dashboard/properties?${queryParams}`, requestOptions);
  }

  /**
   * Get dashboard summary with optional simulation header
   */
  async getDashboardSummary(propertyId: string, options?: { simulatedTenant?: string, timestamp?: number }) {
    const queryParams = new URLSearchParams({ property_id: propertyId });
    if (options?.timestamp) {
      queryParams.append('_t', options.timestamp.toString());
    }

    const requestOptions: RequestInit = {};
    if (options?.simulatedTenant) {
      requestOptions.headers = {
        'X-Simulated-Tenant': options.simulatedTenant
      };
    }

    return this.request<any>(`/api/v1/dashboard/summary?${queryParams}`, requestOptions);
  }

  async uploadCompanyLogo(logo_url: string) {
    return this.request<any>('/api/v1/company-settings/logo', {
      method: 'POST',
      body: JSON.stringify({ logo_url })
    });
  }

  async deleteCompanyLogo() {
    return this.request<any>('/api/v1/company-settings/logo', {
      method: 'DELETE'
    });
  }

  // ============= PORTAL CONFIGURATION (Pre-check-in) =============

  async getPortalConfiguration() {
    return this.request<any>('/api/v1/portal-configuration');
  }

  // ============= DEPARTMENTS =============

  async getDepartments() {
    const res = await this.request<any>('/api/v1/departments');
    // Backend returns array directly, not wrapped in an object
    return Array.isArray(res) ? res : (Array.isArray(res?.departments) ? res.departments : []);
  }

  async createDepartment(department: any) {
    return await this.request<any>('/api/v1/departments', {
      method: 'POST',
      body: JSON.stringify(department),
    });
  }

  async updateDepartment(id: string, department: any) {
    return await this.request<any>(`/api/v1/departments/${id}`, {
      method: 'PUT',
      body: JSON.stringify(department),
    });
  }

  async deleteDepartment(id: string) {
    return await this.request<any>(`/api/v1/departments/${id}`, {
      method: 'DELETE',
    });
  }

  async getMyDepartmentsWithPreferences() {
    const res = await this.request<any>('/api/v1/departments/my-departments');
    return Array.isArray(res) ? res : [];
  }

  async updateMyDepartmentPreference(departmentId: string, showInSidebar: boolean) {
    return await this.request<any>(`/api/v1/departments/my-departments/${departmentId}/preference`, {
      method: 'PUT',
      body: JSON.stringify({ show_in_sidebar: showInSidebar }),
    });
  }

  // ============= PROCESS DOCUMENTS =============

  async getProcessDocuments(departmentId: string, status: string = 'active') {
    const res = await this.request<any[]>(`/api/v1/departments/${departmentId}/process-documents?status=${status}`);
    return Array.isArray(res) ? res : [];
  }

  async createProcessDocument(data: { title: string; content: any; department_id: string }) {
    return this.request(`/api/v1/process-documents`, {
      method: 'POST',
      headers: {
        ...(await this.getAuthHeaders()),
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(data)
    });
  }

  async updateProcessDocument(id: string, data: { title?: string; content?: any; status?: string }) {
    // Ensure at least one key present
    const payload: any = {};
    if (data.title !== undefined) payload.title = data.title;
    if (data.content !== undefined) payload.content = data.content;
    if (data.status !== undefined) payload.status = data.status;
    return this.request(`/api/v1/process-documents/${id}`, {
      method: 'PUT',
      headers: {
        ...(await this.getAuthHeaders()),
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });
  }

  async archiveProcessDocument(id: string) {
    return this.updateProcessDocument(id, { status: 'archived' });
  }

  async restoreProcessDocument(id: string) {
    return this.updateProcessDocument(id, { status: 'active' });
  }

  async listProcessDocumentAttachments(documentId: string) {
    return this.request(`/api/v1/process-documents/${documentId}/attachments`, {
      method: 'GET',
      headers: await this.getAuthHeaders()
    });
  }


  async getProcessDocument(documentId: string) {
    return this.request<any>(`/api/v1/process-documents/${documentId}`);
  }

  async deleteProcessDocument(documentId: string) {
    return this.request<any>(`/api/v1/process-documents/${documentId}`, {
      method: 'DELETE',
    });
  }

  // ============= ATTACHMENTS =============

  async uploadProcessDocumentAttachment(documentId: string, file: File) {
    const headers: any = await this.getAuthHeaders();
    delete headers['Content-Type'];
    const form = new FormData();
    form.append('file', file);
    form.append('size', file.size.toString());
    const res = await fetch(`${this.backendUrl}/api/v1/process-documents/${documentId}/attachments`, {
      method: 'POST',
      headers,
      body: form
    });
    if (!res.ok) {
      const txt = await res.text().catch(() => '');
      throw new Error(`Upload failed (${res.status}) ${txt}`);
    }
    return res.json();
  }

  async uploadInlineAttachment(documentId: string, file: File, nodeId: string, context?: any) {
    const headers: any = await this.getAuthHeaders();
    delete headers['Content-Type']; // Let the browser set the multipart header
    const form = new FormData();
    form.append('file', file);
    form.append('size', file.size.toString());
    form.append('node_id', nodeId);
    if (context) {
      form.append('context_data', JSON.stringify(context));
    }

    const res = await fetch(`${this.backendUrl}/api/v1/process-documents/${documentId}/attachments/inline`, {
      method: 'POST',
      headers,
      body: form
    });

    if (!res.ok) {
      const txt = await res.text().catch(() => '');
      throw new Error(`Upload failed (${res.status}) ${txt}`);
    }
    return res.json();
  }

  async deleteProcessDocumentAttachment(attachmentId: string) {
    return this.request(`/api/v1/process-documents/attachments/${attachmentId}`, {
      method: 'DELETE',
      headers: await this.getAuthHeaders()
    });
  }

  async getAttachmentSignedUrl(attachmentId: string, expiresIn: number = 3600) {
    return this.request<{ signed_url: string; expires_in: number; file_name: string; mime_type: string }>(
      `/api/v1/process-documents/attachments/${attachmentId}/signed-url?expires_in=${expiresIn}`,
      {
        method: 'GET',
        headers: await this.getAuthHeaders()
      }
    );
  }

  // ============= DEPARTMENT DOCUMENTS =============

  async getDepartmentDocuments(departmentId: string, status: string = 'active') {
    const res = await this.request<any[]>(`/api/v1/departments/${departmentId}/documents?status=${status}`);
    return Array.isArray(res) ? res : [];
  }

  // ============= PERMISSION TEMPLATES =============

  async getPermissionTemplates(params?: { department_id?: string; is_active?: boolean }) {
    const queryParams = new URLSearchParams();
    if (params?.department_id) queryParams.append('department_id', params.department_id);
    if (params?.is_active !== undefined) queryParams.append('is_active', String(params.is_active));

    const res = await this.request<any>(`/api/v1/permission_templates?${queryParams}`);
    return Array.isArray(res?.permission_templates) ? res.permission_templates : [];
  }

  async createPermissionTemplate(template: any) {
    return await this.request<any>('/api/v1/permission_templates', {
      method: 'POST',
      body: JSON.stringify(template),
    });
  }

  async updatePermissionTemplate(id: string, template: any) {
    return await this.request<any>(`/api/v1/permission_templates/${id}`, {
      method: 'PUT',
      body: JSON.stringify(template),
    });
  }

  async deletePermissionTemplate(id: string) {
    return await this.request<any>(`/api/v1/permission_templates/${id}`, {
      method: 'DELETE',
    });
  }

  // ============= ACTIVITY LOGS =============

  async getLogs(params: {
    searchTerm?: string;
    user_id?: string;
    section?: string;
    entity_type?: string;
    action?: string;
    user_type?: 'system' | 'users';
    sortAscending?: boolean;
    page?: number;
    page_size?: number;
  }) {
    const qs = new URLSearchParams();
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') qs.append(k, String(v));
    });
    return this.request<any>(`/api/v1/logs?${qs.toString()}`);
  }

  async exportLogs(params: {
    searchTerm?: string;
    user_id?: string;
    section?: string;
    entity_type?: string;
    action?: string;
    user_type?: 'system' | 'users';
    sortAscending?: boolean;
  }) {
    const qs = new URLSearchParams();
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') qs.append(k, String(v));
    });
    return this.request<any>(`/api/v1/logs/export?${qs.toString()}`);
  }

  // ============= PROPERTIES (tenant-scoped) =============

  /**
   * Get all properties (tenant-scoped)
   */
  async getAllProperties() {
    // Delegate to getProperties which already normalizes response and is tenant-scoped
    const res = await this.getProperties({ page_size: 1000 });
    // Ensure consistent format { data, total }
    if (res && typeof res === 'object' && 'data' in res) return res as any;
    if (Array.isArray(res)) return { data: res, total: res.length };
    return { data: [], total: 0 };
  }

  async createLog(payload: any) {
    return this.request<any>('/api/v1/logs', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  }

  async updatePortalConfiguration(payload: Partial<{
    portal_base_url: string;
    enable_auto_creation: boolean;
    portal_expiry_days: number;
    default_locale: string;
    id_verification_auto_approval: boolean;
  }>) {
    return this.request<any>('/api/v1/portal-configuration', {
      method: 'PUT',
      body: JSON.stringify(payload)
    });
  }

  // ============= CUSTOM FIELDS API =============

  /**
   * Get custom fields for the tenant
   */
  async getCustomFields() {
    // Note: custom_fields table doesn't have entity_type - all fields are for the tenant
    return this.request<any>('/api/v1/custom-fields');
  }

  /**
   * Create a new custom field
   */
  async createCustomField(fieldData: any) {
    return this.request<any>('/api/v1/custom-fields', {
      method: 'POST',
      body: JSON.stringify(fieldData)
    });
  }

  /**
   * Update a custom field
   */
  async updateCustomField(fieldId: string, fieldData: any) {
    return this.request<any>(`/api/v1/custom-fields/${fieldId}`, {
      method: 'PUT',
      body: JSON.stringify(fieldData)
    });
  }

  /**
   * Get custom field values for a reservation
   */
  async getCustomFieldValues(reservationId: string) {
    try {
      return await this.request<any>(`/api/v1/custom-fields/values/${reservationId}`);
    } catch (error: any) {
      // Don't log errors for missing reservations (404) - this is expected
      // when reservations haven't been synced to consolidated table yet
      if (error?.message?.includes('404') || error?.message?.includes('not found')) {
        return {};
      }
      // For other errors, still log them but return empty object
      console.debug('Custom field values fetch error:', error?.message);
      return {};
    }
  }

  /**
   * Update custom field values
   */
  async updateCustomFieldValues(reservationId: string, values: Record<string, any>) {
    return this.request<any>(`/api/v1/custom-fields/values/${reservationId}`, {
      method: 'PUT',
      body: JSON.stringify(values)
    });
  }

  /**
   * Bulk update custom field values
   */
  async bulkUpdateCustomFieldValues(reservationIds: string[], fieldId: string, value: any) {
    return this.request<any>('/api/v1/custom-fields/bulk-update', {
      method: 'POST',
      body: JSON.stringify({ reservation_ids: reservationIds, field_id: fieldId, value })
    });
  }

  // ============= FINANCE API =============

  /**
   * Get financial data for properties
   */
  async getFinancialData(filters?: {
    property_id?: string;
    date_from?: string;
    date_to?: string;
  }) {
    const params = new URLSearchParams();
    if (filters) {
      Object.entries(filters).forEach(([key, value]) => {
        if (value !== undefined) params.append(key, String(value));
      });
    }
    return this.request<any>(`/api/v1/finance/summary?${params}`);
  }

  /**
   * Get revenue report
   */
  async getRevenueReport(startDate: string, endDate: string) {
    return this.request<any>(
      `/api/v1/finance/revenue?start=${startDate}&end=${endDate}`
    );
  }

  // ============= SECURITY & MONITORING =============

  /**
   * Get security violations detected in this session
   */
  getSecurityViolations(): string[] {
    return [...this.securityViolations];
  }

  // ============= AUTH INFO =============

  /**
   * Get current user context (permissions, cities, tenant_id, metadata)
   */
  async getAuthMe(refresh: boolean = false): Promise<{
    id: string;
    email: string;
    is_admin: boolean;
    tenant_id: string | null;
    permissions: Array<{ section: string; action: string }>;
    cities: string[];
    departments: string[];
    user_metadata?: Record<string, any> | null;
    app_metadata?: Record<string, any> | null;
  }> {
    const url = refresh ? '/api/v1/auth/me?refresh=true' : '/api/v1/auth/me';
    return this.request<any>(url);
  }

  // ============= PROFILE =============

  /**
   * Get current user's profile bundle (profile, preferences, notification prefs)
   */
  async getMyProfile(): Promise<{
    profile: any;
    preferences: any;
    notification_preferences: any[];
    unread_count: number;
  }> {
    return this.request<any>('/api/v1/profile');
  }

  /**
   * Get brief user info for current tenant; optional filter by IDs
   */
  async getUsersBrief(ids?: string[]): Promise<Array<{ id: string; email: string; name?: string }>> {
    const qs = ids && ids.length ? `?ids=${encodeURIComponent(ids.join(','))}` : '';
    const res = await this.request<any>(`/api/v1/users/brief${qs}`);
    return Array.isArray(res?.users) ? res.users : [];
  }

  /**
   * Get recent access logs for current user
   */
  async getRecentUserLogs(limit: number = 10): Promise<any[]> {
    const res = await this.request<any>(`/api/v1/logs/recent?limit=${limit}&user_only=true`);
    return Array.isArray(res?.data) ? res.data : [];
  }

  /**
   * Get consolidated dashboard data
   */
  async getDashboardData(): Promise<any> {
    return this.request<any>('/api/v1/dashboard/data');
  }


  /**
   * Clear security violations log
   */
  clearSecurityViolations(): void {
    this.securityViolations = [];
  }

  /**
   * Get request statistics
   */
  getRequestStats() {
    return {
      totalRequests: this.requestCount,
      securityViolations: this.securityViolations.length,
      backendUrl: this.backendUrl,
      hasCachedToken: !!this.cachedToken
    };
  }

  /**
   * Verify tenant isolation is working
   */
  async verifyTenantIsolation(): Promise<{
    isolated: boolean;
    tenantId: string;
    message: string;
  }> {
    try {
      const data = await this.request<any>('/api/v1/auth/verify-tenant');
      return {
        isolated: true,
        tenantId: data.tenant_id,
        message: 'Tenant isolation verified successfully'
      };
    } catch (error) {
      return {
        isolated: false,
        tenantId: 'unknown',
        message: 'Tenant isolation verification failed'
      };
    }
  }

  // ============= ADDITIONAL SECURE METHODS =============

  /**
   * Check if API connection is working
   */
  async checkConnection(): Promise<boolean> {
    try {
      await this.requestPublic<any>('/api/v1/health');
      return true;
    } catch {
      try {
        await this.requestPublic<any>('/health');
        return true;
      } catch {
        return false;
      }
    }
  }

  /**
   * Check if we have a valid auth token and it works
   * This actually verifies authentication, unlike checkConnection
   */
  async checkAuthReady(): Promise<boolean> {
    try {
      // First check if we have a cached token
      if (!this.cachedToken) {
        console.log('[SecureAPI] No cached token, auth not ready');
        return false;
      }

      // Try to make an authenticated request to verify the token works
      try {
        await this.getAuthMe();
        console.log('[SecureAPI] Auth verified successfully');
        return true;
      } catch (err) {
        console.log('[SecureAPI] Auth token invalid or expired:', err);
        return false;
      }
    } catch (e) {
      console.log('[SecureAPI] Auth check failed:', e);
      return false;
    }
  }

  /**
   * Get property by ID
   */
  async getPropertyById(id: string) {
    return this.request<any>(`/api/v1/properties/${id}`);
  }

  /**
   * Get properties in radius
   */
  async getPropertiesInRadius(params: {
    center_lat: number;
    center_lng: number;
    radius_km: number;
    exclude_property_id?: string;
    city_filter?: string;
    bedrooms?: number;
  }) {
    const queryParams = new URLSearchParams(params as any);
    return this.request<any>(`/api/v1/properties/in-radius?${queryParams}`);
  }

  /**
   * Check if property exists with specific hostaway_id
   */
  async checkPropertyExists(hostawayId: string): Promise<boolean> {
    try {
      const response = await this.request<any>(`/api/v1/properties/check-exists?hostaway_id=${hostawayId}`);
      return response.exists;
    } catch {
      return false;
    }
  }

  /**
   * Property draft management
   */
  async createPropertyDraft(draft: any) {
    return this.request<any>('/api/v1/property-drafts', {
      method: 'POST',
      body: JSON.stringify(draft)
    });
  }

  async getPropertyDraft(id: string, userId?: string) {
    const params = userId ? `?user_id=${userId}` : '';
    return this.request<any>(`/api/v1/property-drafts/${id}${params}`);
  }

  async updatePropertyDraft(id: string, updates: any) {
    return this.request<any>(`/api/v1/property-drafts/${id}`, {
      method: 'PUT',
      body: JSON.stringify(updates)
    });
  }

  async deletePropertyDraft(id: string) {
    return this.request<any>(`/api/v1/property-drafts/${id}`, {
      method: 'DELETE'
    });
  }

  /**
   * Organization modules management
   */
  async getMyOrgModules(): Promise<string[]> {
    const res = await this.request<any>('/api/v1/organizations/my-modules');
    if (Array.isArray(res?.modules)) return res.modules as string[];
    return [];
  }

  /**
   * Cleaning reports management
   */
  async getCleaningReports(filters: any, signal?: AbortSignal) {
    const params = new URLSearchParams();
    if (filters.city) params.append('city', String(filters.city));
    if (filters.date_from) params.append('date_from', String(filters.date_from));
    if (filters.date_to) params.append('date_to', String(filters.date_to));
    if (filters.status) params.append('status', String(filters.status));
    if (filters.booking_status) params.append('booking_status', String(filters.booking_status));
    if (filters.property_id) params.append('property_id', String(filters.property_id));
    if (filters.search) params.append('search', String(filters.search));
    if (filters.page) params.append('page', String(filters.page));
    if (filters.itemsPerPage) params.append('itemsPerPage', String(filters.itemsPerPage));

    // Use the secure endpoint that validates user city access
    const endpoint = `/api/v1/secure/cleaning/reports?${params}`;

    try {
      const result = await this.request<any>(endpoint, { signal });

      // Additional validation for cleaning results
      if (result && typeof result === 'object') {
        const items = result.items || result.data || [];
        const total = result.total || 0;

        // Log potential issues for monitoring
        if (total === 0 && filters.date_from === 'overdue') {
          console.warn('[SecureAPI] Received empty overdue cleaning data - this may indicate a backend issue');
        }

        // Specific validation for tomorrow's data
        const isTomorrowRequest = filters.date_from && filters.date_to && filters.date_from === filters.date_to &&
          filters.date_from === new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString().split('T')[0];

        if (isTomorrowRequest) {
          console.log('[SecureAPI] Tomorrow cleaning request completed', {
            endpoint: endpoint.substring(0, 80) + '...',
            total,
            itemsLength: items.length,
            dateRequested: filters.date_from,
            city: filters.city,
            cacheKey: await this.generateCacheKey('GET', endpoint, await this.getTenantId() || 'unknown')
          });

          if (total === 0) {
            console.warn('[SecureAPI] Tomorrow returned 0 cleanings - verify this is correct', {
              filters,
              cacheAge: 'fresh_request'
            });
          }
        }

        console.log(`[SecureAPI] Cleaning request completed: ${endpoint.substring(0, 80)}... -> ${total} items`);
      }

      return result;
    } catch (error) {
      console.error(`[SecureAPI] Cleaning request failed: ${endpoint.substring(0, 80)}...`, error);
      throw error;
    }
  }

  async createCleaningReport(payload: any) {
    // Use secure endpoint that validates user city access
    return this.request<any>(`/api/v1/secure/cleaning/reports`, {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  }

  async updateCleaningReport(id: string, updates: any) {
    // Use secure endpoint that validates user city access
    return this.request<any>(`/api/v1/secure/cleaning/reports/${id}`, {
      method: 'PUT',
      body: JSON.stringify(updates)
    });
  }

  async deleteCleaningReport(id: string) {
    // Use secure endpoint that validates user city access
    return this.request<any>(`/api/v1/secure/cleaning/reports/${id}`, {
      method: 'DELETE'
    });
  }

  async getCleaningNotes(cleaningId: string) {
    // Use secure endpoint that validates user city access
    return this.request<any>(`/api/v1/secure/cleaning/notes/${cleaningId}`);
  }

  async addCleaningNote(note: { cleaning_id: string; content: string }) {
    // Use secure endpoint that validates user city access
    return this.request<any>('/api/v1/secure/cleaning/notes', {
      method: 'POST',
      body: JSON.stringify(note)
    });
  }

  async createCleaningNote(note: any) {
    // Use secure endpoint that validates user city access
    return this.request<any>(`/api/v1/secure/cleaning/notes`, {
      method: 'POST',
      body: JSON.stringify(note)
    });
  }

  async deleteCleaningsByParentId(parentId: string) {
    return this.request<any>(`/api/v1/cleaning-reports/by-parent/${parentId}`, {
      method: 'DELETE'
    });
  }

  /**
   * Announcements management
   */
  async getAnnouncements(filters: any) {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== undefined) params.append(key, String(value));
    });
    return this.request<any>(`/api/v1/announcements?${params}`);
  }

  async createAnnouncement(announcement: any) {
    return this.request<any>('/api/v1/announcements', {
      method: 'POST',
      body: JSON.stringify(announcement)
    });
  }

  async acknowledgeAnnouncement(announcementId: string, userId: string) {
    return this.request<any>('/api/v1/announcements/acknowledge', {
      method: 'POST',
      body: JSON.stringify({ announcement_id: announcementId, user_id: userId })
    });
  }

  // ============= CLEANERS API =============

  /**
   * Get all cleaners
   */
  async getCleaners() {
    // Use secure endpoint with tenant isolation
    return this.request<any>('/api/v1/secure/cleaning/cleaners');
  }

  /**
   * Create a new cleaner
   */
  async createCleaner(data: { name: string }) {
    // Use secure endpoint with tenant isolation
    return this.request<any>('/api/v1/secure/cleaning/cleaners', {
      method: 'POST',
      body: JSON.stringify(data)
    });
  }

  /**
   * Delete a cleaner
   */
  async deleteCleaner(id: string) {
    // Use secure endpoint with tenant isolation
    return this.request<any>(`/api/v1/secure/cleaning/cleaners/${id}`, {
      method: 'DELETE'
    });
  }

  // ============= CONTRACT RECORDS API =============

  /**
   * Get contract records for a property
   */
  async getContractRecords(propertyId: string) {
    return this.request<any>(`/api/v1/properties/${propertyId}/contracts`);
  }

  /**
   * Create a contract record
   */
  async createContractRecord(data: any) {
    return this.request<any>('/api/v1/contract-records', {
      method: 'POST',
      body: JSON.stringify(data)
    });
  }

  /**
   * Update a contract record
   */
  async updateContractRecord(id: string, data: any) {
    return this.request<any>(`/api/v1/contract-records/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    });
  }

  /**
   * Delete a contract record
   */
  async deleteContractRecord(id: string) {
    return this.request<any>(`/api/v1/contract-records/${id}`, {
      method: 'DELETE'
    });
  }

  // ============= RESERVATION SUBSECTIONS (SMART VIEWS) API =============

  /**
   * Get all reservation subsections/smart views
   */
  async getAllReservationSubsections(params?: URLSearchParams) {
    const query = params ? `?${params.toString()}` : '';
    return this.request<any>(`/api/v1/smart-views${query}`);
  }

  /**
   * Get a single reservation subsection/smart view
   */
  async getReservationSubsection(id: string) {
    return this.request<any>(`/api/v1/smart-views/${id}`);
  }

  /**
   * Create a reservation subsection/smart view
   */
  async createReservationSubsection(data: any) {
    return this.request<any>('/api/v1/smart-views', {
      method: 'POST',
      body: JSON.stringify(data)
    });
  }

  /**
   * Update a reservation subsection/smart view
   */
  async updateReservationSubsection(id: string, data: any) {
    return this.request<any>(`/api/v1/smart-views/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    });
  }

  /**
   * Delete a reservation subsection/smart view
   */
  async deleteReservationSubsection(id: string) {
    return this.request<any>(`/api/v1/smart-views/${id}`, {
      method: 'DELETE'
    });
  }

  /**
   * Duplicate a reservation subsection/smart view
   */
  async duplicateReservationSubsection(id: string, data: any) {
    return this.request<any>(`/api/v1/smart-views/${id}/duplicate`, {
      method: 'POST',
      body: JSON.stringify(data)
    });
  }

  // ============= GUEST PORTAL VERIFICATION API =============

  /**
   * Get ID verifications based on status filter
   */
  async getVerifications(statusFilter: string = 'pending') {
    let endpoint = '/api/v1/guest-portal/verification-status';

    if (statusFilter === 'pending') {
      endpoint += '/pending';
    } else if (statusFilter === 'all') {
      endpoint += '/all';
    } else if (statusFilter) {
      endpoint += `/${statusFilter}`;
    }

    return this.request<any>(endpoint);
  }

  /**
   * Review an ID verification
   */
  async reviewVerification(verificationId: string, reviewData: any) {
    return this.request<any>(`/api/v1/guest-portal/review-verification/${verificationId}`, {
      method: 'POST',
      body: JSON.stringify(reviewData)
    });
  }

  // ============= TRANSLATION API =============

  /**
   * Trigger AI translation for an entity
   */
  async translateEntity(entityType: string, entityId: string, fields: string[], languages: string[]) {
    return this.request<any>(`/api/v1/translations/${entityType}/${entityId}/translate`, {
      method: 'POST',
      body: JSON.stringify({
        fields: fields,
        languages: languages
      })
    });
  }

  // ============= FORMULAS API =============

  /**
   * Get all formulas for the current tenant
   */
  async getFormulas() {
    return this.request<any[]>('/api/v1/formulas');
  }

  /**
   * Create a new formula
   */
  async createFormula(formula: { name: string; description?: string; composition: string }) {
    return this.request<any>('/api/v1/formulas', {
      method: 'POST',
      body: JSON.stringify(formula)
    });
  }

  /**
   * Update an existing formula
   */
  async updateFormula(formulaId: string, updates: { name?: string; description?: string; composition?: string; order_index?: number }) {
    return this.request<any>(`/api/v1/formulas/${formulaId}`, {
      method: 'PUT',
      body: JSON.stringify(updates)
    });
  }

  /**
   * Delete a formula
   */
  async deleteFormula(formulaId: string) {
    return this.request<any>(`/api/v1/formulas/${formulaId}`, {
      method: 'DELETE'
    });
  }
}

// Export singleton instance
export const SecureAPI = SecureAPIClient.getInstance();

// Export convenience functions for common operations
export const secureReservations = {
  getAll: () => SecureAPI.getAllReservations(),
  get: (id: string) => SecureAPI.getReservation(id),
  update: (id: string, data: any) => SecureAPI.updateReservation(id, data),
  create: (data: any) => SecureAPI.createReservation(data),
  delete: (id: string) => SecureAPI.deleteReservation(id),
  getFilterOptions: () => SecureAPI.getReservationFilterOptions(),
  invalidateCache: (propertyId?: string) => SecureAPI.invalidateReservationCache(propertyId),
  getCached: (forceRefresh?: boolean) => SecureAPI.getCachedReservations(!!forceRefresh)
};

export const secureProperties = {
  getAll: () => SecureAPI.getAllProperties(),
  get: (id: string) => SecureAPI.getProperty(id),
  update: (id: string, data: any) => SecureAPI.updateProperty(id, data),
  create: (data: any) => SecureAPI.createProperty(data),
  getAvailability: (id: string, start: string, end: string) =>
    SecureAPI.getPropertyAvailability(id, start, end)
};

export const secureCleaning = {
  getReports: (filters: any, signal?: AbortSignal) => SecureAPI.getCleaningReports(filters, signal),
  clearCache: () => SecureAPI.clearEndpointCache('secure/cleaning/reports'),
  getDiagnostics: () => SecureAPI.getCacheDiagnostics()
};

export const secureFormulas = {
  getAll: () => SecureAPI.getFormulas(),
  create: (formula: { name: string; description?: string; composition: string }) => SecureAPI.createFormula(formula),
  update: (id: string, updates: { name?: string; description?: string; composition?: string; order_index?: number }) =>
    SecureAPI.updateFormula(id, updates),
  delete: (id: string) => SecureAPI.deleteFormula(id)
};

// Prevent direct exports of supabase to force secure API usage
if (import.meta.env.DEV) {
  console.warn('🔒 SecureAPI initialized - Direct Supabase queries are now blocked');

  // Make cache diagnostics available globally for debugging
  (window as any).secureApiDiagnostics = () => SecureAPI.getCacheDiagnostics();
  (window as any).clearCleaningCache = () => SecureAPI.clearEndpointCache('secure/cleaning/reports');
  console.log('🔧 Debug utilities added: secureApiDiagnostics(), clearCleaningCache()');
}
