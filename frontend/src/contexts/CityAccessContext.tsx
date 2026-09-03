import React, { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react';
import { toast } from 'react-toastify';
import { useAuth } from '../contexts/AuthContext.new';
import { supabase } from '../lib/supabase';
import { getApiBase } from '../lib/apiBase';
import { cityAccessEvents } from '../lib/cityAccessEvents';
import { cityAccessService, CityAccessError } from '../services/CityAccessService';

interface CityAccessResponse {
  cities: string[];
  is_admin: boolean;
  response_time_ms: number;
  cache_hit: boolean;
  error?: string;
}

interface CityAccessContextType {
  // Core data
  cities: string[];
  isAdmin: boolean;
  loading: boolean;
  error: string | null;
  initialized: boolean;
  
  // Performance metrics
  lastFetchTime: number;
  cacheSource: 'none' | 'memory' | 'session' | 'api';
  
  // Methods
  hasAccessToCity: (city: string) => boolean;
  refreshCities: () => Promise<void>;
  clearCache: () => void;
}

const CityAccessContext = createContext<CityAccessContextType>({
  cities: [],
  isAdmin: false,
  loading: true,
  error: null,
  initialized: false,
  lastFetchTime: 0,
  cacheSource: 'none',
  hasAccessToCity: () => false,
  refreshCities: async () => {},
  clearCache: () => {},
});

// Admin emails - should match backend
const ADMIN_EMAILS = [
  'sid@theflexliving.com',
  'raouf@theflexliving.com',
  'michael@theflexliving.com',
  'yazid@theflexliving.com',
];

// Cache configuration
const CACHE_KEY_PREFIX = 'city_access_cache';
const CACHE_DURATION = 3600000; // 1 hour in milliseconds

interface CachedCityAccess {
  cities: string[];
  isAdmin: boolean;
  timestamp: number;
  userId: string;
  tenantId?: string;
}

export function CityAccessProvider({ children }: { children: React.ReactNode }) {
  const auth = useAuth();
  const { user } = auth;
  const authLoading = auth.status === 'initializing';
  
  // State
  const [cities, setCities] = useState<string[]>([]);
  const [isAdmin, setIsAdmin] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [initialized, setInitialized] = useState(false);
  const [lastFetchTime, setLastFetchTime] = useState(0);
  const [cacheSource, setCacheSource] = useState<'none' | 'memory' | 'session' | 'api'>('none');
  
  // Refs to prevent duplicate fetches and API flooding
  const fetchingRef = useRef(false);
  const lastUserIdRef = useRef<string | null>(null);
  const memoryCacheRef = useRef<CachedCityAccess | null>(null);
  const activeRequestRef = useRef<Promise<any> | null>(null);
  const requestTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  /**
   * Get cache key for current user with tenant isolation
   */
  const getCacheKey = useCallback((userId: string, tenantId?: string) => {
    const tenant = tenantId || user?.tenant_id || 'default';
    const key = `${CACHE_KEY_PREFIX}_${userId}_${tenant}`;
    
    // 🔒 DEBUG: Log cache key generation for debugging
    if (import.meta.env.DEV) {
      console.log(`🔒 CACHE_KEY: Generated key for user ${userId}, tenant ${tenant}: ${key}`);
    }
    
    return key;
  }, [user?.tenant_id]);

  // 🔒 MONITORING: Add tenant state monitoring
  const logTenantState = useCallback(() => {
    if (!import.meta.env.DEV) return;
    
    console.group('🔒 TENANT_STATE_DEBUG');
    console.log('Current User:', {
      id: user?.id,
      email: user?.email,
      tenant_id: user?.tenant_id
    });
    console.log('Cities Context:', {
      cities,
      loading,
      initialized,
      cacheSource
    });
    console.log('Cache State:', {
      hasMemoryCache: !!memoryCacheRef.current,
      lastUserId: lastUserIdRef.current,
      previousTenant: previousTenantRef.current
    });
    console.groupEnd();
  }, [user, cities, loading, initialized, cacheSource]);

  /**
   * Load from session storage
   */
  const loadFromSessionStorage = useCallback((userId: string, tenantId?: string): CachedCityAccess | null => {
    try {
      const cacheKey = getCacheKey(userId, tenantId);
      const cached = sessionStorage.getItem(cacheKey);
      
      if (!cached) {
        return null;
      }
      
      const data = JSON.parse(cached) as CachedCityAccess;
      
      // Validate cache age
      const age = Date.now() - data.timestamp;
      if (age > CACHE_DURATION) {
        console.log('[CityAccessContext] Session cache expired, age:', Math.round(age / 1000), 'seconds');
        sessionStorage.removeItem(cacheKey);
        return null;
      }
      
      // Validate it's for the same user and tenant
      if (data.userId !== userId) {
        console.log('[CityAccessContext] Session cache user mismatch');
        sessionStorage.removeItem(cacheKey);
        return null;
      }
      
      // Validate tenant consistency for security
      const currentTenant = tenantId || user?.tenant_id || 'default';
      if (data.tenantId && data.tenantId !== currentTenant) {
        console.warn(`🔒 SECURITY: Session cache tenant mismatch. Expected: ${currentTenant}, Found: ${data.tenantId}`);
        sessionStorage.removeItem(cacheKey);
        return null;
      }
      
      console.log('[CityAccessContext] Loaded from session cache, age:', Math.round(age / 1000), 'seconds');
      return data;
    } catch (err) {
      console.error('[CityAccessContext] Error loading from session storage:', err);
      return null;
    }
  }, [getCacheKey, user?.tenant_id]);

  /**
   * Save to session storage
   */
  const saveToSessionStorage = useCallback((userId: string, cities: string[], isAdmin: boolean, tenantId?: string) => {
    try {
      const cacheKey = getCacheKey(userId, tenantId);
      const data: CachedCityAccess = {
        cities,
        isAdmin,
        timestamp: Date.now(),
        userId,
        tenantId,
      };
      
      sessionStorage.setItem(cacheKey, JSON.stringify(data));
      memoryCacheRef.current = data;
      console.log('[CityAccessContext] Saved to session storage and memory cache');
    } catch (err) {
      console.error('[CityAccessContext] Error saving to session storage:', err);
    }
  }, [getCacheKey]);

  /**
   * Fetch cities from API
   */
  const fetchCitiesFromAPI = useCallback(async (userObj: any): Promise<{ cities: string[], isAdmin: boolean } | null> => {
    try {
      const startTime = Date.now();
      const { data: { session } } = await supabase.auth.getSession();
      
      if (!session) {
        console.error('[CityAccessContext] No session available');
        return null;
      }
      
      const backend = getApiBase();
      
      console.log('[CityAccessContext] Fetching from enhanced filters endpoint with stability fixes');
      
      // Use our enhanced endpoint with comprehensive tenant validation
      const endpoint = `${backend}/api/v1/filters/cities-and-portfolios`;
      console.log('[CityAccessContext] Fetching from:', endpoint);
      console.log('[CityAccessContext] Auth token present:', !!session.access_token);
      
      const resp = await fetch(endpoint, {
        headers: {
          'Authorization': `Bearer ${session.access_token}`,
          'Content-Type': 'application/json'
        }
      });
      
      console.log('[CityAccessContext] Response status:', resp.status);
      console.log('[CityAccessContext] Response ok:', resp.ok);
      
      if (resp.ok) {
        const json = await resp.json();
        const elapsed = Date.now() - startTime;
        
        console.log('[CityAccessContext] ✅ Enhanced API Response SUCCESS:', {
          fullResponse: json,
          success: json.success,
          tenant_id: json.tenant_id,
          citiesCount: json.cities?.length || 0,
          portfoliosCount: json.portfolios?.length || 0,
          totalTime: elapsed
        });
        
        // Extract cities from the filters endpoint response format
        const citiesArray: string[] = [];
        if (json.cities && Array.isArray(json.cities)) {
          json.cities.forEach((cityObj: any) => {
            if (cityObj && cityObj.value && cityObj.value !== '') {
              citiesArray.push(cityObj.value);
            }
          });
        }
        
        // Check if user is admin (for now, use email check since filters endpoint doesn't return this)
        const userIsAdmin = ADMIN_EMAILS.includes(userObj.email || '') || 
                           userObj.app_metadata?.role === 'admin';
        
        console.log('🏙️ CITIES_DEBUG: Enhanced endpoint cities analysis:', {
          rawCitiesResponse: json.cities,
          extractedCitiesArray: citiesArray,
          extractedCount: citiesArray.length,
          tenantId: json.tenant_id,
          isAdmin: userIsAdmin,
          userEmail: userObj.email
        });
        
        if (json.tenant_id && userObj.tenant_id && json.tenant_id !== userObj.tenant_id) {
          console.error('🚨 TENANT_MISMATCH: Response tenant_id does not match user tenant_id:', {
            responseTeantId: json.tenant_id,
            userTenantId: userObj.tenant_id,
            userEmail: userObj.email
          });
        } else if (json.tenant_id) {
          console.log('✅ TENANT_VALIDATION: Response tenant_id matches user context:', json.tenant_id);
        }
        
        return {
          cities: citiesArray,
          isAdmin: userIsAdmin
        };
      } else {
        // Get error response body for debugging
        const errorText = await resp.text();
        console.error('[CityAccessContext] API failed with status:', resp.status);
        console.error('[CityAccessContext] Error response body:', errorText);
      }
      
      // Check if user is admin locally as fallback
      const userIsAdmin = ADMIN_EMAILS.includes(userObj.email || '') || 
                         userObj.app_metadata?.role === 'admin';
      
      if (userIsAdmin) {
        console.log('[CityAccessContext] Using admin fallback');
        return {
          cities: ['london', 'paris', 'algiers', 'lisbon'],
          isAdmin: true
        };
      }
      
      return null;
    } catch (err) {
      console.error('[CityAccessContext] Error fetching from API:', err);
      console.error('[CityAccessContext] Error details:', {
        message: err instanceof Error ? err.message : 'Unknown error',
        stack: err instanceof Error ? err.stack : undefined,
        userEmail: userObj.email,
        backend
      });
      
      // Check if user is admin locally as fallback for errors
      const userIsAdmin = ADMIN_EMAILS.includes(userObj.email || '') ||
                         userObj.app_metadata?.role === 'admin';
      
      console.log('[CityAccessContext] Error fallback admin check:', {
        userEmail: userObj.email,
        isInAdminEmails: ADMIN_EMAILS.includes(userObj.email || ''),
        appMetadataRole: userObj.app_metadata?.role,
        userIsAdmin
      });
      
      if (userIsAdmin) {
        console.log('[CityAccessContext] Error fallback - granting all cities to admin');
        return { cities: ['london', 'paris', 'algiers', 'lisbon'], isAdmin: true };
      }
      
      return null;
    }
  }, []);

  // 🔒 JWT Token Validation
  const validateJWTTokenConsistency = useCallback(async (): Promise<boolean> => {
    try {
      const { data: { session } } = await supabase.auth.getSession();
      
      if (!session) {
        console.warn('[CityAccessContext] 🚨 No session found during JWT validation');
        return false;
      }
      
      if (!user) {
        console.warn('[CityAccessContext] 🚨 No user context during JWT validation');
        return false;
      }
      
      // Decode JWT to check actual user
      const claims = decodeJWTPayload(session.access_token);
      
      if (!claims) {
        console.error('[CityAccessContext] 🚨 Failed to decode JWT claims');
        return false;
      }
      
      // Check if JWT user matches frontend user context
      if (claims.sub !== user.id) {
        console.error('[CityAccessContext] 🚨 JWT MISMATCH DETECTED:', {
          frontendUserId: user.id,
          frontendUserEmail: user.email,
          jwtUserId: claims.sub,
          jwtUserEmail: claims.email,
          tokenPreview: session.access_token.substring(0, 20) + '...'
        });
        return false;
      }
      
      // Check if JWT user email matches frontend user email
      if (claims.email !== user.email) {
        console.error('[CityAccessContext] 🚨 JWT EMAIL MISMATCH:', {
          frontendEmail: user.email,
          jwtEmail: claims.email
        });
        return false;
      }
      
      console.log('[CityAccessContext] ✅ JWT validation passed:', {
        userId: user.id,
        email: user.email,
        tenantId: claims.tenant_id || user.tenant_id
      });
      
      return true;
    } catch (error) {
      console.error('[CityAccessContext] JWT validation error:', error);
      return false;
    }
  }, [user]);

  // Import JWT decoder
  const decodeJWTPayload = useCallback((token: string) => {
    try {
      const parts = token.split('.');
      if (parts.length !== 3) return null;
      
      const payload = parts[1];
      const paddedPayload = payload + '=='.substring(0, (4 - (payload.length % 4)) % 4);
      const decodedBytes = atob(paddedPayload);
      return JSON.parse(decodedBytes);
    } catch (error) {
      console.error('[CityAccessContext] JWT decode error:', error);
      return null;
    }
  }, []);

  /**
   * Main fetch function that tries all cache levels
   */
  const fetchCityAccess = useCallback(async (forceRefresh = false) => {
    const urlParams = new URLSearchParams(window.location.search);
    const cacheBypass = urlParams.has('nocache');
    
    if (cacheBypass) {
      console.log('🔥 CACHE BYPASS ACTIVE: nocache=true detected in URL - skipping all cache layers');
      forceRefresh = true;
    }
    
    console.log('[CityAccessContext] fetchCityAccess called:', {
      hasUser: !!user,
      userEmail: user?.email,
      forceRefresh,
      cacheBypass,
      currentCities: cities,
      currentLoading: loading,
      initialized
    });
    
    if (!user) {
      console.log('[CityAccessContext] No user, clearing state');
      setCities([]);
      setIsAdmin(false);
      setLoading(false);
      setInitialized(true);
      setCacheSource('none');
      return;
    }

    const userId = user.id;

    // 🔒 JWT VALIDATION: Ensure token matches user context
    const jwtValid = await validateJWTTokenConsistency();
    if (!jwtValid) {
      console.error('[CityAccessContext] 🚨 JWT validation failed - forcing session refresh');
      setError('Session inconsistency detected. Please refresh the page.');
      setLoading(false);
      setInitialized(true);
      return;
    }

    // 🚀 ANTI-FLOODING: Advanced request deduplication
    if (!forceRefresh) {
      // If there's an active request for this user, wait for it instead of creating a new one
      if (activeRequestRef.current && lastUserIdRef.current === userId) {
        console.log('[CityAccessContext] 🔄 Active request detected, waiting for completion instead of creating duplicate');
        try {
          await activeRequestRef.current;
          return;
        } catch (error) {
          console.log('[CityAccessContext] Previous request failed, proceeding with new request');
        }
      }
      
      // Basic fetch guard
      if (fetchingRef.current && lastUserIdRef.current === userId) {
        console.log('[CityAccessContext] 🔄 Fetch already in progress, skipping duplicate call');
        return;
      }
    }

    // Check if we already have data for this user in memory (unless force refresh)
    if (!forceRefresh && memoryCacheRef.current && memoryCacheRef.current.userId === userId) {
      const age = Date.now() - memoryCacheRef.current.timestamp;
      if (age < CACHE_DURATION) {
        console.log('[CityAccessContext] Using memory cache, age:', Math.round(age / 1000), 'seconds');
        console.log('[CityAccessContext] Memory cache data:', memoryCacheRef.current);
        
        // Check if cached cities array is empty - if so, force refresh
        if (!memoryCacheRef.current.cities || memoryCacheRef.current.cities.length === 0) {
          console.log('[CityAccessContext] Memory cache has empty cities, forcing refresh');
          memoryCacheRef.current = null;
          // Continue to fetch fresh data instead of returning
        } else {
          setCities(memoryCacheRef.current.cities);
          setIsAdmin(memoryCacheRef.current.isAdmin);
          setLoading(false);
          setInitialized(true);
          setCacheSource('memory');
          setLastFetchTime(memoryCacheRef.current.timestamp);
          return;
        }
      }
    }

    // Create and track the active request to prevent duplication
    const fetchRequest = (async () => {
      fetchingRef.current = true;
      lastUserIdRef.current = userId;
      setLoading(true);
      setError(null);

      try {
        // Try session storage first (unless force refresh)
        if (!forceRefresh) {
          const cached = loadFromSessionStorage(userId, user?.tenant_id);
          if (cached) {
            setCities(cached.cities);
            setIsAdmin(cached.isAdmin);
            setLoading(false);
            setInitialized(true);
            setCacheSource('session');
            setLastFetchTime(cached.timestamp);
            memoryCacheRef.current = cached;
            return;
          }
        }

        // Fetch from API using our enhanced backend endpoint
        console.log('[CityAccessContext] 🔄 Fetching fresh data from enhanced API endpoint');
        
        if (cacheBypass) {
          console.log('🔥 CACHE BYPASS: Making fresh API call without any cache layers');
        }
        
        const result = await fetchCitiesFromAPI(user);
        
        if (result) {
          setCities(result.cities);
          setIsAdmin(result.isAdmin);
          setCacheSource('api');
          setLastFetchTime(Date.now());
          
          if (!cacheBypass) {
            saveToSessionStorage(userId, result.cities, result.isAdmin, user?.tenant_id);
          } else {
            console.log('🔥 CACHE BYPASS: Skipping cache save');
          }
        } else {
          throw new Error('Failed to fetch city access');
        }
      } catch (err: any) {
        console.error('[CityAccessContext] Error:', err);
        setError(err.message || 'Failed to load city access');
        
        // Use fallback for admins
        const userIsAdmin = ADMIN_EMAILS.includes(user.email || '') || 
                           user.app_metadata?.role === 'admin';
        
        if (userIsAdmin) {
          const fallbackCities = ['london', 'paris', 'algiers', 'lisbon'];
          setCities(fallbackCities);
          setIsAdmin(true);
          setCacheSource('none');
          console.log('[CityAccessContext] Applied admin fallback');
        } else {
          setCities([]);
          setIsAdmin(false);
          setCacheSource('none');
        }
      } finally {
        setLoading(false);
        setInitialized(true);
        fetchingRef.current = false;
        activeRequestRef.current = null;
      }
    })();
    
    // Track the active request
    activeRequestRef.current = fetchRequest;
    
    // Execute the request
    await fetchRequest;
  }, [user, loadFromSessionStorage, fetchCitiesFromAPI, saveToSessionStorage, validateJWTTokenConsistency]);

  /**
   * Check if user has access to a specific city
   */
  const hasAccessToCity = useCallback((city: string): boolean => {
    if (!city) return true; // Empty city means "all cities"
    if (isAdmin) return true; // Admins have access to all cities
    
    const normalizedCity = city.toLowerCase().trim();
    return cities.some(c => c.toLowerCase().trim() === normalizedCity);
  }, [cities, isAdmin]);

  /**
   * Force refresh cities from API
   */
  const refreshCities = useCallback(async () => {
    console.log('[CityAccessContext] Manual refresh requested');
    await fetchCityAccess(true);
  }, [fetchCityAccess]);

  /**
   * Clear all caches
   */
  const clearCache = useCallback(() => {
    if (user) {
      const cacheKey = getCacheKey(user.id, user.tenant_id);
      sessionStorage.removeItem(cacheKey);
      memoryCacheRef.current = null;
      
      // Also clear any old non-tenant-aware cache keys for security
      const oldKey = `${CACHE_KEY_PREFIX}_${user.id}`;
      if (sessionStorage.getItem(oldKey)) {
        sessionStorage.removeItem(oldKey);
        console.info('🔒 SECURITY: Cleared old non-tenant-aware session cache key');
      }
      
      console.log('[CityAccessContext] Cache cleared with tenant isolation');
    }
  }, [user, getCacheKey]);

  // 🔒 TENANT-AWARE: Enhanced auth event handling with tenant change detection
  const previousTenantRef = useRef<string | null>(null);
  
  useEffect(() => {
    // Subscribe to auth success event for immediate fetching
    const unsubscribeAuthSuccess = cityAccessEvents.onAuthSuccess((userId) => {
      console.log('🔒 TENANT_EVENT: Auth success event received, triggering immediate fetch');
      memoryCacheRef.current = null; // Clear memory cache
      if (user && user.id === userId) {
        fetchCityAccess(true); // Force refresh to ensure fresh tenant data
      }
    });
    
    // Subscribe to auth logout event
    const unsubscribeAuthLogout = cityAccessEvents.onAuthLogout(() => {
      console.log('🔒 TENANT_EVENT: Auth logout event received, clearing all data');
      clearCache();
      setCities([]);
      setIsAdmin(false);
      setCacheSource('none');
      previousTenantRef.current = null; // Reset tenant reference
    });
    
    return () => {
      unsubscribeAuthSuccess();
      unsubscribeAuthLogout();
    };
  }, [user, fetchCityAccess, clearCache]);

  useEffect(() => {
    const currentTenant = user?.tenant_id;
    const previousTenant = previousTenantRef.current;
    
    // Detect tenant changes
    if (previousTenant && currentTenant && previousTenant !== currentTenant) {
      console.warn(`🔒 TENANT_CHANGE_DETECTED: Switch from ${previousTenant} to ${currentTenant}`);
      
      // 🔒 MONITORING: Log detailed transition state
      logTenantState();
      
      // Immediately clear all caches
      memoryCacheRef.current = null;
      lastUserIdRef.current = null;
      
      // Clear session storage for both tenants to be safe
      if (user?.id) {
        const prevKey = getCacheKey(user.id, previousTenant);
        const currentKey = getCacheKey(user.id, currentTenant);
        sessionStorage.removeItem(prevKey);
        sessionStorage.removeItem(currentKey);
        console.info(`🔒 TENANT_CACHE_CLEAR: Cleared caches for tenant transition`);
        console.info(`🔒 TENANT_CACHE_KEYS: Removed ${prevKey} and ${currentKey}`);
      }
      
      // Force immediate refresh with new tenant context
      if (user?.id && currentTenant) {
        console.log(`🔒 TENANT_REFRESH: Forcing fresh fetch for tenant ${currentTenant}`);
        setTimeout(() => {
          fetchCityAccess(true); // Force refresh with slight delay to ensure auth context is stable
        }, 100);
      }
    }
    
    // Update previous tenant reference
    previousTenantRef.current = currentTenant || null;
  }, [user?.tenant_id, user?.id, fetchCityAccess, getCacheKey]);

  // 🔒 SESSION VALIDATION: Validate JWT token consistency on app load
  useEffect(() => {
    if (!authLoading && user) {
      // Delay validation slightly to ensure auth context is stable
      const validateSession = async () => {
        const isValid = await validateJWTTokenConsistency();
        if (!isValid) {
          console.error('[CityAccessContext] 🚨 Session validation failed on app load - potential JWT mismatch');
          setError('Session validation failed. Please refresh the page or sign in again.');
          return;
        }
        console.log('[CityAccessContext] ✅ Session validation passed on app load');
      };
      
      setTimeout(validateSession, 200);
    }
  }, [user, authLoading, validateJWTTokenConsistency]);

  // Main effect to fetch cities when user changes
  useEffect(() => {
    // Wait for auth to be ready
    if (authLoading) {
      return;
    }

    // If no user, clear everything
    if (!user) {
      setCities([]);
      setIsAdmin(false);
      setLoading(false);
      setInitialized(true);
      setCacheSource('none');
      memoryCacheRef.current = null;
      lastUserIdRef.current = null;
      
      // 🔒 SECURITY: Comprehensive cleanup of all tenant-related cache data
      const keysToRemove: string[] = [];
      for (let i = 0; i < sessionStorage.length; i++) {
        const key = sessionStorage.key(i);
        if (key && key.startsWith(CACHE_KEY_PREFIX)) {
          keysToRemove.push(key);
        }
      }
      keysToRemove.forEach(key => {
        sessionStorage.removeItem(key);
        console.info('🔒 SECURITY: Cleared session storage key on user logout:', key);
      });
      
      return;
    }

    // Extract tenant_id from user object
    const extractedTenantId = user.tenant_id || 
      user.user_metadata?.tenant_id || 
      user.app_metadata?.tenant_id || 
      null;
    
    if (!extractedTenantId) {
      console.warn('[CityAccessContext] Waiting for tenant_id extraction before fetching cities...', {
        userId: user.id,
        email: user.email,
        hasTenantId: !!user.tenant_id
      });
      return;
    }

    // Fetch city access using the centralized service with error handling
    let cancelled = false;
    
    (async () => {
      try {
        const cities = await cityAccessService.getCities({
          userId: user.id,
          tenantId: extractedTenantId,
          email: user.email || 'unknown'
        });
        
        // Don't update state if component unmounted
        if (cancelled) return;
        
        setCities(cities);
        setInitialized(true);
        setError(null);
        
        console.log('[CityAccessContext] Cities loaded successfully via CityAccessService', {
          count: cities.length,
          tenantId: extractedTenantId
        });
        
      } catch (error) {
        console.error('[CityAccessContext] Failed to fetch cities:', error);
        setError(error as Error);
        setCities([]);
        
        // User-facing error notifications
        if (error instanceof CityAccessError) {
          if (error.code === 'MISSING_TENANT') {
            toast.error('Cannot load cities. Please re-login.');
          } else if (error.code === 'NO_ACCESS') {
            toast.warning('No cities available. Contact your administrator.');
          } else if (error.code === 'NETWORK_ERROR') {
            toast.error('Network error. Please check your connection.');
          } else {
            toast.error('Failed to load cities. Please refresh the page.');
          }
        } else {
          toast.error('An unexpected error occurred while loading cities.');
        }
      }
    })();
    
    // Cleanup function
    return () => {
      cancelled = true;
    };
  }, [user, authLoading, validateJWTTokenConsistency]);

  // 🔄 TENANT SWITCH: Listen for tenant-switched events to clear cache
  useEffect(() => {
    const handleTenantSwitch = (event: Event) => {
      const customEvent = event as CustomEvent<{ oldTenantId?: string; newTenantId: string }>;
      console.log('[CityAccessContext] Tenant switch detected', customEvent.detail);
      
      // Clear local state
      setCities([]);
      setInitialized(false);
      setError(null);
      
      // Service cache is already cleared by secureCache.switchTenant()
      // Just need to trigger re-fetch when user/tenant updates
    };
    
    window.addEventListener('tenant-switched', handleTenantSwitch);
    return () => window.removeEventListener('tenant-switched', handleTenantSwitch);
  }, []);

  // 🔒 SESSION CLEANUP: Enhanced cleanup on sign out with memory leak prevention
  useEffect(() => {
    if (!user && lastUserIdRef.current) {
      clearCache();
      lastUserIdRef.current = null;
      
      // Cancel any pending requests
      if (activeRequestRef.current) {
        console.log('[CityAccessContext] 🔄 Cancelling pending request due to user sign out');
        activeRequestRef.current = null;
      }
      
      // Clear any pending timeouts
      if (requestTimeoutRef.current) {
        clearTimeout(requestTimeoutRef.current);
        requestTimeoutRef.current = null;
      }
      
      // Reset all refs for clean state
      memoryCacheRef.current = null;
      fetchingRef.current = false;
      previousTenantRef.current = null;
      
      console.log('[CityAccessContext] 🧹 Complete session cleanup completed');
    }
  }, [user, clearCache]);

  // 🔒 COMPONENT CLEANUP: Prevent memory leaks on unmount
  useEffect(() => {
    return () => {
      if (activeRequestRef.current) {
        activeRequestRef.current = null;
      }
      if (requestTimeoutRef.current) {
        clearTimeout(requestTimeoutRef.current);
      }
    };
  }, []);

  // 🔒 DEBUG: Add global debugging utilities in development
  useEffect(() => {
    if (import.meta.env.DEV) {
      (window as any).debugTenantState = () => {
        logTenantState();
        return {
          user: {
            id: user?.id,
            email: user?.email,
            tenant_id: user?.tenant_id
          },
          cities,
          loading,
          initialized,
          cacheSource,
          error
        };
      };
      
      (window as any).debugClearTenantCache = () => {
        clearCache();
        memoryCacheRef.current = null;
        lastUserIdRef.current = null;
        previousTenantRef.current = null;
        console.log('🔒 DEBUG: All tenant caches cleared');
      };
      
      (window as any).debugForceTenantRefresh = () => {
        console.log('🔒 DEBUG: Forcing tenant refresh');
        fetchCityAccess(true);
      };
      
      console.log('🔒 TENANT_DEBUG: Debugging utilities available:');
      console.log('- window.debugTenantState()');
      console.log('- window.debugClearTenantCache()');  
      console.log('- window.debugForceTenantRefresh()');
    }
  }, [logTenantState, clearCache, fetchCityAccess, user, cities, loading, initialized, cacheSource, error]);

  const value: CityAccessContextType = {
    cities,
    isAdmin,
    loading,
    error,
    initialized,
    lastFetchTime,
    cacheSource,
    hasAccessToCity,
    refreshCities,
    clearCache,
  };

  return (
    <CityAccessContext.Provider value={value}>
      {children}
    </CityAccessContext.Provider>
  );
}

// Hook to use city access context
export function useCityAccessContext() {
  const context = useContext(CityAccessContext);
  if (!context) {
    throw new Error('useCityAccessContext must be used within CityAccessProvider');
  }
  return context;
}

// Backward compatible hook that matches the old useCityAccess interface
export function useCityAccess() {
  const { cities, hasAccessToCity, loading, error, isAdmin } = useCityAccessContext();
  
  return {
    accessibleCities: cities,
    hasAccessToCity,
    loading,
    error,
    // Additional properties some components might expect
    isAdmin,
  };
}
