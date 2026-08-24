/**
 * Simplified AppContext that works with the new AuthContext
 * This is a compatibility layer to avoid breaking existing code
 */

import React, {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  useCallback
} from 'react';
import { useAuth } from './AuthContext.new';
import { SecureAPI } from '../lib/secureApi';
import { storageManager } from '../utils/StorageManager';

/* ---------- User Types ---------- */
interface BaseAuthUser {
  id: string;
  email: string;
  is_admin?: boolean;
  tenant_id?: string | null;
  permissions?: Array<{ section: string; action: string }>;
  cities?: string[];
  user_metadata?: Record<string, any> | null;
  app_metadata?: Record<string, any> | null;
  [key: string]: any;
}

export interface EnrichedUser extends BaseAuthUser {
  tenant_id: string | null;
  permissions: Array<{ section: string; action: string }>;
  departments: any[];
  modules: string[];
}

interface AppContextData {
  user: EnrichedUser | null;
  tenant: any;
  companySettings: any;
  permissions: Array<{ section: string; action: string }>;
  modules: Set<string>;
  isLoading: boolean;
  error: string | null;
  isAdmin: boolean;
  hasPermission: (section: string, action: string) => boolean;
  hasModule: (module: string) => boolean;
  refreshData: (forceRefresh?: boolean) => Promise<void>;
  refreshDepartments: () => Promise<void>;
  departments?: any[];
}

const AppContext = createContext<AppContextData | null>(null);

export const useAppContext = () => {
  const context = useContext(AppContext);
  if (!context) throw new Error('useAppContext must be used within AppProvider');
  return context;
};

// Sticky modules memory to avoid dropping to zero between auth transitions
const lastModulesByTenant: Record<string, string[]> = {};

