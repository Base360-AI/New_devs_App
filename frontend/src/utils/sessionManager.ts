/**
 * Enhanced Session Manager - Comprehensive session handling with isolation and cleanup
 * 
 * This module ensures proper session management across all authentication scenarios:
 * - Page refresh
 * - Token expiration  
 * - Network failures
 * - Concurrent requests
 * - Session isolation between different users/tenants
 * - Complete cleanup to prevent localStorage pollution
 * - Automatic corruption detection and recovery
 */

import { Session, User } from '@supabase/supabase-js';
import { supabase } from '../lib/supabase';
import { storageManager, STORAGE_KEYS } from './StorageManager';
import { storageHealthChecker } from './StorageHealthChecker';

export interface SessionValidation {
  isValid: boolean;
  session: Session | null;
  error?: string;
}

export interface SessionContext {
  user_id: string;
  tenant_id: string;
  email: string;
  session_id: string;
  login_timestamp: number;
  last_activity: number;
}

export interface SessionChangeEvent {
  type: 'login' | 'logout' | 'user_change' | 'tenant_change' | 'cleanup' | 'corruption_detected';
  previous_context?: SessionContext;
  new_context?: SessionContext;
  cleanup_performed: boolean;
  timestamp: number;
}

type SessionChangeListener = (event: SessionChangeEvent) => void | Promise<void>;

class SessionManager {
  private static instance: SessionManager;
  private sessionValidationPromise: Promise<SessionValidation> | null = null;
  private lastValidationTime: number = 0;
  private readonly VALIDATION_CACHE_DURATION = 300000; // 5 minutes (increased from 30 seconds)
  private readonly MAX_RETRY_ATTEMPTS = 5; // Increased for better resilience
  private readonly RETRY_DELAY_BASE = 1000; // Base delay in ms
  private isRefreshing = false;
  private refreshPromise: Promise<Session | null> | null = null;

  // Enhanced session isolation properties
  private currentContext: SessionContext | null = null;
  private sessionChangeListeners: Set<SessionChangeListener> = new Set();
  private sessionMonitorInterval: NodeJS.Timeout | null = null;
  private readonly SESSION_TIMEOUT = 24 * 60 * 60 * 1000; // 24 hours
  private readonly ACTIVITY_CHECK_INTERVAL = 5 * 60 * 1000; // 5 minutes
  private isCleanupInProgress = false;

  private constructor() {
    this.initializeSessionMonitoring();
    this.setupSupabaseAuthListener();
  }

  static getInstance(): SessionManager {
    if (!SessionManager.instance) {
      SessionManager.instance = new SessionManager();
    }
    return SessionManager.instance;
  }

  /**
   * Validates the current session with retry logic
   * Uses caching to prevent excessive validation calls
   */
  async validateSession(): Promise<SessionValidation> {
    // If we have a recent validation, return it
    if (
      this.sessionValidationPromise &&
      Date.now() - this.lastValidationTime < this.VALIDATION_CACHE_DURATION
    ) {
      console.log('[SessionManager] Using cached session validation');
      return this.sessionValidationPromise;
    }

    // Start new validation
    this.lastValidationTime = Date.now();
    this.sessionValidationPromise = this.performValidation();
    return this.sessionValidationPromise;
  }

