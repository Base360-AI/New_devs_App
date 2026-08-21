export const TENANT_A = "tenant-a";
export const TENANT_B = "tenant-b";
export const SHARED_PROPERTY_ID = "prop-001";
export const PARIS_TZ = "Europe/Paris";
export const NEW_YORK_TZ = "America/New_York";
export const RES_TZ_1_CHECK_IN = "2024-02-29T23:30:00.000Z";

export const TENANT_A_MARCH_TOTAL = 2250;
export const TENANT_A_BOOKINGS = [
  { check_in: "2024-03-05T10:00:00.000Z", amount: 250 },
  { check_in: "2024-03-12T10:00:00.000Z", amount: 250 },
  { check_in: "2024-03-20T10:00:00.000Z", amount: 500 },
  { check_in: RES_TZ_1_CHECK_IN, amount: 1250 },
];

export const TENANT_A_REVENUE = {
  property_id: SHARED_PROPERTY_ID,
  total_revenue: TENANT_A_MARCH_TOTAL,
  currency: "USD",
  reservations_count: 4,
};

export const TENANT_B_REVENUE = {
  property_id: SHARED_PROPERTY_ID,
  total_revenue: 0,
  currency: "USD",
  reservations_count: 0,
};

export function revenueForSimulatedTenant(simulatedTenant?: string) {
  if (simulatedTenant === TENANT_B) {
    return TENANT_B_REVENUE;
  }
  return TENANT_A_REVENUE;
}
