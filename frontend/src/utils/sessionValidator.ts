import { supabase } from '../lib/supabase';

export const validateSession = async (): Promise<any> => {
  try {
    // 1. Try standard Supabase getSession
    const { data: { session } } = await supabase.auth.getSession();
    
    if (session) {
      // Try refresh if session exists (on 401 recovery) – AuthResponse shape {session, user, error}
      const { session: refreshedSession, error: refreshError } = await supabase.auth.refreshSession();
      if (!refreshError && refreshedSession) {
        return refreshedSession;
      }
      return session;
    }

    // 2. Fallback to localStorage access_token for custom backend JWTs
    const storedToken = localStorage.getItem('access_token') || localStorage.getItem('token');
    if (storedToken) {
      try {
        // Verify token isn't corrupted
        if (storedToken.includes('.') && storedToken.split('.').length === 3) {
          const payload = JSON.parse(atob(storedToken.split('.')[1]));
          const now = Math.floor(Date.now() / 1000);
          
          if (!payload.exp || payload.exp > now) {
            return { access_token: storedToken, user: payload };
          }
        }
      } catch (e) {
        console.warn('[sessionValidator] Stored token parse failed:', e);
      }
    }

    return null;
  } catch (error) {
    console.error('[sessionValidator] Unexpected error:', error);
    return null;
  }
};

export const sessionValidator = {
  validateSession
};