  /**
   * Performs actual session validation with retry logic
   */
  private async performValidation(): Promise<SessionValidation> {
    let lastError: Error | null = null;

    for (let attempt = 1; attempt <= this.MAX_RETRY_ATTEMPTS; attempt++) {
      try {
        console.log(`[SessionManager] Validating session (attempt ${attempt}/${this.MAX_RETRY_ATTEMPTS})`);

        // Get current session
        const { data: { session }, error } = await supabase.auth.getSession();

        if (error) {
          throw error;
        }

        if (!session) {
          console.log('[SessionManager] No session found');
          return { isValid: false, session: null, error: 'No session found' };
        }

        // Check if token is expired or about to expire (within 1 minute)
        const expiresAt = session.expires_at;
        if (expiresAt) {
          const expiresIn = expiresAt * 1000 - Date.now();

          if (expiresIn < 60000) { // Less than 1 minute
            console.log('[SessionManager] Token expired or expiring soon, refreshing...');
            const refreshedSession = await this.refreshSession();
            if (refreshedSession) {
              return { isValid: true, session: refreshedSession };
            } else {
              return { isValid: false, session: null, error: 'Failed to refresh expired token' };
            }
          }
        }

        // Validate the session by checking if we can get user info
        const { data: { user }, error: userError } = await supabase.auth.getUser(session.access_token);

        if (userError || !user) {
          console.log('[SessionManager] Session validation failed, attempting refresh');
          const refreshedSession = await this.refreshSession();
          if (refreshedSession) {
            return { isValid: true, session: refreshedSession };
          } else {
            return { isValid: false, session: null, error: userError?.message || 'User validation failed' };
          }
        }

        console.log('[SessionManager] Session validated successfully');
        return { isValid: true, session };

      } catch (error) {
        lastError = error as Error;
        console.error(`[SessionManager] Validation attempt ${attempt} failed:`, error);

        if (attempt < this.MAX_RETRY_ATTEMPTS) {
          // Exponential backoff
          const delay = this.RETRY_DELAY_BASE * Math.pow(2, attempt - 1);
          console.log(`[SessionManager] Retrying in ${delay}ms...`);
          await new Promise(resolve => setTimeout(resolve, delay));
        }
      }
    }

    console.error('[SessionManager] All validation attempts failed');
    return {
      isValid: false,
      session: null,
      error: lastError?.message || 'Session validation failed after all retries'
    };
  }

  /**
   * Refreshes the session token
   * Uses a singleton pattern to prevent multiple simultaneous refresh attempts
   */
  async refreshSession(): Promise<Session | null> {
    // If already refreshing, wait for the existing refresh to complete
    if (this.isRefreshing && this.refreshPromise) {
      console.log('[SessionManager] Refresh already in progress, waiting...');
      return this.refreshPromise;
    }

    this.isRefreshing = true;
    this.refreshPromise = this.performRefresh();

    try {
      const result = await this.refreshPromise;
      return result;
    } finally {
      this.isRefreshing = false;
      this.refreshPromise = null;
    }
  }

  /**
   * Performs the actual token refresh
   */
  private async performRefresh(): Promise<Session | null> {
    try {
      console.log('[SessionManager] Refreshing session token...');
      const { data: { session }, error } = await supabase.auth.refreshSession();

      if (error) {
        console.error('[SessionManager] Token refresh failed:', error);

        // If refresh fails, try to re-authenticate with stored credentials if available
        // Get the correct storage key for Supabase v2
        const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
        const storageKey = `sb-${supabaseUrl.split('//')[1].split('.')[0]}-auth-token`;
        const storedSession = localStorage.getItem(storageKey);

        if (storedSession) {
          try {
            const parsed = JSON.parse(storedSession);
            if (parsed?.currentSession?.refresh_token) {
              console.log('[SessionManager] Attempting refresh with stored refresh token');
              const { data: { session: refreshedSession }, error: refreshError } =
                await supabase.auth.refreshSession({ refresh_token: parsed.currentSession.refresh_token });

              if (!refreshError && refreshedSession) {
                console.log('[SessionManager] Session refreshed with stored token');
                // Ensure the refreshed session is persisted
                await supabase.auth.setSession({
                  access_token: refreshedSession.access_token,
                  refresh_token: refreshedSession.refresh_token
                });
                return refreshedSession;
              }
            }
          } catch (e) {
            console.error('[SessionManager] Failed to use stored refresh token:', e);
          }
        }

        return null;
      }

      if (session) {
        console.log('[SessionManager] Session refreshed successfully');
        // This prevents loss of session on page refresh
        try {
          await supabase.auth.setSession({
            access_token: session.access_token,
            refresh_token: session.refresh_token
          });
          console.log('[SessionManager] Refreshed session persisted to storage');
        } catch (persistError) {
          console.error('[SessionManager] Failed to persist refreshed session:', persistError);
        }

        // Clear the validation cache to force revalidation with new session
        this.sessionValidationPromise = null;
        this.lastValidationTime = 0;
      }

      return session;
    } catch (error) {
      console.error('[SessionManager] Unexpected error during refresh:', error);
      return null;
    }
  }

