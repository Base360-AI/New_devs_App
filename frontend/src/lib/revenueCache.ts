const store = new Map<string, unknown>();

export function revenueCacheKey(propertyId: string, tenantId: string): string {
  return `revenue:${propertyId}:tenant:${tenantId}`;
}

export function setRevenueCache(propertyId: string, tenantId: string, value: unknown): void {
  store.set(revenueCacheKey(propertyId, tenantId), value);
}

export function getRevenueCache(propertyId: string, tenantId: string): unknown {
  return store.get(revenueCacheKey(propertyId, tenantId));
}

export function clearRevenueCacheForTenant(tenantId: string): void {
  const suffix = `:tenant:${tenantId}`;
  for (const key of [...store.keys()]) {
    if (key.endsWith(suffix)) {
      store.delete(key);
    }
  }
}

export function clearAllRevenueCache(): void {
  store.clear();
}

export function revenueCacheSize(): number {
  return store.size;
}

export function revenueCacheKeys(): string[] {
  return [...store.keys()];
}
