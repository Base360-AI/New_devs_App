#!/bin/bash
# PR-based Loom demo driver: ONLY live proofs (code diffs are shown on the PR page).
# Run in a BIG-FONT terminal. Press ENTER to advance. Test: AUTO=1 ./demo_pr.sh

API=http://localhost:8000/api/v1
dc() { docker compose "$@" 2>/dev/null; }

pause() {
  if [ -z "$AUTO" ]; then
    echo
    read -r -p "--- press ENTER for next step ---"
    clear
  else
    echo; echo "=========================================="; echo
  fi
}

step() {
  echo
  echo "############################################################"
  echo "##  $1"
  echo "############################################################"
  echo
}

clear
step "SETUP - logging in both tenants, clearing cache"
dc exec -T redis redis-cli flushall >/dev/null
TOKEN_A=$(curl -s -X POST $API/auth/login -H 'Content-Type: application/json' -d '{"email":"sunset@propertyflow.com","password":"client_a_2024"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
TOKEN_B=$(curl -s -X POST $API/auth/login -H 'Content-Type: application/json' -d '{"email":"ocean@propertyflow.com","password":"client_b_2024"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
echo "Logged in: Sunset Properties (tenant-a) + Ocean Rentals (tenant-b)."
echo "READY - start recording, talk over the PR page first, come back here for proofs."
pause

step "PROOF 1 - what the database ACTUALLY contains vs what the API returns"
echo ">> Database ground truth:"
dc exec -T db psql -U postgres -d propertyflow -c \
  "SELECT tenant_id, property_id, COUNT(*) AS reservations, SUM(total_amount) AS total FROM reservations GROUP BY 1,2 ORDER BY 1,2;"
echo ">> API response for prop-001 as Sunset Properties (was mock 1000.00/3 before the fix):"
curl -s "$API/dashboard/summary?property_id=prop-001" -H "Authorization: Bearer $TOKEN_A" | python3 -m json.tool
pause

step "PROOF 2 - tenant isolation: both tenants own 'prop-001'"
echo "\$ Tenant A queries prop-001 (populates the cache):"
curl -s "$API/dashboard/summary?property_id=prop-001" -H "Authorization: Bearer $TOKEN_A" | python3 -m json.tool
echo
echo "\$ Tenant B queries the SAME property_id immediately after:"
curl -s "$API/dashboard/summary?property_id=prop-001" -H "Authorization: Bearer $TOKEN_B" | python3 -m json.tool
echo
echo "\$ Redis keys are now tenant-scoped:"
dc exec -T redis redis-cli keys 'revenue:*'
echo
echo ">> Before the fix, B received A's cached 2250.00 here."
pause

step "PROOF 3 - the timezone reservation: Feb 29 UTC = March 1 in Paris"
dc exec -T db psql -U postgres -d propertyflow -c \
  "SELECT id, check_in_date AS utc_checkin, check_in_date AT TIME ZONE 'Europe/Paris' AS paris_local, total_amount FROM reservations WHERE id='res-tz-1';"
echo ">> March totals, old vs new bucketing:"
dc exec -T db psql -U postgres -d propertyflow -c \
  "SELECT 'UTC (buggy)' AS method, SUM(total_amount) AS march_total FROM reservations WHERE property_id='prop-001' AND tenant_id='tenant-a' AND check_in_date >= '2024-03-01' AND check_in_date < '2024-04-01';"
dc exec -T db psql -U postgres -d propertyflow -c \
  "SELECT 'property tz (fixed)' AS method, SUM(r.total_amount) AS march_total FROM reservations r JOIN properties p ON p.id=r.property_id AND p.tenant_id=r.tenant_id WHERE r.property_id='prop-001' AND r.tenant_id='tenant-a' AND EXTRACT(YEAR FROM (r.check_in_date AT TIME ZONE p.timezone))=2024 AND EXTRACT(MONTH FROM (r.check_in_date AT TIME ZONE p.timezone))=3;"
echo ">> 1000 vs 2250 - the missing 1250 is exactly the client's March gap."
pause

step "PROOF 4 - floats can't represent money"
echo "\$ python3 -c 'print(0.1 + 0.2)'"
python3 -c "print(0.1 + 0.2)"
echo
echo ">> API now serializes money as an exact decimal string:"
curl -s "$API/dashboard/summary?property_id=prop-002" -H "Authorization: Bearer $TOKEN_A" | python3 -m json.tool
pause

step "DONE - switch to the browser for the final dashboard views"
echo "Window 1 (Sunset Properties) and Window 2 incognito (Ocean Rentals): http://localhost:3000"