  /**
   * Ensures we have a valid session before making API calls
   * This is the main method components should use
   */
  async ensureValidSession(): Promise<Session | null> {
    const validation = await this.validateSession();

    if (!validation.isValid) {
      console.log('[SessionManager] Session invalid, attempting to recover...');

      // Try to refresh one more time
      const refreshedSession = await this.refreshSession();
      if (refreshedSession) {
        return refreshedSession;
      }

      // If all else fails, clear everything and force re-login
      console.log('[SessionManager] Unable to recover session, clearing auth state');
      await this.clearAuthState();
      return null;
    }

    return validation.session;
  }

  /**
   * Initialize session from current Supabase auth state with isolation checks
   */
  async initializeSession(): Promise<SessionContext | null> {
    console.log('[SessionManager] Initializing session with isolation checks...');

    try {
      // Check for existing corruption first
      if (await this.detectSessionCorruption()) {
        console.warn('[SessionManager] Session corruption detected, performing cleanup');
        await this.performEmergencyCleanup();
        return null;
      }

      const { data: { session } } = await supabase.auth.getSession();

      if (!session || !session.user) {
        console.log('[SessionManager] No active session found');
        await this.clearSessionComplete();
        return null;
      }

      const newContext = await this.createSessionContext(session);

      // Check if this is a different user than what we had before
      const previousContext = this.currentContext;
      if (previousContext && previousContext.user_id !== newContext.user_id) {
        console.log('[SessionManager] User change detected, cleaning previous session');
        await this.handleUserChange(previousContext, newContext);
      } else if (previousContext && previousContext.tenant_id !== newContext.tenant_id) {
        console.log('[SessionManager] Tenant change detected, cleaning previous session');
        await this.handleTenantChange(previousContext, newContext);
      } else {
        // Same user, just update context
        await this.setSessionContext(newContext);
      }

      return this.currentContext;

    } catch (error) {
      console.error('[SessionManager] Failed to initialize session:', error);
      await this.performEmergencyCleanup();
      return null;
    }
  }

  /**
   * Set current session context with storage isolation
   */
  async setSessionContext(context: SessionContext): Promise<void> {
    console.log('[SessionManager] Setting session context:', {
      user_id: context.user_id,
      tenant_id: context.tenant_id,
      email: context.email,
      session_id: context.session_id
    });

    const previousContext = this.currentContext;
    this.currentContext = context;

    // Update storage manager context
    storageManager.setContext({
      user_id: context.user_id,
      tenant_id: context.tenant_id,
      email: context.email
    });

    // Store session context securely
    storageManager.set(STORAGE_KEYS.SESSION_METADATA, context, {
      skipIntegrityCheck: false,
      ttl: this.SESSION_TIMEOUT
    });

    // Notify listeners
    await this.notifySessionChange({
      type: previousContext ? 'user_change' : 'login',
      previous_context: previousContext || undefined,
      new_context: context,
      cleanup_performed: false,
      timestamp: Date.now()
    });

    console.log('[SessionManager] Session context set successfully');
  }

