/**
 * Storage Health Checker
 * 
 * Comprehensive storage health monitoring system that:
 * - Detects various types of storage corruption
 * - Validates storage integrity across sessions
 * - Monitors storage health over time
 * - Provides automatic recovery mechanisms
 * - Offers detailed diagnostics for debugging
 */

import { storageManager, STORAGE_KEYS } from './StorageManager';
import { supabase } from '../lib/supabase';

export interface StorageHealthReport {
  overall_health: 'healthy' | 'degraded' | 'corrupted' | 'critical';
  issues: StorageIssue[];
  diagnostics: StorageHealthDiagnostics;
  recommendations: string[];
  auto_fix_applied: boolean;
  timestamp: number;
}

export interface StorageIssue {
  type: 'corruption' | 'orphaned_data' | 'version_mismatch' | 'size_overflow' | 'invalid_schema' | 'session_conflict';
  severity: 'low' | 'medium' | 'high' | 'critical';
  description: string;
  affected_keys: string[];
  auto_fixable: boolean;
}

export interface StorageHealthDiagnostics {
  total_size: number;
  total_items: number;
  corrupted_items: number;
  orphaned_items: number;
  expired_items: number;
  version_mismatches: number;
  session_conflicts: number;
  largest_item: { key: string; size: number };
  oldest_item: { key: string; age_hours: number };
  storage_efficiency: number;
}

export class StorageHealthChecker {
  private static instance: StorageHealthChecker;
  private lastHealthCheck: number = 0;
  private healthCheckInterval: NodeJS.Timeout | null = null;
  private readonly HEALTH_CHECK_INTERVAL = 10 * 60 * 1000; // 10 minutes
  private readonly MAX_ITEM_AGE_HOURS = 24; // 24 hours
  private readonly MAX_ORPHANED_AGE_HOURS = 1; // 1 hour for orphaned data
  
  private constructor() {
    this.startHealthMonitoring();
  }
  
  static getInstance(): StorageHealthChecker {
    if (!StorageHealthChecker.instance) {
      StorageHealthChecker.instance = new StorageHealthChecker();
    }
    return StorageHealthChecker.instance;
  }
  
  /**
   * Perform comprehensive storage health check
   */
  async performHealthCheck(options?: {
    autoFix?: boolean;
    detailed?: boolean;
  }): Promise<StorageHealthReport> {
    const startTime = Date.now();
    console.log('[StorageHealthChecker] Starting comprehensive health check...');
    
    const issues: StorageIssue[] = [];
    let autoFixApplied = false;
    
    try {
      // 1. Check for corrupted items
      const corruptionIssues = this.checkForCorruption();
      issues.push(...corruptionIssues);
      
      // 2. Check for orphaned data
      const orphanedIssues = await this.checkForOrphanedData();
      issues.push(...orphanedIssues);
      
      // 3. Check for version mismatches
      const versionIssues = this.checkVersionMismatches();
      issues.push(...versionIssues);
      
      // 4. Check for session conflicts
      const sessionIssues = await this.checkSessionConflicts();
      issues.push(...sessionIssues);
      
      // 5. Check storage size and efficiency
      const sizeIssues = this.checkStorageSize();
      issues.push(...sizeIssues);
      
      if (options?.autoFix) {
        autoFixApplied = await this.autoFixIssues(issues);
      }
      
      // 7. Generate diagnostics
      const diagnostics = this.generateDiagnostics();
      
      // 8. Determine overall health
      const overallHealth = this.determineOverallHealth(issues);
      
      // 9. Generate recommendations
      const recommendations = this.generateRecommendations(issues, diagnostics);
      
      const report: StorageHealthReport = {
        overall_health: overallHealth,
        issues,
        diagnostics,
        recommendations,
        auto_fix_applied: autoFixApplied,
        timestamp: Date.now()
      };
      
      // Store health report
      storageManager.set(STORAGE_KEYS.STORAGE_HEALTH, report, {
        skipIntegrityCheck: true, // Avoid recursion
        ttl: 24 * 60 * 60 * 1000 // 24 hours
      });
      
      const duration = Date.now() - startTime;
      console.log('[StorageHealthChecker] Health check completed:', {
        duration_ms: duration,
        overall_health: overallHealth,
        issues_found: issues.length,
        auto_fix_applied: autoFixApplied
      });
      
      this.lastHealthCheck = Date.now();
      return report;
      
    } catch (error) {
      console.error('[StorageHealthChecker] Health check failed:', error);
      
      return {
        overall_health: 'critical',
        issues: [{
          type: 'corruption',
          severity: 'critical',
          description: `Health check system failure: ${error instanceof Error ? error.message : String(error)}`,
          affected_keys: [],
          auto_fixable: false
        }],
        diagnostics: this.generateDiagnostics(),
        recommendations: ['Perform manual storage cleanup', 'Contact technical support'],
        auto_fix_applied: false,
        timestamp: Date.now()
      };
    }
  }
  
