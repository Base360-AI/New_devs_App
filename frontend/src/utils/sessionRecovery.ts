/**
 * Session Recovery Utility
 * 
 * Handles recovery of Supabase sessions from localStorage
 */

import { supabase } from '../lib/supabase';
import { Session } from '@supabase/supabase-js';

export class SessionRecovery {
  private static instance: SessionRecovery;
  private recoveryPromise: Promise<Session | null> | null = null;
  private recoveryStartTime: number | null = null;
  
  private constructor() {}
  
  static getInstance(): SessionRecovery {
    if (!SessionRecovery.instance) {
      SessionRecovery.instance = new SessionRecovery();
    }
    return SessionRecovery.instance;
  }
  
  /**
   * Attempts to recover a session from localStorage
   * This should be called on app initialization before any auth checks
   */
  async recoverSession(): Promise<Session | null> {
    if (typeof window !== 'undefined' && (window as any).__isLoggingOut) {
      console.log('[SessionRecovery] Skipping recovery - logout in progress');
      return null;
    }

    // If recovery is already in progress, check for timeout
    if (this.recoveryPromise) {
      const now = Date.now();
      // If recovery has been running for more than 10 seconds, reset it
      if (this.recoveryStartTime && now - this.recoveryStartTime > 10000) {
        console.log('[SessionRecovery] Recovery timeout - resetting');
        this.recoveryPromise = null;
        this.recoveryStartTime = null;
      } else {
        console.log('[SessionRecovery] Recovery already in progress, returning existing promise');
        return this.recoveryPromise;
      }
    }
    
    // Start new recovery
    this.recoveryStartTime = Date.now();
    
    // Create a new recovery promise with timeout
    this.recoveryPromise = Promise.race([
      this.performRecovery(),
      new Promise<null>((resolve) => {
        setTimeout(() => {
          console.log('[SessionRecovery] Recovery timeout after 10s');
          resolve(null);
        }, 10000);
      })
    ]);
    
    try {
      const result = await this.recoveryPromise;
      return result;
    } finally {
      // Clear the promise after completion
      this.recoveryPromise = null;
      this.recoveryStartTime = null;
    }
  }
  
  private async performRecovery(): Promise<Session | null> {
    
    try {
      console.log('[SessionRecovery] Attempting to recover session from storage...');
      
      // First, check if Supabase can get the session from storage
      const { data: { session }, error } = await supabase.auth.getSession();
      
      if (error) {
        console.error('[SessionRecovery] Error getting session:', error);
        return null;
      }
      
      if (session) {
        console.log('[SessionRecovery] Session recovered successfully');
        
        // Verify the session is valid
        const { data: { user }, error: userError } = await supabase.auth.getUser(session.access_token);
        
        if (userError || !user) {
          console.log('[SessionRecovery] Session invalid, attempting refresh...');
          
          // Try to refresh the session
          const { data: { session: refreshedSession }, error: refreshError } = 
            await supabase.auth.refreshSession();
          
          if (!refreshError && refreshedSession) {
            console.log('[SessionRecovery] Session refreshed successfully');
            return refreshedSession;
          } else {
            console.error('[SessionRecovery] Failed to refresh session:', refreshError);
            return null;
          }
        }
        
        return session;
      }
      
      // If no session found, check localStorage directly as a fallback
      console.log('[SessionRecovery] No session from getSession, checking localStorage directly...');
      
      const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || '';
      const storageKey = (supabaseUrl && supabaseUrl.includes('//')) 
        ? `sb-${supabaseUrl.split('//')[1].split('.')[0]}-auth-token` 
        : 'base360-auth-token';
      const storedData = localStorage.getItem(storageKey) || localStorage.getItem('access_token') || localStorage.getItem('base360-auth-token');
      
      if (storedData) {
        try {
          const parsed = JSON.parse(storedData);
          
          if (parsed?.currentSession?.refresh_token) {
            console.log('[SessionRecovery] Found refresh token in localStorage, attempting to restore...');
            
            const { data: { session: restoredSession }, error: restoreError } = 
              await supabase.auth.setSession({
                access_token: parsed.currentSession.access_token,
                refresh_token: parsed.currentSession.refresh_token
              });
            
            if (!restoreError && restoredSession) {
              console.log('[SessionRecovery] Session restored from localStorage');
              return restoredSession;
            } else {
              console.error('[SessionRecovery] Failed to restore session:', restoreError);
            }
          }
        } catch (e) {
          console.error('[SessionRecovery] Failed to parse stored session:', e);
        }
      }
      
      console.log('[SessionRecovery] No recoverable session found');
      return null;
    } catch (error) {
      console.error('[SessionRecovery] Recovery error:', error);
      return null;
    }
  }
  
  /**
   * Ensures a session is properly persisted to localStorage
   */
  async persistSession(session: Session): Promise<void> {
    try {
      console.log('[SessionRecovery] Persisting session to storage...');
      
      await supabase.auth.setSession({
        access_token: session.access_token,
        refresh_token: session.refresh_token
      });
      
      console.log('[SessionRecovery] Session persisted successfully');
    } catch (error) {
      console.error('[SessionRecovery] Failed to persist session:', error);
    }
  }
  
  /**
   * Clears any stored session data
   */
  clearStoredSession(): void {
    try {
      const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
      const storageKey = `sb-${supabaseUrl.split('//')[1].split('.')[0]}-auth-token`;
      localStorage.removeItem(storageKey);
      console.log('[SessionRecovery] Stored session cleared');
    } catch (error) {
      console.error('[SessionRecovery] Failed to clear stored session:', error);
    }
  }

  /**
   * Alias for recoverSession to maintain compatibility with AuthContext
   * Returns user object wrapped for compatibility with legacy code
   */
  async tryRecover(): Promise<{ user: any } | null> {
    if (typeof window !== 'undefined' && (window as any).__isLoggingOut) {
      console.log('[SessionRecovery] Skipping tryRecover - logout in progress');
      return null;
    }

    try {
      const session = await this.recoverSession();
      if (session && session.user) {
        return { user: session.user };
      }
      return null;
    } catch (error) {
      console.error('[SessionRecovery] tryRecover failed:', error);
      return null;
    }
  }
}

export const sessionRecovery = SessionRecovery.getInstance();