  /**
   * Clear current session and perform complete cleanup
   */
  async clearSessionComplete(): Promise<void> {
    if (this.isCleanupInProgress) {
      console.log('[SessionManager] Cleanup already in progress, waiting...');
      return;
    }

    this.isCleanupInProgress = true;

    try {
      console.log('[SessionManager] Starting complete session cleanup...');

      const previousContext = this.currentContext;
      this.currentContext = null;

      // Clear storage manager context
      storageManager.clearContext();

      // Perform comprehensive cleanup
      await this.performComprehensiveCleanup();

      // Notify listeners
      await this.notifySessionChange({
        type: 'logout',
        previous_context: previousContext || undefined,
        new_context: undefined,
        cleanup_performed: true,
        timestamp: Date.now()
      });

      console.log('[SessionManager] Complete session cleanup finished');

    } finally {
      this.isCleanupInProgress = false;
    }
  }

  /**
   * Handle user change (different user logging in)
   */
  private async handleUserChange(previousContext: SessionContext, newContext: SessionContext): Promise<void> {
    console.log('[SessionManager] Handling user change:', {
      previous_user: previousContext.email,
      new_user: newContext.email
    });

    // Clear all data for previous user
    await this.performUserSpecificCleanup(previousContext);

    // Set new session
    await this.setSessionContext(newContext);

    // Notify listeners
    await this.notifySessionChange({
      type: 'user_change',
      previous_context: previousContext,
      new_context: newContext,
      cleanup_performed: true,
      timestamp: Date.now()
    });
  }

  /**
   * Handle tenant change (same user, different tenant)
   */
  private async handleTenantChange(previousContext: SessionContext, newContext: SessionContext): Promise<void> {
    console.log('[SessionManager] Handling tenant change:', {
      user: newContext.email,
      previous_tenant: previousContext.tenant_id,
      new_tenant: newContext.tenant_id
    });

    // Clear tenant-specific data but preserve user data
    await this.performTenantSpecificCleanup(previousContext);

    // Set new session
    await this.setSessionContext(newContext);

    // Notify listeners
    await this.notifySessionChange({
      type: 'tenant_change',
      previous_context: previousContext,
      new_context: newContext,
      cleanup_performed: true,
      timestamp: Date.now()
    });
  }

  /**
   * Perform comprehensive cleanup (logout or corruption)
   */
  private async performComprehensiveCleanup(): Promise<void> {
    console.log('[SessionManager] Performing comprehensive cleanup...');

    try {
      // 1. Clear all user data from storage
      if (this.currentContext) {
        storageManager.clearUserData(this.currentContext);
      }

      // 2. Clear legacy storage items
      await this.clearLegacyStorage();

      // 3. Run health check to clean up any remaining issues
      await storageHealthChecker.performHealthCheck({ autoFix: true });

      // 4. Clear existing auth state using the original method
      await this.clearAuthState();

      console.log('[SessionManager] Comprehensive cleanup completed');

    } catch (error) {
      console.error('[SessionManager] Error during comprehensive cleanup:', error);
    }
  }

  /**
   * Perform user-specific cleanup (when switching users)
   */
  private async performUserSpecificCleanup(context: SessionContext): Promise<void> {
    console.log('[SessionManager] Performing user-specific cleanup for:', context.email);

    try {
      // Clear all storage for this specific user
      storageManager.clearUserData(context);

      console.log('[SessionManager] User-specific cleanup completed');

    } catch (error) {
      console.error('[SessionManager] Error during user-specific cleanup:', error);
    }
  }

  /**
   * Perform tenant-specific cleanup (when switching tenants)
   */
  private async performTenantSpecificCleanup(context: SessionContext): Promise<void> {
    console.log('[SessionManager] Performing tenant-specific cleanup for tenant:', context.tenant_id);

    try {
      // Clear tenant-specific cached data
      const tenantSpecificKeys = [
        STORAGE_KEYS.CITY_ACCESS,
        STORAGE_KEYS.BOOTSTRAP_DATA,
        STORAGE_KEYS.PERMISSIONS_CACHE
      ];

      for (const key of tenantSpecificKeys) {
        storageManager.remove(key, {
          context: { tenant_id: context.tenant_id, user_id: context.user_id }
        });
      }

      console.log('[SessionManager] Tenant-specific cleanup completed');

    } catch (error) {
      console.error('[SessionManager] Error during tenant-specific cleanup:', error);
    }
  }