export const AppProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const authContext = useAuth();

  // Normalized "auth" proxy object
  const auth = {
    user: authContext.user,
    status: authContext.isLoading
      ? 'initializing'
      : (authContext.isAuthenticated ? 'authenticated' : 'unauthenticated'),
    permissions: [] as Array<{ section: string; action: string }>,
    modules: [] as string[],
    tenantId: authContext.user?.user_metadata?.tenant_id || null,
    companySettings: null,
    tenant: null,
    error: null,
    hasPermission: (_s: string, _a: string) => false,
    hasModule: (_m: string) => false,
    refreshSession: authContext.refreshSession
  };

  /* ---------- State ---------- */
  const isLoading = authContext.isLoading;
  const [permState, setPermState] = useState<Array<{ section: string; action: string }>>([]);
  const [authError, setAuthError] = useState<string | null>(null);
  const [resolvedTenantId, setResolvedTenantId] = useState<string | null>(null);
  const [modulesState, setModulesState] = useState<string[]>([]);
  const [companySettingsState, setCompanySettingsState] = useState<any>(null);
  const [departmentsState, setDepartmentsState] = useState<any[]>([]);
  const [isAdminFromMe, setIsAdminFromMe] = useState<boolean | null>(null);
  const [hasInitialRefresh, setHasInitialRefresh] = useState(false);
  const [forceRefreshFlag, setForceRefreshFlag] = useState(false);

  /* ---------- Modules as Set ---------- */
  const modules = useMemo(() => {
    const tid = (resolvedTenantId || auth.tenantId) || null;
    const current = modulesState.length > 0
      ? modulesState
      : (Array.isArray(auth.modules) ? auth.modules : []);
    if (tid && current.length > 0) {
      lastModulesByTenant[tid] = current;
      return new Set(current);
    }
    if (tid && lastModulesByTenant[tid]?.length) {
      return new Set(lastModulesByTenant[tid]);
    }
    return new Set(current);
  }, [modulesState, auth.modules, auth.tenantId, resolvedTenantId]);

  /* ---------- Admin Check ---------- */
  const isAdmin = useMemo(() => {
    if (isAdminFromMe !== null) {
      console.log('[AppContext] Using is_admin from /me endpoint:', isAdminFromMe);
      return isAdminFromMe;
    }

    // Fallback checks if /me hasn't loaded yet
    const list = permState.length > 0 ? permState : (auth.permissions || []);
    if (list.some(p => p.section === '*' && p.action === '*')) return true;
    const role =
      (auth.user as any)?.app_metadata?.role ||
      (auth.user as any)?.user_metadata?.role;
    if (role === 'admin') return true;
    const email = (auth.user as any)?.email || '';
    const ADMIN_EMAILS = [
      'sid@theflexliving.com',
      'raouf@theflexliving.com',
      'michael@theflexliving.com',
    ];
    return ADMIN_EMAILS.includes(email);
  }, [isAdminFromMe, permState, auth.permissions, auth.user]);

  /* ---------- Reset on user change ---------- */
  useEffect(() => {
    try {
      Object.keys(lastModulesByTenant).forEach(k => delete lastModulesByTenant[k]);
    } catch {}
    setModulesState([]);
    setCompanySettingsState(null);
    setResolvedTenantId(null);
    setPermState([]);
    setDepartmentsState([]);
    setIsAdminFromMe(null); // ✅ Reset admin status on user change
    setHasInitialRefresh(false); // ✅ Reset refresh flag for new user
    setForceRefreshFlag(false);
    console.log('[AppContext] User changed – state reset');
  }, [auth.user?.id]);

  /* ---------- Bootstrap + /auth/me hydration ---------- */
  useEffect(() => {
    if (auth.status !== 'authenticated') return;
    let cancelled = false;
    (async () => {
      try {
        // 1. Bootstrap local cache
        if (!permState.length) {
          try {
            // Only ever hydrate from THIS user's cache entry. Scanning for the
            // newest app_bootstrap_data_* key loaded whichever entry was freshest,
            // which could be another tenant's bootstrap data.
            const bestKey = auth.user?.id ? `app_bootstrap_data_${auth.user.id}` : null;
            if (bestKey && localStorage.getItem(bestKey)) {
              const raw = localStorage.getItem(bestKey)!;
              const parsed = JSON.parse(raw);
              const data = parsed?.data || {};
              const perms = Array.isArray(data.permissions) ? data.permissions : [];
              const tidFromData = data?.metadata?.tenant_id || data?.tenant?.id || null;
              const mods = Array.isArray(data.modules) ? data.modules : [];
              const company = data.company_settings || null;
              const depts =
                Array.isArray(data.departments)
                  ? data.departments
                  : (Array.isArray(data?.metadata?.departments)
                      ? data.metadata.departments
                      : []);

              const tenantMismatch = !!(auth.tenantId && tidFromData && tidFromData !== auth.tenantId);
              if (tenantMismatch) {
                console.warn('[AppContext] - discarding cache', {
                  jwt_tenant_id: auth.tenantId,
                  bootstrap_tenant_id: tidFromData
                });
                localStorage.removeItem(bestKey);
              }

              if (!cancelled && !tenantMismatch) {
                if (perms.length) setPermState(perms);

                // ✅ Apply same tenant prioritization logic for bootstrap data
                if (tidFromData) {
                  const jwtTenantId = auth.tenantId;
                  const userEmail = auth.user?.email;

                  const emergencyTenantOverrides: Record<string, string> = {
                    'noam@stayhomely.de': '5a382f72-aec3-40f1-9063-89476ae00669', // Homely
                  };

                  let finalTenantId = jwtTenantId || tidFromData;

                  if (userEmail && emergencyTenantOverrides[userEmail]) {
                    const correctTenant = emergencyTenantOverrides[userEmail];
                    if (finalTenantId !== correctTenant) {
                      console.warn('[AppContext] 🚨 BOOTSTRAP EMERGENCY OVERRIDE:', {
                        user_email: userEmail,
                        wrong_tenant: finalTenantId,
                        correct_tenant: correctTenant
                      });
                      finalTenantId = correctTenant;
                    }
                  }

                  if (jwtTenantId && tidFromData !== jwtTenantId) {
                    console.warn('[AppContext] 🚨 BOOTSTRAP TENANT CONFLICT:', {
                      jwt_tenant_id: jwtTenantId,
                      bootstrap_tenant_id: tidFromData,
                      final_tenant_id: finalTenantId,
                      resolution: emergencyTenantOverrides[userEmail || ''] ? 'emergency_override' : 'jwt_priority'
                    });
                  }

                  setResolvedTenantId(finalTenantId);
                }

                if (mods.length) setModulesState(mods);
                if (company) setCompanySettingsState(company);
                if (depts.length) setDepartmentsState(depts);
              }
              console.log('[AppContext] Hydrated from bootstrap cache', {
                perms: perms.length,
                mods: mods.length,
                depts: depts.length,
                tidFromData
              });
            }
          } catch (e) {
            console.log('[AppContext] Bootstrap cache parse failed', e);
          }
        }

        // 2. Always fetch fresh permissions on page load, use cache only for subsequent loads
        const shouldForceRefresh = !hasInitialRefresh || forceRefreshFlag;
        const shouldUseCache = hasInitialRefresh && !forceRefreshFlag && !permState.length;

        // Load from cache only if we've already done initial refresh in this session
        if (shouldUseCache) {
          const tid = resolvedTenantId || auth.tenantId || 'unknown';
          const cacheKey = `auth_cache_permissions_${auth.user?.id || 'anon'}_${tid}`;
          const raw = localStorage.getItem(cacheKey);
          if (raw) {
            const parsed = JSON.parse(raw);
            if (Array.isArray(parsed?.data) && parsed.data.length > 0) {
              if (!cancelled) setPermState(parsed.data);
              console.log('[AppContext] Loaded permissions from cache (subsequent load)', parsed.data.length);
            }
          }
        }

        // 3. ALWAYS fetch fresh permissions on page refresh or initial auth
        if (shouldForceRefresh) {
          console.log('[AppContext] Fetching FRESH permissions from backend (page refresh/initial load)', { hasInitialRefresh, forceRefreshFlag });
          const me = await SecureAPI.getAuthMe();
          if (me) {
            if (!cancelled && Array.isArray(me.permissions)) {
              console.log(`[AppContext] ✅ Setting FRESH permissions: ${me.permissions.length} permissions loaded`);
              setPermState(me.permissions);
            }
            // This prevents tenant conflicts that cause 403 errors and wrong branding
            if (!cancelled) {
              const jwtTenantId = auth.tenantId;
              const apiTenantId = me.tenant_id;
              const userEmail = auth.user?.email;

              // Since backend diagnosis shows DB is correct but JWT may have wrong tenant metadata
              const emergencyTenantOverrides: Record<string, string> = {
                'noam@stayhomely.de': '5a382f72-aec3-40f1-9063-89476ae00669', // Homely
                // Add other users here if needed
              };

              let finalTenantId = jwtTenantId || apiTenantId || null;

              if (userEmail && emergencyTenantOverrides[userEmail]) {
                const correctTenant = emergencyTenantOverrides[userEmail];
                if (finalTenantId !== correctTenant) {
                  console.warn('[AppContext] 🚨 EMERGENCY TENANT OVERRIDE:', {
                    user_email: userEmail,
                    wrong_tenant: finalTenantId,
                    correct_tenant: correctTenant,
                    source: 'emergency_override'
                  });
                  finalTenantId = correctTenant;
                }
              }

              if (jwtTenantId && apiTenantId && jwtTenantId !== apiTenantId) {
                console.warn('[AppContext] 🚨 TENANT CONFLICT DETECTED:', {
                  jwt_tenant_id: jwtTenantId,
                  api_tenant_id: apiTenantId,
                  user_email: userEmail,
                  final_tenant_id: finalTenantId,
                  resolution: emergencyTenantOverrides[userEmail || ''] ? 'emergency_override' : 'jwt_priority'
                });
              }
              setResolvedTenantId(finalTenantId);

              // Update StorageManager context to ensure consistency
              if (finalTenantId && auth.user?.id) {
                storageManager.setContext({
                  tenant_id: finalTenantId,
                  user_id: auth.user.id,
                  email: auth.user.email
                });
              }

              console.log('[AppContext] ✅ Tenant resolution completed:', {
                final_tenant_id: finalTenantId,
                source: jwtTenantId ? 'JWT_prioritized' : 'API_fallback'
              });
            }
            if (!cancelled) {
              setHasInitialRefresh(true);
              setForceRefreshFlag(false);
            }

            // ✅ For admins, fetch ALL departments instead of just assigned ones
            if (me.is_admin) {
              console.log('[AppContext] User is admin - fetching ALL departments');
              try {
                const allDepartments = await SecureAPI.getDepartments();
                if (!cancelled && Array.isArray(allDepartments)) {
                  setDepartmentsState(allDepartments);
                  console.log('[AppContext] Admin departments loaded:', allDepartments.length);
                }
              } catch (err) {
                console.error('[AppContext] Failed to fetch all departments for admin:', err);
                // Fallback to assigned departments
                if (!cancelled && Array.isArray(me.departments)) {
                  setDepartmentsState(me.departments);
                }
              }
            } else {
              // Non-admin: use only assigned departments from /me
              if (!cancelled && Array.isArray(me.departments)) {
                setDepartmentsState(me.departments);
              }
            }

            // ✅ Store is_admin from /me endpoint
            if (!cancelled && typeof me.is_admin === 'boolean') {
              setIsAdminFromMe(me.is_admin);
              console.log('[AppContext] Set isAdmin from /me endpoint:', me.is_admin);
            }

            try {
              if (Array.isArray(me.permissions)) {
                const key = `auth_cache_permissions_${auth.user?.id || 'anon'}_${me.tenant_id || 'unknown'}`;
                localStorage.setItem(key, JSON.stringify({ ts: Date.now(), data: me.permissions }));
              }
            } catch {}
          }
        }
      } catch (e: any) {
        if (!cancelled) setAuthError(e?.message || 'Failed to load auth context');
        console.log('[AppContext] Error during hydration', e);
      }
    })();

    return () => { cancelled = true; };
  }, [auth.status, auth.user?.id, resolvedTenantId, auth.tenantId, permState.length, hasInitialRefresh, forceRefreshFlag]);

  /* ---------- Permission helper ---------- */
  const hasPermissionFn = useCallback((section: string, action: string) => {
    const s = (section || '').toLowerCase();
    const list = permState.length > 0 ? permState : (auth.permissions || []);
    if (!list.length) return false;
    if (isAdmin) return true;
    if (list.some(p => p.section === '*' && p.action === '*')) return true;
    const norm = (x: string) => ({
      'reservations': 'all_reservations',
      'property': 'properties',
      'property_details': 'properties',
      'props': 'properties',
    } as Record<string,string>)[x] || x;
    const ns = norm(s);
    return list.some(
      p =>
        norm((p.section || '').toLowerCase()) === ns &&
        (p.action === action || (action === 'read' && p.action === 'view'))
    );
  }, [permState, auth.permissions, isAdmin]);

  /* ---------- Company Settings ---------- */
  useEffect(() => {
    const tid = resolvedTenantId || auth.tenantId || null;
    if (auth.status !== 'authenticated' || !tid) return;
    let cancelled = false;
    (async () => {
      try {
        const data = await SecureAPI.getCompanySettings();
        if (!cancelled && data) {
          setCompanySettingsState(data);
          console.log('[AppContext] Company settings refreshed');
        }
      } catch {
        // silent
      }
    })();
    return () => { cancelled = true; };
  }, [auth.status, resolvedTenantId, auth.tenantId]);

  /* ---------- Loading Flag ---------- */
  const effectiveLoading = useMemo(
    () => isLoading || (auth.status === 'authenticated' && permState.length === 0 && !authError),
    [isLoading, auth.status, permState.length, authError]
  );

  /* ---------- Compose Enriched User ---------- */
  const composedUser: EnrichedUser | null = useMemo(() => {
    if (!auth.user) return null;
    return {
      ...(auth.user as BaseAuthUser),
      tenant_id: resolvedTenantId || auth.tenantId || null,
      permissions: permState.length > 0 ? permState : (auth.permissions || []),
      departments: departmentsState,
      modules: Array.from(modules),
      is_admin: isAdminFromMe ?? false, // ✅ Include is_admin from /me endpoint
    };
  }, [
    auth.user,
    resolvedTenantId,
    auth.tenantId,
    permState,
    auth.permissions,
    departmentsState,
    modules,
    isAdminFromMe, // ✅ Add to dependencies
  ]);

  /* ---------- Log enriched user (full departments) ---------- */
  useEffect(() => {
    if (composedUser) {
      console.log('[AppContext] Composed user updated', {
        id: composedUser.id,
        email: composedUser.email,
        is_admin: composedUser.is_admin,
        tenant_id: composedUser.tenant_id,
        permissions: composedUser.permissions.length,
        departmentsCount: composedUser.departments.length,
        modules: composedUser.modules.length
      });
    }
  }, [composedUser]);

  /* ---------- Context Value ---------- */
  const value: AppContextData = {
    user: composedUser,
    tenant: (resolvedTenantId || auth.tenantId)
      ? { id: (resolvedTenantId || auth.tenantId)! }
      : null,
    companySettings: companySettingsState || auth.companySettings,
    permissions: permState.length ? permState : (auth.permissions || []),
    modules,
    isLoading: effectiveLoading,
    error: authError || auth.error,
    isAdmin,
    hasPermission: hasPermissionFn,
    hasModule: auth.hasModule,
    refreshData: async (forceRefresh = false) => {
      await auth.refreshSession();
      if (forceRefresh || !hasInitialRefresh) {
        console.log('[AppContext] refreshData invoked - forcing permission refresh');
        setForceRefreshFlag(true);
      } else {
        console.log('[AppContext] refreshData invoked - session refresh only');
      }
    },
    refreshDepartments: async () => {
      console.log('[AppContext] refreshDepartments invoked');
      try {
        // Check if user is admin by looking at current state
        const userIsAdmin = isAdmin;

        if (userIsAdmin) {
          console.log('[AppContext] Fetching ALL departments for admin');
          const allDepartments = await SecureAPI.getDepartments();
          setDepartmentsState(allDepartments);
          console.log('[AppContext] Departments refreshed:', allDepartments.length);
        } else {
          // For non-admin, re-fetch from /me endpoint
          console.log('[AppContext] Fetching assigned departments for non-admin');
          const me = await SecureAPI.getAuthMe();
          if (me && Array.isArray(me.departments)) {
            setDepartmentsState(me.departments);
            console.log('[AppContext] Departments refreshed:', me.departments.length);
          }
        }
      } catch (error) {
        console.error('[AppContext] Failed to refresh departments:', error);
      }
    },
    departments: departmentsState
  };

  return (
    <AppContext.Provider value={value}>{children}</AppContext.Provider>
  );
};

/* ---------- Legacy / Convenience Hooks ---------- */
export default AppContext;

let lastCompanySettings: any | null = null;
let lastCompanyTenant: string | null = null;

export function useCompanySettings() {
  const context = useAppContext();
  const currentTenant = context.tenant?.id || null;
  if (context.companySettings) {
    lastCompanySettings = context.companySettings;
    lastCompanyTenant = currentTenant;
  }
  const settings = context.companySettings
    ? context.companySettings
    : (lastCompanyTenant === currentTenant ? lastCompanySettings : null);
  return {
    companySettings: settings,
    isLoading: context.isLoading,
    error: null
  };
}

export function usePermissions() {
  const context = useAppContext();
  return {
    permissions: context.permissions,
    hasPermission: context.hasPermission,
    loading: context.isLoading,
    isAdmin: context.isAdmin,
    refreshPermissions: context.refreshData
  };
}

export function useModules() {
  const context = useAppContext();
  return {
    modules: context.modules,
    hasModule: context.hasModule,
    isLoading: context.isLoading
  };
}