  /**
   * Check for corrupted storage items
   */
  private checkForCorruption(): StorageIssue[] {
    const issues: StorageIssue[] = [];
    const corruptedKeys: string[] = [];
    
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (!key) continue;
      
      try {
        const value = localStorage.getItem(key);
        if (!value) continue;

        // Plain strings (version marker, language, ...) are legitimate values,
        // not corruption. Only JSON-shaped values are validated below.
        const trimmed = value.trim();
        if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) continue;

        // Try to parse as JSON
        const parsed = JSON.parse(trimmed);
        
        // Check if it's our storage format
        if (typeof parsed === 'object' && parsed !== null) {
          // Validate basic structure
          if (parsed.data === undefined || parsed.timestamp === undefined) {
            // This might be a legacy or foreign storage item
            continue;
          }
          
          // Check timestamp validity
          if (typeof parsed.timestamp !== 'number' || parsed.timestamp > Date.now()) {
            corruptedKeys.push(key);
          }
          
          // Check version if present
          if (parsed.version && typeof parsed.version !== 'string') {
            corruptedKeys.push(key);
          }
        }
      } catch (error) {
        // Failed to parse JSON - corrupted
        corruptedKeys.push(key);
      }
    }
    
    if (corruptedKeys.length > 0) {
      issues.push({
        type: 'corruption',
        severity: corruptedKeys.length > 10 ? 'critical' : corruptedKeys.length > 5 ? 'high' : 'medium',
        description: `Found ${corruptedKeys.length} corrupted storage items`,
        affected_keys: corruptedKeys,
        auto_fixable: true
      });
    }
    
    return issues;
  }
  
  /**
   * Check for orphaned data (data without current session context)
   */
  private async checkForOrphanedData(): Promise<StorageIssue[]> {
    const issues: StorageIssue[] = [];
    const orphanedKeys: string[] = [];
    
    // Get current session context
    let currentUserId: string | null = null;
    let currentTenantId: string | null = null;
    
    try {
      const { data: { session } } = await supabase.auth.getSession();
      currentUserId = session?.user?.id || null;
      currentTenantId = session?.user?.app_metadata?.tenant_id || null;
    } catch (error) {
      console.warn('[StorageHealthChecker] Could not get current session for orphan check:', error);
    }
    
    const now = Date.now();
    
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (!key) continue;
      
      try {
        // Check if key is namespaced
        const parts = key.split('::');
        if (parts.length >= 3) {
          const keyTenantId = parts[0];
          const keyUserId = parts[1];
          
          // Check if this belongs to a different user/tenant
          if (currentUserId && currentTenantId) {
            if (keyUserId !== currentUserId || keyTenantId !== currentTenantId) {
              // Check age to see if it's truly orphaned
              const value = localStorage.getItem(key);
              if (value) {
                try {
                  const parsed = JSON.parse(value);
                  const ageHours = (now - parsed.timestamp) / (1000 * 60 * 60);
                  
                  if (ageHours > this.MAX_ORPHANED_AGE_HOURS) {
                    orphanedKeys.push(key);
                  }
                } catch {
                  // Can't parse - treat as orphaned
                  orphanedKeys.push(key);
                }
              }
            }
          }
        }
      } catch (error) {
        console.warn('[StorageHealthChecker] Error checking orphaned data:', error);
      }
    }
    
    if (orphanedKeys.length > 0) {
      issues.push({
        type: 'orphaned_data',
        severity: orphanedKeys.length > 20 ? 'high' : 'medium',
        description: `Found ${orphanedKeys.length} orphaned storage items from previous sessions`,
        affected_keys: orphanedKeys,
        auto_fixable: true
      });
    }
    
    return issues;
  }
  
  /**
   * Check for version mismatches
   */
  private checkVersionMismatches(): StorageIssue[] {
    const issues: StorageIssue[] = [];
    const mismatchedKeys: string[] = [];
    const currentVersion = '2.0.0'; // Should match StorageManager.STORAGE_VERSION
    
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (!key) continue;
      
      try {
        const value = localStorage.getItem(key);
        if (!value) continue;
        
        const parsed = JSON.parse(value);
        if (typeof parsed === 'object' && parsed !== null && parsed.version) {
          if (parsed.version !== currentVersion) {
            mismatchedKeys.push(key);
          }
        }
      } catch (error) {
        // Ignore parsing errors - handled in corruption check
      }
    }
    
    if (mismatchedKeys.length > 0) {
      issues.push({
        type: 'version_mismatch',
        severity: 'medium',
        description: `Found ${mismatchedKeys.length} items with outdated storage format`,
        affected_keys: mismatchedKeys,
        auto_fixable: true
      });
    }
    
    return issues;
  }
  
  /**
   * Check for session conflicts
   */
  private async checkSessionConflicts(): Promise<StorageIssue[]> {
    const issues: StorageIssue[] = [];
    
    try {
      // Look for multiple session-like storage items
      const sessionKeys: string[] = [];
      const authKeys: string[] = [];
      
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (!key) continue;
        
        if (key.includes('auth') || key.includes('session') || key.includes('supabase')) {
          if (key.includes(STORAGE_KEYS.AUTH_SESSION) || key.includes(STORAGE_KEYS.SESSION_BACKUP)) {
            sessionKeys.push(key);
          } else if (key.includes('auth')) {
            authKeys.push(key);
          }
        }
      }
      
      // Check for multiple active sessions
      if (sessionKeys.length > 3) { // Allow for namespaced variations
        issues.push({
          type: 'session_conflict',
          severity: 'high',
          description: `Multiple active session detected (${sessionKeys.length} session keys found)`,
          affected_keys: sessionKeys,
          auto_fixable: true
        });
      }
      
      // Check for too many auth-related keys (might indicate accumulation)
      if (authKeys.length > 10) {
        issues.push({
          type: 'session_conflict',
          severity: 'medium',
          description: `Excessive authentication data accumulation (${authKeys.length} auth keys)`,
          affected_keys: authKeys,
          auto_fixable: true
        });
      }
      
    } catch (error) {
      console.warn('[StorageHealthChecker] Error checking session conflicts:', error);
    }
    
    return issues;
  }
  
  /**
   * Check storage size and efficiency
   */
  private checkStorageSize(): StorageIssue[] {
    const issues: StorageIssue[] = [];
    const diagnostics = storageManager.getDiagnostics();
    
    // Check if approaching storage limits
    const usagePercentage = parseFloat(diagnostics.usage_percentage);
    
    if (usagePercentage > 90) {
      issues.push({
        type: 'size_overflow',
        severity: 'critical',
        description: `Storage usage at ${usagePercentage}% - approaching browser limits`,
        affected_keys: [],
        auto_fixable: true
      });
    } else if (usagePercentage > 75) {
      issues.push({
        type: 'size_overflow',
        severity: 'high',
        description: `Storage usage at ${usagePercentage}% - cleanup recommended`,
        affected_keys: [],
        auto_fixable: true
      });
    }
    
    return issues;
  }
  
  /**
   */
  private async autoFixIssues(issues: StorageIssue[]): Promise<boolean> {
    let fixedAny = false;
    
    for (const issue of issues) {
      if (!issue.auto_fixable) continue;
      
      try {
        switch (issue.type) {
          case 'corruption':
            this.fixCorruptedItems(issue.affected_keys);
            fixedAny = true;
            break;
            
          case 'orphaned_data':
            this.fixOrphanedItems(issue.affected_keys);
            fixedAny = true;
            break;
            
          case 'version_mismatch':
            this.fixVersionMismatches(issue.affected_keys);
            fixedAny = true;
            break;
            
          case 'session_conflict':
            await this.fixSessionConflicts(issue.affected_keys);
            fixedAny = true;
            break;
            
          case 'size_overflow':
            this.fixSizeOverflow();
            fixedAny = true;
            break;
        }
      } catch (error) {
        console.error(`[StorageHealthChecker] Failed to auto-fix ${issue.type}:`, error);
      }
    }
    
    if (fixedAny) {
      console.log('[StorageHealthChecker] Auto-fix applied for detected issues');
    }
    
    return fixedAny;
  }
  
  /**
   */
  private fixCorruptedItems(keys: string[]): void {
    keys.forEach(key => {
      try {
        localStorage.removeItem(key);
      } catch (error) {
        console.warn(`[StorageHealthChecker] Failed to remove corrupted key ${key}:`, error);
      }
    });
    
    console.log(`[StorageHealthChecker] Removed ${keys.length} corrupted items`);
  }
  
  /**
   */
  private fixOrphanedItems(keys: string[]): void {
    keys.forEach(key => {
      try {
        localStorage.removeItem(key);
      } catch (error) {
        console.warn(`[StorageHealthChecker] Failed to remove orphaned key ${key}:`, error);
      }
    });
    
    console.log(`[StorageHealthChecker] Removed ${keys.length} orphaned items`);
  }
  
  /**
   */
  private fixVersionMismatches(keys: string[]): void {
    keys.forEach(key => {
      try {
        // For now, just remove outdated items
        // In future, could implement data migration
        localStorage.removeItem(key);
      } catch (error) {
        console.warn(`[StorageHealthChecker] Failed to fix version mismatch for ${key}:`, error);
      }
    });
    
    console.log(`[StorageHealthChecker] Fixed ${keys.length} version mismatches`);
  }
  
  /**
   */
  private async fixSessionConflicts(keys: string[]): Promise<void> {
    // Try to preserve the most recent/relevant session data
    const currentSession = await supabase.auth.getSession();
    const currentUserId = currentSession.data?.session?.user?.id;
    
    if (!currentUserId) {
      // No current session, safe to remove all
      keys.forEach(key => {
        try {
          localStorage.removeItem(key);
        } catch (error) {
          console.warn(`[StorageHealthChecker] Failed to remove conflicting session key ${key}:`, error);
        }
      });
    } else {
      // Remove keys that don't belong to current user
      keys.forEach(key => {
        if (!key.includes(currentUserId)) {
          try {
            localStorage.removeItem(key);
          } catch (error) {
            console.warn(`[StorageHealthChecker] Failed to remove conflicting session key ${key}:`, error);
          }
        }
      });
    }
    
    console.log(`[StorageHealthChecker] Resolved session conflicts`);
  }
  
  /**
   */
  private fixSizeOverflow(): void {
    // Remove expired items first
    const now = Date.now();
    const expiredKeys: string[] = [];
    
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (!key) continue;
      
      try {
        const value = localStorage.getItem(key);
        if (!value) continue;
        
        const parsed = JSON.parse(value);
        if (parsed.expires_at && now > parsed.expires_at) {
          expiredKeys.push(key);
        }
      } catch (error) {
        // Ignore parsing errors
      }
    }
    
    expiredKeys.forEach(key => localStorage.removeItem(key));
    
    console.log(`[StorageHealthChecker] Removed ${expiredKeys.length} expired items to free space`);
  }
  
  /**
   * Generate detailed storage diagnostics
   */
  private generateDiagnostics(): StorageHealthDiagnostics {
    let totalSize = 0;
    let corruptedItems = 0;
    let orphanedItems = 0;
    let expiredItems = 0;
    let versionMismatches = 0;
    let sessionConflicts = 0;
    
    let largestItem = { key: '', size: 0 };
    let oldestItem = { key: '', age_hours: 0 };
    
    const now = Date.now();
    
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (!key) continue;
      
      const value = localStorage.getItem(key);
      if (!value) continue;
      
      const itemSize = key.length + value.length;
      totalSize += itemSize;
      
      // Track largest item
      if (itemSize > largestItem.size) {
        largestItem = { key, size: itemSize };
      }
      
      try {
        const parsed = JSON.parse(value);
        
        // Check age
        if (parsed.timestamp) {
          const ageHours = (now - parsed.timestamp) / (1000 * 60 * 60);
          if (ageHours > oldestItem.age_hours) {
            oldestItem = { key, age_hours: ageHours };
          }
          
          // Check if expired
          if (parsed.expires_at && now > parsed.expires_at) {
            expiredItems++;
          }
        }
        
        // Check version
        if (parsed.version && parsed.version !== '2.0.0') {
          versionMismatches++;
        }
        
      } catch (error) {
        corruptedItems++;
      }
    }
    
    return {
      total_size: totalSize,
      total_items: localStorage.length,
      corrupted_items: corruptedItems,
      orphaned_items: orphanedItems,
      expired_items: expiredItems,
      version_mismatches: versionMismatches,
      session_conflicts: sessionConflicts,
      largest_item: largestItem,
      oldest_item: oldestItem,
      storage_efficiency: totalSize > 0 ? ((totalSize - (corruptedItems + expiredItems) * 1000) / totalSize) * 100 : 100
    };
  }
  
  /**
   * Determine overall storage health
   */
  private determineOverallHealth(issues: StorageIssue[]): 'healthy' | 'degraded' | 'corrupted' | 'critical' {
    const criticalIssues = issues.filter(i => i.severity === 'critical').length;
    const highIssues = issues.filter(i => i.severity === 'high').length;
    const mediumIssues = issues.filter(i => i.severity === 'medium').length;
    
    if (criticalIssues > 0) return 'critical';
    if (highIssues > 2 || (highIssues > 0 && mediumIssues > 3)) return 'corrupted';
    if (highIssues > 0 || mediumIssues > 2) return 'degraded';
    
    return 'healthy';
  }
  
  /**
   * Generate recommendations based on issues and diagnostics
   */
  private generateRecommendations(issues: StorageIssue[], diagnostics: StorageHealthDiagnostics): string[] {
    const recommendations: string[] = [];
    
    const criticalIssues = issues.filter(i => i.severity === 'critical');
    if (criticalIssues.length > 0) {
      recommendations.push('Immediate action required: Perform emergency storage cleanup');
      recommendations.push('Consider using incognito mode temporarily');
    }
    
    // Storage size issues
    if (diagnostics.total_size > 4 * 1024 * 1024) { // > 4MB
      recommendations.push('Clear old cached data to free up storage space');
    }
    
    // Corruption issues
    if (diagnostics.corrupted_items > 5) {
      recommendations.push('Run storage integrity check and auto-fix');
    }
    
    // Session issues
    const sessionIssues = issues.filter(i => i.type === 'session_conflict');
    if (sessionIssues.length > 0) {
      recommendations.push('Clear conflicting session data and re-login');
    }
    
    // General maintenance
    if (diagnostics.expired_items > 10) {
      recommendations.push('Enable automatic cleanup of expired items');
    }
    
    if (recommendations.length === 0) {
      recommendations.push('Storage is healthy - no action required');
    }
    
    return recommendations;
  }
  
  /**
   * Start automatic health monitoring
   */
  private startHealthMonitoring(): void {
    // Initial health check after short delay
    setTimeout(() => {
      this.performHealthCheck({ autoFix: true });
    }, 5000);
    
    // Regular health checks
    this.healthCheckInterval = setInterval(() => {
      this.performHealthCheck({ autoFix: true });
    }, this.HEALTH_CHECK_INTERVAL);
  }
  
  /**
   * Stop health monitoring
   */
  stopHealthMonitoring(): void {
    if (this.healthCheckInterval) {
      clearInterval(this.healthCheckInterval);
      this.healthCheckInterval = null;
    }
  }
  
  /**
   * Get last health check timestamp
   */
  getLastHealthCheck(): number {
    return this.lastHealthCheck;
  }
}

// Export singleton instance
export const storageHealthChecker = StorageHealthChecker.getInstance();

// Make health checker available globally for debugging
if (typeof window !== 'undefined') {
  (window as any).storageHealthChecker = storageHealthChecker;
  (window as any).runStorageHealthCheck = () => storageHealthChecker.performHealthCheck({ autoFix: true, detailed: true });
}