export interface DashboardSummaryOptions {
  simulatedTenant?: string;
  tenantId?: string;
  timestamp?: number;
  year?: number;
  month?: number;
}

export function buildDashboardSummaryRequest(
  propertyId: string,
  options?: DashboardSummaryOptions,
): { url: string; headers: Record<string, string> } {
  const queryParams = new URLSearchParams({ property_id: propertyId });
  if (options?.timestamp) {
    queryParams.append("_t", options.timestamp.toString());
  }
  if (options?.year) {
    queryParams.append("year", String(options.year));
  }
  if (options?.month) {
    queryParams.append("month", String(options.month));
  }

  const headers: Record<string, string> = {};
  if (options?.simulatedTenant) {
    headers["X-Simulated-Tenant"] = options.simulatedTenant;
  }

  return {
    url: `/api/v1/dashboard/summary?${queryParams.toString()}`,
    headers,
  };
}