  /**
   */
  private async clearLegacyStorage(): Promise<void> {
    const legacyPatterns = [
      'city_access_cache',
      'bootstrap_cache',
      'auth_cache',
      'user_context'
    ];

    for (let i = localStorage.length - 1; i >= 0; i--) {
      const key = localStorage.key(i);
      if (!key) continue;

      const shouldRemove = legacyPatterns.some(pattern =>
        key.includes(pattern) || key.startsWith(pattern)
      );

      if (shouldRemove) {
        try {
          localStorage.removeItem(key);
        } catch (error) {
          console.warn('[SessionManager] Failed to remove legacy key:', key, error);
        }
      }
    }

    console.log('[SessionManager] Legacy storage cleared');
  }

  /**
   * Detect session corruption
   */
  private async detectSessionCorruption(): Promise<boolean> {
    try {
      // Check for obvious signs of corruption

      // 1. Multiple session contexts
      const sessionKeys = [];
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key && key.includes(STORAGE_KEYS.SESSION_METADATA)) {
          sessionKeys.push(key);
        }
      }

      if (sessionKeys.length > 3) { // Allow some namespaced variations
        console.warn('[SessionManager] Multiple session contexts detected');
        return true;
      }

      // 2. Check for conflicting user contexts
      const { data: { session } } = await supabase.auth.getSession();
      if (session && this.currentContext) {
        if (session.user.id !== this.currentContext.user_id) {
          console.warn('[SessionManager] Session user mismatch detected');
          return true;
        }
      }

      // 3. Check storage health
      const healthReport = await storageHealthChecker.performHealthCheck();
      if (healthReport.overall_health === 'critical' || healthReport.overall_health === 'corrupted') {
        console.warn('[SessionManager] Storage corruption detected by health checker');
        return true;
      }

