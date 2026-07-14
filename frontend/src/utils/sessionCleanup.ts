/**
 * Session cleanup utility to ensure proper user isolation
 */

import { supabase } from '../lib/supabase';

const getBackendBaseUrl = (): string => {
  if (import.meta.env.VITE_BACKEND_URL) {
    return import.meta.env.VITE_BACKEND_URL;
  }

  if (typeof window !== 'undefined') {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }

  return 'http://localhost:8000';
};

export async function ensureCleanSession() {
  /**
   * Force a clean session by:
   * 1. Getting current session
   * 2. Verifying it matches the logged-in user
   */
  
  try {
    const { data: { session }, error } = await supabase.auth.getSession();
    
    if (error) {
      console.error('[SessionCleanup] Error getting session:', error);
      return;
    }
    
    if (!session) {
      console.log('[SessionCleanup] No session found');
      return;
    }
    
    // Get the user from the session
    const sessionUser = session.user;
    
    // Verify the session is valid by checking with backend
    const response = await fetch(`${getBackendBaseUrl()}/api/v1/auth/me`, {
      headers: {
        'Authorization': `Bearer ${session.access_token}`
      }
    });
    
    if (!response.ok) {
      console.warn('[SessionCleanup] Session validation failed, clearing...');
      await supabase.auth.signOut();
      window.location.href = '/login';
      return;
    }
    
    const userData = await response.json();
    
    // Check if the session user matches the API response
    if (userData.email !== sessionUser.email) {
      console.error('[SessionCleanup] Session mismatch detected!');
      console.error(`Session user: ${sessionUser.email}, API user: ${userData.email}`);
      
      // Clear everything and force re-login
      await supabase.auth.signOut();
      localStorage.clear();
      sessionStorage.clear();
      
      // Clear IndexedDB
      if (window.indexedDB) {
        const databases = await indexedDB.databases();
        for (const db of databases) {
          if (db.name) {
            indexedDB.deleteDatabase(db.name);
          }
        }
      }
      
      window.location.href = '/login';
    } else {
      console.log(`[SessionCleanup] Session validated for user: ${sessionUser.email}`);
    }
    
  } catch (error) {
    console.error('[SessionCleanup] Error during session cleanup:', error);
  }
}

/**
 * Clear all authentication data for a clean slate
 */
export async function forceCleanLogout() {
  console.log('[SessionCleanup] Forcing clean logout...');
  
  // Sign out from Supabase
  await supabase.auth.signOut();
  
  // Clear all storage
  localStorage.clear();
  sessionStorage.clear();
  
  // Clear cookies
  document.cookie.split(";").forEach(function(c) { 
    document.cookie = c.replace(/^ +/, "").replace(/=.*/, "=;expires=" + new Date().toUTCString() + ";path=/"); 
  });
  
  // Clear IndexedDB
  if (window.indexedDB) {
    try {
      const databases = await indexedDB.databases();
      for (const db of databases) {
        if (db.name) {
          indexedDB.deleteDatabase(db.name);
        }
      }
    } catch (e) {
      console.error('[SessionCleanup] Error clearing IndexedDB:', e);
    }
  }
  
  // Redirect to login
  window.location.href = '/login';
}

/**
 * Monitor for session changes and ensure consistency
 */
export function setupSessionMonitor() {
  // Check session validity every 30 seconds
  setInterval(ensureCleanSession, 30000);
  
  // Also check on visibility change
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      ensureCleanSession();
    }
  });
  
  // Check on window focus
  window.addEventListener('focus', ensureCleanSession);
}