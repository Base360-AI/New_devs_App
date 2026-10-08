/**
 * Legacy LocalStorage Manager - DEPRECATED
 * 
 * This file is maintained for backward compatibility but delegates to the new StorageManager.
 * New code should use StorageManager directly from './StorageManager.ts'
 * 
 * Handles localStorage validation, migration, and cleanup
 */

import { storageManager, STORAGE_KEYS } from './StorageManager';
import { storageHealthChecker } from './StorageHealthChecker';
import { storageRecoverySystem } from './StorageRecoverySystem';

const STORAGE_VERSION_KEY = 'app_storage_version';
const CURRENT_VERSION = '2.0.0'; // Keep at 2.0.0 to avoid forcing migration on existing users

// Session key used by localAuthClient; wiping it logs the user out
const AUTH_TOKEN_KEY = 'base360-auth-token';

// Keys that must survive any storage cleanup or migration
const isAuthKey = (key: string): boolean =>
  key === AUTH_TOKEN_KEY || key.includes('supabase') || key.includes('sb-');

interface StorageSchema {
  version: string;
  timestamp: number;
}

/**
 * @deprecated Use StorageManager from './StorageManager.ts' instead
 */
class LocalStorageManager {
  private static instance: LocalStorageManager;
  
  private constructor() {
    this.initialize();
  }

  static getInstance(): LocalStorageManager {
    if (!LocalStorageManager.instance) {
      LocalStorageManager.instance = new LocalStorageManager();
    }
    return LocalStorageManager.instance;
  }

  /**
   * Initialize localStorage with version checking
   */
  private initialize(): void {
    try {
      const storedVersion = localStorage.getItem(STORAGE_VERSION_KEY);
      
      if (!storedVersion || storedVersion !== CURRENT_VERSION) {
        console.log(`LocalStorage version mismatch. Current: ${CURRENT_VERSION}, Stored: ${storedVersion}`);
        this.migrateStorage(storedVersion);
      }
      
      // Set current version
      localStorage.setItem(STORAGE_VERSION_KEY, CURRENT_VERSION);
    } catch (error) {
      console.error('Failed to initialize localStorage:', error);
      this.clearCorruptedStorage();
    }
  }

  /**
   * Migrate localStorage from old version to new version
   */
  private migrateStorage(oldVersion: string | null): void {
    console.log(`Migrating localStorage from version ${oldVersion} to ${CURRENT_VERSION}`);
    
    // Define migration strategies based on version
    const migrations: Record<string, () => void> = {
      'null': () => {
        // First time initialization or corrupted storage
        this.clearAllExceptEssentials();
      },
      '1.0.0': () => {
        // Migrate from 1.0.0 to current
        this.migrateV1ToV2();
      },
      '1.1.0': () => {
        // Migrate from 1.1.0 to current
        this.migrateV1ToV2();
      },
      '1.2.0': () => {
        // Migrate from 1.2.0 to current
        this.migrateV1ToV2();
      },
      '2.0.0': () => {
        // Migrate from 2.0.0 to 2.1.0 - cleanup corrupted data
        this.migrateV1ToV2();
      }
    };

    const migrationFn = migrations[oldVersion || 'null'];
    if (migrationFn) {
      migrationFn();
    } else {
      // Unknown version - clear potentially incompatible data
      console.warn(`Unknown storage version: ${oldVersion}. Clearing non-essential data.`);
      this.clearAllExceptEssentials();
    }
  }

  /**
   * Migration from v1 to v2 format
   */
  private migrateV1ToV2(): void {
    try {
      // Preserve essential data
      const essentialKeys = [
        'selectedCity',
        'user_permissions',
        'tenant_id',
        'organization_id'
      ];
      
      const preservedData: Record<string, string> = {};
      
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key && isAuthKey(key)) {
          const value = localStorage.getItem(key);
          if (value) {
            preservedData[key] = value;
            console.log(`Preserving auth key: ${key}`);
          }
        }
      }
      
      // Preserve other essential keys
      essentialKeys.forEach(key => {
        const value = localStorage.getItem(key);
        if (value) {
          if (key === 'user_permissions') {
            try {
              JSON.parse(value);
              preservedData[key] = value;
            } catch {
              console.warn(`Corrupted JSON in ${key}, skipping preservation`);
            }
          } else {
            preservedData[key] = value;
          }
        }
      });
      
