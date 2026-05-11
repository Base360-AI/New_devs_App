import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { User, Session } from '@supabase/supabase-js';
import { supabase } from '../lib/supabase';
import { authOptimizer } from '../utils/authOptimizer';
import { sessionRecovery } from '../utils/sessionRecovery';
import { sessionPersistenceManager } from '../utils/SessionPersistenceManager';
import { extractTenantFromSession } from '../utils/jwtUtils';

// Global logout flag to prevent session recovery during logout
if (typeof window !== 'undefined') {
  (window as any).__isLoggingOut = false;
}

// Enhanced user type that includes tenant_id for compatibility
interface EnhancedUser extends User {
  tenant_id?: string;
}

interface AuthContextType {
  user: EnhancedUser | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  getAccessToken: () => Promise<string | null>;
  signIn: (email: string, password: string) => Promise<{ error: Error | null }>;
  signOut: () => Promise<void>;
  refreshSession: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<EnhancedUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  // Helper function to enrich user object with tenant_id from JWT claims and metadata  
  const enrichUserWithTenant = useCallback((session: Session): EnhancedUser => {
    const enhancedUser = session.user as EnhancedUser;

    // Extract tenant_id with priority: JWT claims > app_metadata > user_metadata
    let tenant_id: string | null = null;
    let source = 'none';

    // 1. First try JWT claims (added by custom_access_token_hook)
    const jwtTenantId = extractTenantFromSession(session);
    if (jwtTenantId) {
      tenant_id = jwtTenantId;
      source = 'jwt_claims';
    }

    // 2. Fallback to app_metadata  
    if (!tenant_id && enhancedUser.app_metadata?.tenant_id) {
      tenant_id = enhancedUser.app_metadata.tenant_id;
      source = 'app_metadata';
    }

    // 3. Fallback to user_metadata
    if (!tenant_id && enhancedUser.user_metadata?.tenant_id) {
      tenant_id = enhancedUser.user_metadata.tenant_id;
      source = 'user_metadata';
    }

    // 4. Fallback to existing top-level tenant_id on the user object
    //    (local backend returns it there)
    if (!tenant_id && enhancedUser.tenant_id) {
      tenant_id = enhancedUser.tenant_id;
      source = 'top_level';
    }

    // Add tenant_id as a direct property for backward compatibility
    enhancedUser.tenant_id = tenant_id;

    if (import.meta.env.DEV) {
      console.log('🔒 TENANT_RESOLUTION: Enhanced user object', {
        userId: enhancedUser.id,
        email: enhancedUser.email,
        tenant_id,
        source,
        jwt_tenant: jwtTenantId,
        app_metadata_tenant: enhancedUser.app_metadata?.tenant_id,
        user_metadata_tenant: enhancedUser.user_metadata?.tenant_id
      });
    }

    return enhancedUser;
  }, []);

  // Fallback function for cases where we only have user object (like session recovery)
  const enrichUserFallback = useCallback((user: User): EnhancedUser => {
    const enhancedUser = user as EnhancedUser;

    // Extract tenant_id from metadata only (no JWT claims available)
    let tenant_id: string | null = null;
    let source = 'none';

    // Try app_metadata first
    if (enhancedUser.app_metadata?.tenant_id) {
      tenant_id = enhancedUser.app_metadata.tenant_id;
      source = 'app_metadata';
    }
    // Fallback to user_metadata
    else if (enhancedUser.user_metadata?.tenant_id) {
      tenant_id = enhancedUser.user_metadata.tenant_id;
      source = 'user_metadata';
    }

    // Add tenant_id as a direct property for backward compatibility
    enhancedUser.tenant_id = tenant_id;

    if (import.meta.env.DEV) {
      console.log('🔒 TENANT_RESOLUTION (fallback): User object without session', {
        userId: enhancedUser.id,
        email: enhancedUser.email,
        tenant_id,
        source,
        app_metadata_tenant: enhancedUser.app_metadata?.tenant_id,
        user_metadata_tenant: enhancedUser.user_metadata?.tenant_id
      });
    }

    return enhancedUser;
  }, []);

