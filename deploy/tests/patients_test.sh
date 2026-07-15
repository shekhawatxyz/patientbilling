#!/usr/bin/env bash
# TDD test — patients module
set -uo pipefail

BASE="http://localhost:8000"
APP_HOST="patientbilling.localhost"
PASS=0; FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

APP_UUID="496d3013-cdd0-4531-92fd-3646714463c1"
STAFF_EMAIL="staff@billing.local"
STAFF_PASS="Billing@123"

echo "=== patients module tests ==="

# --- App user login (BillingStaff) ---
# Step 1: Get CSRF for app domain
curl -s -c /tmp/zt_app \
  -H "Host: $APP_HOST" \
  "$BASE/api/v1/appauth/login/" -o /dev/null
APP_CSRF=$(grep csrftoken /tmp/zt_app | awk '{print $NF}')

# Step 2: Login
LOGIN_RESP=$(curl -s -c /tmp/zt_app -b /tmp/zt_app \
  -H "Host: $APP_HOST" \
  -H "X-CSRFToken: $APP_CSRF" \
  -H "Content-Type: application/json" \
  -X POST "$BASE/api/v1/appauth/login/" \
  -d "{\"email\": \"$STAFF_EMAIL\", \"password\": \"$STAFF_PASS\"}")

# Step 3: If set_password pending, complete it
if echo "$LOGIN_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if d.get('response',{}).get('data',{}).get('next_step',{}).get('id') == 'set_password' else 1)" 2>/dev/null; then
  NEW_CSRF=$(grep csrftoken /tmp/zt_app | awk '{print $NF}')
  curl -s -c /tmp/zt_app -b /tmp/zt_app \
    -H "Host: $APP_HOST" \
    -H "X-CSRFToken: $NEW_CSRF" \
    -H "Content-Type: application/json" \
    -X POST "$BASE/api/v1/appauth/password/set/" \
    -d "{\"new_password\": \"$STAFF_PASS\", \"confirm_password\": \"$STAFF_PASS\"}" -o /dev/null
fi

APP_CSRF=$(grep csrftoken /tmp/zt_app | awk '{print $NF}')

# Test 1: /patients/ returns 200 (not 404 or 500) — module is registered
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -b /tmp/zt_app \
  -H "Host: $APP_HOST" \
  "$BASE/patients/?view=table&action=get_table_data&page=1&page_size=10")
if [ "$STATUS" = "200" ]; then
  pass "GET /patients/ returns HTTP 200 (module registered, auth working)"
else
  fail "GET /patients/ returned $STATUS (expected 200)"
fi

# Test 2: GET table data returns JSON with records field
RESP=$(curl -s -b /tmp/zt_app \
  -H "Host: $APP_HOST" \
  "$BASE/patients/?view=table&action=get_table_data&page=1&page_size=10")
if echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'data' in d" 2>/dev/null; then
  pass "GET table response has 'data' field"
else
  fail "GET table response missing 'data': ${RESP:0:200}"
fi

# Test 3: POST create patient
RESP=$(curl -s -b /tmp/zt_app \
  -H "Host: $APP_HOST" \
  -H "X-CSRFToken: $APP_CSRF" \
  -X POST "$BASE/patients/?form_type=create_form" \
  -F "first_name=Test" -F "last_name=Patient" \
  -F "date_of_birth=1990-01-01" \
  -F "email=test@example.com" \
  -F "phone=+15555550100" \
  -F "address=123 Main St" \
  -F "insurance_provider=Blue Cross" \
  -F "insurance_policy_number=BC123456" \
  -F "insurance_group_number=GRP001")
if echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('success') == True" 2>/dev/null; then
  pass "POST /patients/ create_form succeeds"
else
  fail "POST /patients/ create_form failed: ${RESP:0:300}"
fi

# Test 4: GET table data returns at least 1 record
RESP=$(curl -s -b /tmp/zt_app \
  -H "Host: $APP_HOST" \
  "$BASE/patients/?view=table&action=get_table_data&page=1&page_size=10")
COUNT=$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('recordsTotal', 0))" 2>/dev/null || echo "0")
if [ "$COUNT" -ge "1" ] 2>/dev/null; then
  pass "GET /patients/ table returns $COUNT record(s)"
else
  fail "GET /patients/ table returned 0 records: ${RESP:0:200}"
fi

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