      // Clear deprecated cache keys and potentially corrupted data
      const deprecatedPrefixes = [
        'cache_',
        'temp_',
        'old_',
        '_legacy',
        'undefined',
        'null'
      ];
      
      const keysToRemove: string[] = [];
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key) {
          const shouldRemove = deprecatedPrefixes.some(prefix => 
            key.startsWith(prefix) || key === prefix
          );
          if (shouldRemove) {
            keysToRemove.push(key);
          }
          
          // Also remove any keys with invalid JSON
          try {
            const value = localStorage.getItem(key);
            if (value && value.startsWith('{') || value?.startsWith('[')) {
              JSON.parse(value);
            }
          } catch {
            if (!essentialKeys.includes(key)) {
              console.warn(`Removing corrupted JSON key: ${key}`);
              keysToRemove.push(key);
            }
          }
        }
      }
      
      // Remove deprecated keys but never remove preserved ones
      keysToRemove.forEach(key => {
        if (!preservedData.hasOwnProperty(key)) {
          localStorage.removeItem(key);
        }
      });
      
      // Restore all preserved data (in case anything was accidentally removed)
      Object.entries(preservedData).forEach(([key, value]) => {
        localStorage.setItem(key, value);
      });
      
      // Update data structures if needed
      this.updateDataStructures();
      
      console.log('Migration from v1 to v2 completed successfully', {
        preservedKeys: Object.keys(preservedData).length,
        removedKeys: keysToRemove.length
      });
    } catch (error) {
      console.error('Migration failed:', error);
      this.clearCorruptedStorage();
    }
  }

  /**
   * Update data structures to current format
   */
  private updateDataStructures(): void {
    // Update filter presets format if exists
    const filterPresets = localStorage.getItem('filterPresets');
    if (filterPresets) {
      try {
        const parsed = JSON.parse(filterPresets);
        // Add any necessary structure updates
        localStorage.setItem('filterPresets', JSON.stringify(parsed));
      } catch {
        localStorage.removeItem('filterPresets');
      }
    }
    
    // Update reservation cache format
    const reservationCache = localStorage.getItem('reservation_cache');
    if (reservationCache) {
      try {
        const parsed = JSON.parse(reservationCache);
        // Clear if data is older than 24 hours
        if (parsed.timestamp && Date.now() - parsed.timestamp > 24 * 60 * 60 * 1000) {
          localStorage.removeItem('reservation_cache');
        }
      } catch {
        localStorage.removeItem('reservation_cache');
      }
    }
  }

  /**
   * Clear all localStorage except essential keys
   */
  private clearAllExceptEssentials(): void {
    const preservedData: Record<string, string> = {};
    
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && isAuthKey(key)) {
        const value = localStorage.getItem(key);
        if (value) {
          preservedData[key] = value;
        }
      }
    }

    // Also preserve version key
    const versionValue = localStorage.getItem(STORAGE_VERSION_KEY);
    if (versionValue) {
      preservedData[STORAGE_VERSION_KEY] = versionValue;
    }
    
    localStorage.clear();
    
    // Restore essential data
    Object.entries(preservedData).forEach(([key, value]) => {
      localStorage.setItem(key, value);
    });
    
    console.log('Cleared localStorage except essential keys', {
      preservedKeys: Object.keys(preservedData)
    });
  }

  /**
   * Clear corrupted storage and start fresh
   */
  private clearCorruptedStorage(): void {
    console.warn('Clearing corrupted localStorage');
    try {
      // Never log the user out as a side effect of a storage cleanup
      const authToken = localStorage.getItem(AUTH_TOKEN_KEY);
      localStorage.clear();
      if (authToken) {
        localStorage.setItem(AUTH_TOKEN_KEY, authToken);
      }
      localStorage.setItem(STORAGE_VERSION_KEY, CURRENT_VERSION);
    } catch (error) {
      console.error('Failed to clear corrupted storage:', error);
    }
  }

  /**
   * Validate stored data structure
   */
  validateStoredData(key: string, validator: (data: any) => boolean): any {
    try {
      const stored = localStorage.getItem(key);
      if (!stored) return null;
      
      const parsed = JSON.parse(stored);
      if (validator(parsed)) {
        return parsed;
      } else {
        console.warn(`Invalid data structure for key: ${key}. Removing.`);
        localStorage.removeItem(key);
        return null;
      }
    } catch (error) {
      console.error(`Failed to validate data for key: ${key}`, error);
      localStorage.removeItem(key);
      return null;
    }
  }

  /**
   * Safe get with JSON parsing
   * @deprecated Use storageManager.get() instead
   */
  getItem<T>(key: string): T | null {
    console.warn(`[LocalStorageManager] DEPRECATED: getItem(${key}) - Use storageManager.get() instead`);
    return storageManager.get<T>(key, { skipIntegrityCheck: true });
  }

  /**
   * Safe set with JSON stringification
   * @deprecated Use storageManager.set() instead
   */
  setItem(key: string, value: any): void {
    console.warn(`[LocalStorageManager] DEPRECATED: setItem(${key}) - Use storageManager.set() instead`);
    const success = storageManager.set(key, value, { skipIntegrityCheck: true });
    
    if (!success) {
      console.error(`Failed to set item: ${key}`);
      // If storage failed, attempt recovery
      storageRecoverySystem.attemptRecovery().catch(err => {
        console.error('Failed to recover storage:', err);
      });
    }
  }

  /**
   * Clear cache data to free up space
   */
  private clearCacheData(): void {
    const cacheKeys = [
      'reservation_cache',
      'properties_cache',
      'cache_',
      'temp_'
    ];
    
    for (let i = localStorage.length - 1; i >= 0; i--) {
      const key = localStorage.key(i);
      if (key && cacheKeys.some(prefix => key.startsWith(prefix))) {
        localStorage.removeItem(key);
      }
    }
    
    console.log('Cleared cache data from localStorage');
  }

  /**
   * Force clear all localStorage and reload
   * @deprecated Use storageManager.clearAll() instead
   */
  forceReset(): void {
    console.warn('[LocalStorageManager] DEPRECATED: forceReset() - Use storageManager.clearAll() instead');
    storageManager.clearAll();
    localStorage.setItem(STORAGE_VERSION_KEY, CURRENT_VERSION);
    window.location.reload();
  }

  /**
   * Get storage info
   * @deprecated Use storageManager.getDiagnostics() instead
   */
  getStorageInfo(): {
    version: string;
    itemCount: number;
    approximateSize: number;
    keys: string[];
  } {
    console.warn('[LocalStorageManager] DEPRECATED: getStorageInfo() - Use storageManager.getDiagnostics() instead');
    const diagnostics = storageManager.getDiagnostics();
    
    return {
      version: localStorage.getItem(STORAGE_VERSION_KEY) || 'unknown',
      itemCount: diagnostics.item_count,
      approximateSize: diagnostics.total_size,
      keys: [] // Not exposed by new system for security reasons
    };
  }
}

export default LocalStorageManager.getInstance();

// Export utility functions for direct use
/**
 * @deprecated Use storageManager.clearUserData() instead
 */
export const clearLocalStorageCache = () => {
  console.warn('[LocalStorageManager] DEPRECATED: clearLocalStorageCache() - Use storageManager.clearUserData() instead');
  const manager = LocalStorageManager.getInstance();
  manager['clearCacheData']();
};

/**
 * @deprecated Use storageManager.clearAll() instead
 */
export const resetLocalStorage = () => {
  console.warn('[LocalStorageManager] DEPRECATED: resetLocalStorage() - Use storageManager.clearAll() instead');
  storageManager.clearAll();
};

/**
 * @deprecated Use storageManager.getDiagnostics() instead
 */
export const getStorageInfo = () => {
  console.warn('[LocalStorageManager] DEPRECATED: getStorageInfo() - Use storageManager.getDiagnostics() instead');
  const manager = LocalStorageManager.getInstance();
  return manager.getStorageInfo();
};

// Re-export new storage utilities for migration
export { storageManager } from './StorageManager';
export { storageHealthChecker } from './StorageHealthChecker';
export { storageRecoverySystem } from './StorageRecoverySystem';