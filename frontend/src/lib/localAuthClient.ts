// Local authentication client to replace Supabase
interface AuthUser {
  id: string;
  email: string;
  name?: string;
  is_admin?: boolean;
  tenant_id?: string;
  app_metadata?: any;
  user_metadata?: any;
  created_at?: string;
}

interface AuthSession {
  access_token: string;
  refresh_token?: string;
  user: AuthUser;
  token_type: string;
  expires_in?: number;
}

interface AuthResponse {
  user: AuthUser | null;
  session: AuthSession | null;
  error: Error | null;
}

interface SignInCredentials {
  email: string;
  password: string;
}

class LocalAuthClient {
  private subscribers: ((event: string, session: AuthSession | null) => void)[] = [];
  private session: AuthSession | null = null;
  private storageKey = 'base360-auth-token';

  constructor() {
    this.loadSession();
  }

  private getApiUrl(): string {
    return import.meta.env.VITE_API_URL || import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';
  }

  private notifySubscribers(event: string, session: AuthSession | null) {
    console.log(`📣 [LocalAuth] Notifying ${this.subscribers.length} subscribers of event: ${event}`);
    this.subscribers.forEach((callback) => {
      try {
        callback(event, session);
      } catch (e) {
        console.error('📣 [LocalAuth] Error in subscriber callback:', e);
      }
    });
  }

  private saveSession(session: AuthSession | null) {
    this.session = session;
    if (session) {
      localStorage.setItem(this.storageKey, JSON.stringify(session));
      this.notifySubscribers('SIGNED_IN', session);
    } else {
      localStorage.removeItem(this.storageKey);
      this.notifySubscribers('SIGNED_OUT', null);
    }
  }

  private loadSession() {
    try {
      const stored = localStorage.getItem(this.storageKey);
      if (stored) {
        this.session = JSON.parse(stored);
      }
    } catch (error) {
      console.warn('[LocalAuth] Failed to load session from storage:', error);
      localStorage.removeItem(this.storageKey);
    }
  }

  async signInWithPassword(credentials: SignInCredentials): Promise<AuthResponse> {
    try {
      const response = await fetch(`${this.getApiUrl()}/api/v1/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(credentials),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || data.error || `HTTP ${response.status}`);
      }

      if (data.error) {
        throw new Error(data.error);
      }

      const session: AuthSession = {
        access_token: data.access_token,
        token_type: data.token_type || 'bearer',
        user: data.user,
      };

      this.saveSession(session);

      return {
        user: data.user,
        session: session,
        error: null,
      };
    } catch (error: any) {
      console.error('[LocalAuth] Sign in failed:', error);
      return {
        user: null,
        session: null,
        error: error,
      };
    }
  }

  async signOut(): Promise<{ error: Error | null }> {
    try {
      // Call backend logout endpoint if needed
      if (this.session?.access_token) {
        try {
          await fetch(`${this.getApiUrl()}/api/v1/auth/logout`, {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${this.session.access_token}`,
            },
          });
        } catch (logoutError) {
          console.warn('[LocalAuth] Backend logout failed (continuing):', logoutError);
        }
      }

      this.saveSession(null);

      return { error: null };
    } catch (error: any) {
      console.error('[LocalAuth] Sign out failed:', error);
      return { error: error };
    }
  }

  async getSession(): Promise<{ data: { session: AuthSession | null } }> {
    if (!this.session?.access_token) {
      this.loadSession();
    }
    return { data: { session: this.session } };
  }

  async getUser(token?: string): Promise<{ user: AuthUser | null }> {
    const tokenToUse = token || this.session?.access_token;

    if (!tokenToUse) {
      return { user: null };
    }

    try {
      const response = await fetch(`${this.getApiUrl()}/api/v1/auth/me`, {
        headers: {
          'Authorization': `Bearer ${tokenToUse}`,
        },
      });

      if (response.ok) {
        const userData = await response.json();
        return { user: userData };
      } else {
        return { user: null };
      }
    } catch (error) {
      console.error('[LocalAuth] Get user failed:', error);
      return { user: null };
    }
  }

  async setSession(session: AuthSession): Promise<{ error: Error | null }> {
    try {
      this.saveSession(session);
      return { error: null };
    } catch (error: any) {
      return { error: error };
    }
  }

  private refreshPromise: Promise<AuthResponse> | null = null;

  async refreshSession(): Promise<AuthResponse> {
    if (!this.session?.access_token) {
      this.loadSession();
    }

    // Deduplicate concurrent refreshes – backend exp (60s) drives expiry
    if (this.refreshPromise) {
      console.log('[LocalAuth] Session refresh already in-flight, reusing promise');
      return this.refreshPromise;
    }

    this.refreshPromise = (async (): Promise<AuthResponse> => {
      try {
        if (!this.session?.access_token) {
          return {
            user: null,
            session: null,
            error: new Error('No session to refresh'),
          };
        }

        const response = await fetch(`${this.getApiUrl()}/api/v1/auth/refresh-session`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${this.session.access_token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            session_id: `session-${this.session.user.id}`,
            user_id: this.session.user.id,
            device_id: 'default-device',
          }),
        });

        if (response.ok) {
          const data = await response.json();
          const newAccessToken = data.access_token || this.session.access_token;
          const updatedSession: AuthSession = {
            ...this.session,
            access_token: newAccessToken,
          };

          this.saveSession(updatedSession);
          console.log('✅ [LocalAuth] Session refreshed successfully');

          return {
            user: updatedSession.user,
            session: updatedSession,
            error: null,
          };
        } else if (response.status === 401) {
          // Explicit 401 Unauthorized -> Token revoked or invalid -> Log out user
          console.warn('[LocalAuth] Token explicitly revoked by server (401), logging out');
          this.saveSession(null);
          return {
            user: null,
            session: null,
            error: new Error('Session expired'),
          };
        } else {
          // 500 or temporary server error -> Preserve existing session
          console.warn(`[LocalAuth] Server error ${response.status} during refresh, preserving session`);
          return {
            user: this.session.user,
            session: this.session,
            error: null,
          };
        }
      } catch (error: any) {
        // Network error / offline -> Preserve existing session
        console.warn('[LocalAuth] Network glitch during refreshSession, preserving session:', error);
        return {
          user: this.session?.user || null,
          session: this.session,
          error,
        };
      }
    })().finally(() => {
      this.refreshPromise = null;
    });

    return this.refreshPromise;
  }


  // Mock auth state change handler for compatibility
  onAuthStateChange(callback: (event: string, session: AuthSession | null) => void) {
    // Register subscriber
    this.subscribers.push(callback);

    // Call immediately with current state
    callback('INITIAL_SESSION', this.session);

    // Return unsubscribe function
    return {
      data: {
        subscription: {
          unsubscribe: () => {
            this.subscribers = this.subscribers.filter(cb => cb !== callback);
          }
        }
      }
    };
  }

  // Mock admin interface for compatibility
  get auth() {
    return {
      admin: {
        getUser: this.getUser.bind(this),
        getUserById: (id: string) => this.getUser(),
        listUsers: () => Promise.resolve([]), // Mock implementation
      },
      signInWithPassword: this.signInWithPassword.bind(this),
      signOut: this.signOut.bind(this),
      getSession: this.getSession.bind(this),
      getUser: this.getUser.bind(this),
      setSession: this.setSession.bind(this),
      onAuthStateChange: this.onAuthStateChange.bind(this),
      refreshSession: this.refreshSession.bind(this)
    };
  }
}


export const localAuthClient = new LocalAuthClient();
export default localAuthClient;