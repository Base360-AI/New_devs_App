import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RevenueSummary } from "../src/components/RevenueSummary";
import { buildDashboardSummaryRequest } from "../src/lib/dashboardSummaryRequest";
import {
  clearAllRevenueCache,
  getRevenueCache,
  revenueCacheKey,
  revenueCacheKeys,
  setRevenueCache,
} from "../src/lib/revenueCache";
import {
  SHARED_PROPERTY_ID,
  TENANT_A,
  TENANT_A_REVENUE,
  TENANT_B,
  TENANT_B_REVENUE,
  revenueForSimulatedTenant,
} from "./fixtures";
import { loadFeatureCatalog } from "./featureLoader";

const getDashboardSummary = vi.fn();

vi.mock("../src/lib/secureApi", () => ({
  SecureAPI: {
    getDashboardSummary: (...args: unknown[]) => getDashboardSummary(...args),
  },
}));

describe("Feature: Frontend tenant isolation", () => {
  beforeEach(() => {
    clearAllRevenueCache();
    getDashboardSummary.mockReset();
    getDashboardSummary.mockImplementation(
      (_propertyId: string, options?: { simulatedTenant?: string; tenantId?: string }) =>
        Promise.resolve(revenueForSimulatedTenant(options?.simulatedTenant ?? options?.tenantId)),
    );
  });

  it("loads isolation scenarios from Gherkin", () => {
    const catalog = loadFeatureCatalog();
    const isolation = catalog.files.find((file) => file.endsWith("frontend-tenant-isolation.feature"));
    expect(isolation).toBeDefined();
    expect(catalog.scenarioCount).toBeGreaterThanOrEqual(5);
  });

  it("Sunset user loads the default property", async () => {
    render(<RevenueSummary propertyId={SHARED_PROPERTY_ID} sessionTenant={TENANT_A} />);

    await waitFor(() => expect(getDashboardSummary).toHaveBeenCalled());
    const [, options] = getDashboardSummary.mock.calls[0];
    const request = buildDashboardSummaryRequest(SHARED_PROPERTY_ID, options);

    expect(request.url).toContain(`property_id=${SHARED_PROPERTY_ID}`);
    expect(options.tenantId).toBe(TENANT_A);
    expect(options.simulatedTenant).toBeUndefined();
    expect(request.headers["X-Simulated-Tenant"]).toBeUndefined();
    expect(await screen.findByTestId("revenue-total")).toHaveTextContent("2,250.00");
  });

  it("Ocean user loads the same property id", async () => {
    render(<RevenueSummary propertyId={SHARED_PROPERTY_ID} sessionTenant={TENANT_B} />);

    await waitFor(() => expect(getDashboardSummary).toHaveBeenCalled());
    const [, options] = getDashboardSummary.mock.calls[0];
    const request = buildDashboardSummaryRequest(SHARED_PROPERTY_ID, options);

    expect(request.url).toContain(`property_id=${SHARED_PROPERTY_ID}`);
    expect(options.tenantId).toBe(TENANT_B);
    expect(options.simulatedTenant).toBeUndefined();
    expect(request.headers["X-Simulated-Tenant"]).toBeUndefined();
    expect(await screen.findByTestId("revenue-total")).toHaveTextContent("0.00");
    expect(screen.queryByTestId("revenue-total")).not.toHaveTextContent("2,250.00");
  });

  it("No simulated-tenant override on a real session", async () => {
    render(<RevenueSummary propertyId={SHARED_PROPERTY_ID} sessionTenant={TENANT_A} />);

    await waitFor(() => expect(getDashboardSummary).toHaveBeenCalled());
    const [, options] = getDashboardSummary.mock.calls[0];
    const request = buildDashboardSummaryRequest(SHARED_PROPERTY_ID, options);

    expect(options.simulatedTenant).toBeUndefined();
    expect(request.headers["X-Simulated-Tenant"]).toBeUndefined();
    expect(JSON.stringify(request.headers)).not.toContain("candidate");
  });

  it("Refresh after switching companies", () => {
    setRevenueCache(SHARED_PROPERTY_ID, TENANT_A, TENANT_A_REVENUE);
    expect(getRevenueCache(SHARED_PROPERTY_ID, TENANT_A)).toEqual(TENANT_A_REVENUE);

    expect(getRevenueCache(SHARED_PROPERTY_ID, TENANT_B)).not.toEqual(TENANT_A_REVENUE);
    expect(getRevenueCache(SHARED_PROPERTY_ID, TENANT_B)).toBeUndefined();
  });

  it("Concurrent tabs with a shared property id", () => {
    setRevenueCache(SHARED_PROPERTY_ID, TENANT_A, TENANT_A_REVENUE);
    setRevenueCache(SHARED_PROPERTY_ID, TENANT_B, TENANT_B_REVENUE);

    expect(revenueCacheKey(SHARED_PROPERTY_ID, TENANT_A)).toContain(TENANT_A);
    expect(revenueCacheKey(SHARED_PROPERTY_ID, TENANT_B)).toContain(TENANT_B);
    expect(revenueCacheKey(SHARED_PROPERTY_ID, TENANT_A)).not.toBe(
      revenueCacheKey(SHARED_PROPERTY_ID, TENANT_B),
    );
    expect(revenueCacheKeys()).toHaveLength(2);
    expect(getRevenueCache(SHARED_PROPERTY_ID, TENANT_A)).toEqual(TENANT_A_REVENUE);
    expect(getRevenueCache(SHARED_PROPERTY_ID, TENANT_B)).toEqual(TENANT_B_REVENUE);
  });
});
