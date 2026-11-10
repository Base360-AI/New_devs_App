# Property Revenue Dashboard – Bug Fixes

Summary of the issues reported by clients, their root causes, and how each was fixed.

---

## Bug 1 – Monthly revenue doesn't match client records (Client A – Sunset Properties)

**Symptom**
Sunset's March total for Beach House Alpha showed 1,000.00 from 3 bookings, while their records show 2,250.00 from 4 bookings.

**Root cause**
1. **Month boundaries were calculated in UTC instead of the property's local time.** One reservation checks in at 23:30 UTC on 29 February, which is 00:30 on 1 March in Paris, where the property is. The client correctly counts it as March, but the system put it in February.

**Fix**
- The monthly revenue calculation now converts each check-in date to the property's own timezone before deciding which month it belongs to.

---

## Bug 2 – Clients seeing another company's revenue (Client B – Ocean Rentals)

**Symptom**
When refreshing the dashboard, Ocean Rentals sometimes saw revenue that belonged to Sunset Properties.

**Root cause**
Revenue summaries are cached for 5 minutes, and the cache key contained only the property ID, not the tenant. Both clients have a property with the same ID (prop-001). Whichever client loaded it first filled the cache, and the other client was then shown that cached data.

**Fix**
The cache key now includes the tenant as well as the property ID, so each client's cached data is stored and read separately. After the fix, Ocean's prop-001 correctly shows 0.00 while Sunset's shows 2,250.00.

---

## Bug 3 – Totals "slightly off" by a few cents (Finance team)

**Symptom**
Some revenue totals were off by one cent, with no obvious pattern.

**Root cause**
Amounts are stored with three decimal places to track sub-cent values. The exact total was converted to a floating-point number in the backend and then rounded again with floating-point math in the frontend. Floats can't represent most decimal values exactly; for example, 128.015 is really stored as slightly less than that, so it rounds down to 128.01 instead of up to 128.02. This only affects some amounts, which is why the error looked random.

**Fix**
The total stays an exact decimal value throughout the calculation and is rounded once, to the cent, using standard half-up rounding before the API returns it. The frontend no longer rounds it again.

**Note**
Our totals add up exact amounts and round once at the end. If the finance team rounds each reservation to the cent before adding them up, their totals can still differ by a cent; for example, three bookings of 333.333, 333.333 and 333.334 give 1,000.00 our way and 999.99 their way. This is a business choice rather than a bug, and one convention should be agreed on and used everywhere.

---