  const refreshSession = useCallback(async () => {
    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (session) {
        const enrichedUser = enrichUserWithTenant(session);
        setUser(enrichedUser);
        setIsAuthenticated(true);
      } else {
        setUser(null);
        setIsAuthenticated(false);
      }
    } catch (error) {
      console.error('Error refreshing session:', error);
      setUser(null);
      setIsAuthenticated(false);
    }
  }, [enrichUserWithTenant]);

  const getAccessToken = useCallback(async (): Promise<string | null> => {
    try {
      const { data: { session } } = await supabase.auth.getSession();
      return session?.access_token ?? null;
    } catch {
      return null;
    }
  }, []);

  useEffect(() => {
    console.log('🔍 [AuthContext] Provider MOUNTED via useEffect');
    let mounted = true;

    // Initialize state
    const initAuth = async () => {
      try {
        // Skip initialization if logout is in progress
        if ((window as any).__isLoggingOut) {
          console.log('[AuthContext] Skipping auth initialization - logout in progress');
          setIsLoading(false);
          return;
        }

        // Try to get session from Supabase first
        const { data: { session } } = await supabase.auth.getSession();

        if (session) {
          const enrichedUser = enrichUserWithTenant(session);
          setUser(enrichedUser);
          setIsAuthenticated(true);
        } else {
          // Try session recovery if no session (and not logging out)
          if (!(window as any).__isLoggingOut) {
            const recovered = await sessionRecovery.tryRecover();
            if (recovered) {
              const enrichedUser = enrichUserFallback(recovered.user);
              setUser(enrichedUser);
              setIsAuthenticated(true);
            }
          }
        }
      } catch (error) {
        console.error('Error initializing auth:', error);
      } finally {
        setIsLoading(false);
      }
    };

    initAuth();

    // Start session persistence monitoring for robust recovery
    sessionPersistenceManager.start();

    // Listen for session expiry events from SessionPersistenceManager
    const handleSessionExpired = (event: Event) => {
      const customEvent = event as CustomEvent;
      console.error('[AuthContext] Session expired and could not be recovered:', customEvent.detail);
      // Force logout
      setUser(null);
      setIsAuthenticated(false);
    };
    window.addEventListener('session-expired', handleSessionExpired);

    // Set up auth state change listener
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      console.log('🔍 [AuthContext] Auth state changed EVENT:', event);
      console.log('🔍 [AuthContext] Session present:', !!session);

      try {
        if (session) {
          console.log('🔍 [AuthContext] Session User Email:', session.user.email);
          const enrichedUser = enrichUserWithTenant(session);
          console.log('🔍 [AuthContext] Enriched User:', enrichedUser ? 'SUCCESS' : 'NULL');
          setUser(enrichedUser);
          setIsAuthenticated(true);
          // Store session for recovery
          authOptimizer.storeSession(session);
        } else {
          console.log('🔍 [AuthContext] Session is NULL -> Logging out');
          setUser(null);
          setIsAuthenticated(false);
          authOptimizer.clearSession();
        }
      } catch (error) {
        console.error('❌ [AuthContext] CRITICAL ERROR in auth state change handler:', error);
      }
      setIsLoading(false);
    });

    return () => {
      subscription.unsubscribe();
      sessionPersistenceManager.stop();
      window.removeEventListener('session-expired', handleSessionExpired);
    };
  }, [enrichUserWithTenant]);

  const signIn = async (email: string, password: string) => {
    try {
      const { data, error } = await supabase.auth.signInWithPassword({
        email,
        password,
      });

      if (error) {
        return { error };
      }

      if (data.session) {
        const enrichedUser = enrichUserWithTenant(data.session);
        setUser(enrichedUser);
        setIsAuthenticated(true);
        authOptimizer.storeSession(data.session);

        // Restart session persistence manager after successful login
        sessionPersistenceManager.start();
        console.log('[AuthContext] Session persistence manager restarted after login');
      }

      return { error: null };
    } catch (error) {
      return { error: error as Error };
    }
  };

  const signOut = async () => {
    try {
      console.log('[AuthContext] Starting logout process');

      // 0. SET LOGOUT FLAG FIRST - prevents ALL session recovery attempts
      (window as any).__isLoggingOut = true;
      console.log('[AuthContext] Logout flag set - blocking all session recovery');

      // 1. Clear storage IMMEDIATELY before anything else
      localStorage.clear();
      sessionStorage.clear();
      console.log('[AuthContext] Storage cleared');

      // 2. Stop session persistence manager
      sessionPersistenceManager.stop();
      console.log('[AuthContext] Session persistence manager stopped');

      // 3. Clear all session recovery data
      sessionRecovery.clearStoredSession();
      authOptimizer.clearSession();
      console.log('[AuthContext] Session recovery cleared');

      // 4. Sign out from Supabase
      await supabase.auth.signOut();
      console.log('[AuthContext] Supabase sign out completed');

      // 5. Update local state
      setUser(null);
      setIsAuthenticated(false);

      console.log('[AuthContext] Logout completed successfully');

      // 6. Redirect to login page immediately
      setTimeout(() => {
        // Clear flag AFTER redirect starts
        (window as any).__isLoggingOut = false;
        window.location.href = '/login';
      }, 100);

    } catch (error) {
      console.error('[AuthContext] Error during logout:', error);

      // Even on error, ensure everything is cleared
      try {
        localStorage.clear();
        sessionStorage.clear();
        sessionPersistenceManager.stop();
        sessionRecovery.clearStoredSession();
        authOptimizer.clearSession();
      } catch (e) {
        console.error('[AuthContext] Error clearing sessions:', e);
      }

      setUser(null);
      setIsAuthenticated(false);

      // Force redirect even on error
      setTimeout(() => {
        (window as any).__isLoggingOut = false;
        window.location.href = '/login';
      }, 100);
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated,
        signIn,
        signOut,
        refreshSession,
        getAccessToken,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};