      return false;

    } catch (error) {
      console.error('[SessionManager] Error detecting corruption:', error);
      return true; // Assume corruption if we can't check
    }
  }

  /**
   */
  private async performEmergencyCleanup(): Promise<void> {
    console.log('[SessionManager] Performing emergency cleanup...');

    try {
      // Nuclear option: clear all localStorage via StorageManager
      storageManager.clearAll();

      // Clear any residual Supabase state
      await this.clearAuthState();

      // Notify listeners of cleanup
      await this.notifySessionChange({
        type: 'cleanup',
        previous_context: this.currentContext || undefined,
        new_context: undefined,
        cleanup_performed: true,
        timestamp: Date.now()
      });

      this.currentContext = null;

      console.log('[SessionManager] Emergency cleanup completed');

    } catch (error) {
      console.error('[SessionManager] Emergency cleanup failed:', error);
    }
  }

  /**
   * Create session context from Supabase session
   */
  private async createSessionContext(session: Session): Promise<SessionContext> {
    const user = session.user;

    // Extract tenant_id from JWT claims or metadata
    let tenant_id = '';

    try {
      // Try JWT claims first
      if (session.access_token && session.access_token.includes('.') && session.access_token.split('.').length === 3) {
        const payload = JSON.parse(atob(session.access_token.split('.')[1]));
        tenant_id = payload.tenant_id || '';
      }
    } catch (error) {
      // Fallback to metadata
      tenant_id = user.app_metadata?.tenant_id || user.user_metadata?.tenant_id || '';
    }

    return {
      user_id: user.id,
      tenant_id,
      email: user.email || '',
      session_id: `session_${user.id}_${Date.now()}`,
      login_timestamp: Date.now(),
      last_activity: Date.now()
    };
  }

  /**
   * Setup Supabase auth state change listener
   */
  private setupSupabaseAuthListener(): void {
    supabase.auth.onAuthStateChange(async (event, session) => {
      console.log('[SessionManager] Supabase auth state changed:', event);

      switch (event) {
        case 'SIGNED_IN':
          if (session) {
            const newContext = await this.createSessionContext(session);
            await this.setSessionContext(newContext);
          }
          break;

        case 'SIGNED_OUT':
          await this.clearSessionComplete();
          break;

        case 'TOKEN_REFRESHED':
          if (session && this.currentContext) {
            // Update activity timestamp
            this.currentContext.last_activity = Date.now();
          }
          break;
      }
    });
  }

  /**
   * Initialize session monitoring
   */
  private initializeSessionMonitoring(): void {
    this.sessionMonitorInterval = setInterval(async () => {
      if (this.currentContext) {
        const now = Date.now();
        const inactiveTime = now - this.currentContext.last_activity;

        if (inactiveTime > this.SESSION_TIMEOUT) {
          console.log('[SessionManager] Session timeout detected, clearing session');
          await this.clearSessionComplete();
        }
      }
    }, this.ACTIVITY_CHECK_INTERVAL);
  }

  /**
   * Update last activity timestamp
   */
  updateActivity(): void {
    if (this.currentContext) {
      this.currentContext.last_activity = Date.now();
    }
  }

  /**
   * Add session change listener
   */
  addSessionChangeListener(listener: SessionChangeListener): void {
    this.sessionChangeListeners.add(listener);
  }

  /**
   * Remove session change listener
   */
  removeSessionChangeListener(listener: SessionChangeListener): void {
    this.sessionChangeListeners.delete(listener);
  }

  /**
   * Notify all session change listeners
   */
  private async notifySessionChange(event: SessionChangeEvent): Promise<void> {
    const promises = Array.from(this.sessionChangeListeners).map(async listener => {
      try {
        await listener(event);
      } catch (error) {
        console.error('[SessionManager] Session change listener error:', error);
      }
    });

    await Promise.all(promises);
  }

  /**
   * Get current session context
   */
  getCurrentContext(): SessionContext | null {
    return this.currentContext;
  }

  /**
   * Check if user is currently logged in with valid context
   */
  isLoggedInWithContext(): boolean {
    return this.currentContext !== null;
  }

  /**
   * Clears all authentication state (original method enhanced)
   */
  async clearAuthState(): Promise<void> {
    console.log('[SessionManager] Clearing all authentication state');

    // Clear Supabase session
    try {
      await supabase.auth.signOut();
    } catch (error) {
      console.error('[SessionManager] Error during signOut:', error);
    }

    // Clear all auth-related localStorage items
    const keysToRemove: string[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && (
        key.includes('supabase') ||
        key.includes('auth') ||
        key.includes('token') ||
        key.includes('session')
      )) {
        keysToRemove.push(key);
      }
    }

    keysToRemove.forEach(key => {
      localStorage.removeItem(key);
      console.log('[SessionManager] Removed auth key:', key);
    });

    // Clear session storage
    sessionStorage.clear();

    // Reset internal state
    this.sessionValidationPromise = null;
    this.lastValidationTime = 0;
    this.isRefreshing = false;
    this.refreshPromise = null;
  }

  /**
   * Gets the current session without validation
   * Use this only when you need quick access and can handle invalid sessions
   */
  async getCurrentSession(): Promise<Session | null> {
    try {
      const { data: { session } } = await supabase.auth.getSession();
      return session;
    } catch (error) {
      console.error('[SessionManager] Error getting current session:', error);
      return null;
    }
  }

  /**
   * Checks if we have any session (valid or not)
   */
  async hasSession(): Promise<boolean> {
    const session = await this.getCurrentSession();
    return session !== null;
  }

  /**
   * Force invalidates the validation cache
   */
  invalidateCache(): void {
    console.log('[SessionManager] Invalidating session validation cache');
    this.sessionValidationPromise = null;
    this.lastValidationTime = 0;
  }
}

// Export singleton instance
export const sessionManager = SessionManager.getInstance();
