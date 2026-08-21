import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { formatInUserTimezone, displayTimezone } from "../src/lib/userTimezone";
import { isCheckInInMonth, sumRevenueInMonth } from "../src/lib/propertyMonthWindow";
import {
  NEW_YORK_TZ,
  PARIS_TZ,
  RES_TZ_1_CHECK_IN,
  TENANT_A_BOOKINGS,
  TENANT_A_MARCH_TOTAL,
} from "./fixtures";
import { loadFeatureCatalog } from "./featureLoader";

const OriginalDateTimeFormat = Intl.DateTimeFormat;

describe("Feature: User timezone vs property timezone", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "Intl",
      {
        ...Intl,
        DateTimeFormat: function MockDateTimeFormat(
          locales?: string | string[],
          options?: Intl.DateTimeFormatOptions,
        ) {
          return new OriginalDateTimeFormat(locales, {
            ...options,
            timeZone: options?.timeZone ?? PARIS_TZ,
          });
        },
      },
    );
    (Intl.DateTimeFormat as unknown as { supportedLocalesOf: typeof OriginalDateTimeFormat.supportedLocalesOf }).supportedLocalesOf =
      OriginalDateTimeFormat.supportedLocalesOf;
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("loads timezone scenarios from Gherkin", () => {
    const catalog = loadFeatureCatalog();
    const timezone = catalog.files.find((file) => file.endsWith("user-timezone.feature"));
    expect(timezone).toBeDefined();
  });

  it("Profile timezone differs from the browser", () => {
    expect(displayTimezone(NEW_YORK_TZ)).toBe(NEW_YORK_TZ);
    const formatted = formatInUserTimezone(RES_TZ_1_CHECK_IN, NEW_YORK_TZ);
    expect(formatted).toMatch(/Feb/);
    expect(formatted).not.toMatch(/Mar/);
  });

  it("Missing profile timezone", () => {
    expect(displayTimezone(undefined)).toBe("UTC");
    expect(displayTimezone(null)).toBe("UTC");
    expect(displayTimezone("")).toBe("UTC");
    const formatted = formatInUserTimezone(RES_TZ_1_CHECK_IN, undefined);
    expect(formatted).toMatch(/Feb 29/);
  });

  it("Paris property on a New York user includes res-tz-1 in March", () => {
    expect(isCheckInInMonth(RES_TZ_1_CHECK_IN, 2024, 3, PARIS_TZ)).toBe(true);
    expect(sumRevenueInMonth(TENANT_A_BOOKINGS, 2024, 3, PARIS_TZ)).toBe(TENANT_A_MARCH_TOTAL);
  });

  it("Browser zone must not shrink March", () => {
    expect(isCheckInInMonth(RES_TZ_1_CHECK_IN, 2024, 3, "UTC")).toBe(false);
    expect(isCheckInInMonth(RES_TZ_1_CHECK_IN, 2024, 3, PARIS_TZ)).toBe(true);
    expect(sumRevenueInMonth(TENANT_A_BOOKINGS, 2024, 3, PARIS_TZ)).toBe(TENANT_A_MARCH_TOTAL);
  });
});
