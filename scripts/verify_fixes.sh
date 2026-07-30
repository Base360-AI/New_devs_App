#!/usr/bin/env bash
# End-to-end verification of the revenue dashboard fixes.
#
# Usage:  docker compose up --build -d && ./scripts/verify_fixes.sh
#
# Every expected figure below was taken from the seeded database, not from the
# API, so the script fails if the API ever drifts away from the source data.
set -uo pipefail

API="${API:-http://localhost:8000}"
PASS=0
FAIL=0

login() {
  curl -s -X POST "$API/api/v1/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$1\",\"password\":\"$2\"}" |
    python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])'
}

check() {
  local label="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    printf '  \033[32mPASS\033[0m  %s\n' "$label"
    PASS=$((PASS + 1))
  else
    printf '  \033[31mFAIL\033[0m  %s\n        expected: %s\n        actual:   %s\n' "$label" "$expected" "$actual"
    FAIL=$((FAIL + 1))
  fi
}

summary() { # token, property, [month year]
  local token="$1" property="$2" query="property_id=$2"
  [ $# -gt 2 ] && query="$query&month=$3&year=$4"
  curl -s "$API/api/v1/dashboard/summary?$query" -H "Authorization: Bearer $token"
}

field() { python3 -c 'import sys,json; print(json.load(sys.stdin).get(sys.argv[1],"<missing>"))' "$1"; }

TOKEN_A=$(login sunset@propertyflow.com client_a_2024)
TOKEN_B=$(login ocean@propertyflow.com client_b_2024)

echo
echo "1. Tenant isolation - prop-001 exists for BOTH clients"
check "Sunset sees its own Beach House Alpha revenue" \
  "2250.00" "$(summary "$TOKEN_A" prop-001 | field total_revenue)"
check "Ocean sees its own Mountain Lodge Beta (no bookings), not Sunset's" \
  "0.00" "$(summary "$TOKEN_B" prop-001 | field total_revenue)"
check "Repeat read for Ocean is still Ocean's (cache is tenant-scoped)" \
  "0.00" "$(summary "$TOKEN_B" prop-001 | field total_revenue)"
check "Repeat read for Sunset is still Sunset's" \
  "2250.00" "$(summary "$TOKEN_A" prop-001 | field total_revenue)"
check "Sunset cannot read Ocean's prop-004" \
  "Property not found" "$(summary "$TOKEN_A" prop-004 | field detail)"
check "Ocean cannot read Sunset's prop-003" \
  "Property not found" "$(summary "$TOKEN_B" prop-003 | field detail)"
check "Unauthenticated requests are rejected" \
  "401" "$(curl -s -o /dev/null -w '%{http_code}' "$API/api/v1/dashboard/summary?property_id=prop-001")"

echo
echo "2. Timezone - months are counted in the property's local time"
check "Sunset prop-001 March 2024 (Paris) includes the 29 Feb 23:30 UTC check-in" \
  "2250.00" "$(summary "$TOKEN_A" prop-001 3 2024 | field total_revenue)"
check "...and that booking is counted (4 reservations, not 3)" \
  "4" "$(summary "$TOKEN_A" prop-001 3 2024 | field reservations_count)"
check "February 2024 is therefore empty" \
  "0.00" "$(summary "$TOKEN_A" prop-001 2 2024 | field total_revenue)"
check "Period is reported in the property's timezone" \
  "Europe/Paris" "$(summary "$TOKEN_A" prop-001 3 2024 | field timezone)"
check "Ocean's properties are evaluated in New York time" \
  "America/New_York" "$(summary "$TOKEN_B" prop-004 3 2024 | field timezone)"

echo
echo "3. Precision - sub-cent amounts sum exactly and round once"
check "Sunset prop-002 exact sum" \
  "4975.500" "$(summary "$TOKEN_A" prop-002 | field total_revenue_exact)"
check "Sunset prop-003 total" \
  "6100.50" "$(summary "$TOKEN_A" prop-003 | field total_revenue)"
check "Ocean prop-004 total" \
  "1776.50" "$(summary "$TOKEN_B" prop-004 | field total_revenue)"
check "Ocean prop-005 total" \
  "3256.00" "$(summary "$TOKEN_B" prop-005 | field total_revenue)"
check "prop-001's three 333.33x bookings total 1000.000, not 999.99" \
  "1000.000" "$(summary "$TOKEN_A" prop-001 3 2024 | python3 -c '
import sys, json
from decimal import Decimal
data = json.load(sys.stdin)
# The 1250.00 timezone booking plus the three sub-cent ones.
print(Decimal(data["total_revenue_exact"]) - Decimal("1250.000"))')"

echo
echo "4. Property list is scoped to the caller's tenant"
check "Sunset sees only its 3 properties" \
  "prop-001,prop-002,prop-003" \
  "$(curl -s "$API/api/v1/dashboard/properties" -H "Authorization: Bearer $TOKEN_A" |
    python3 -c 'import sys,json; print(",".join(sorted(p["id"] for p in json.load(sys.stdin)["properties"])))')"
check "Ocean sees only its 3 properties" \
  "prop-001,prop-004,prop-005" \
  "$(curl -s "$API/api/v1/dashboard/properties" -H "Authorization: Bearer $TOKEN_B" |
    python3 -c 'import sys,json; print(",".join(sorted(p["id"] for p in json.load(sys.stdin)["properties"])))')"

echo
printf '%s passed, %s failed\n\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
