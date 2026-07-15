#!/usr/bin/env bash
# TDD test — invoices module
set -uo pipefail

BASE="http://localhost:8000"
APP_HOST="patientbilling.localhost"
PASS=0; FAIL=0
RUN_ID=$(date +%s)

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

STAFF_EMAIL="staff@billing.local"
STAFF_PASS="Billing@123"

echo "=== invoices module tests ==="

# --- App user login ---
curl -s -c /tmp/zt_inv \
  -H "Host: $APP_HOST" \
  "$BASE/api/v1/appauth/login/" -o /dev/null
APP_CSRF=$(grep csrftoken /tmp/zt_inv | awk '{print $NF}')

LOGIN_RESP=$(curl -s -c /tmp/zt_inv -b /tmp/zt_inv \
  -H "Host: $APP_HOST" \
  -H "X-CSRFToken: $APP_CSRF" \
  -H "Content-Type: application/json" \
  -X POST "$BASE/api/v1/appauth/login/" \
  -d "{\"email\": \"$STAFF_EMAIL\", \"password\": \"$STAFF_PASS\"}")

if echo "$LOGIN_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if d.get('response',{}).get('data',{}).get('next_step',{}).get('id') == 'set_password' else 1)" 2>/dev/null; then
  NEW_CSRF=$(grep csrftoken /tmp/zt_inv | awk '{print $NF}')
  curl -s -c /tmp/zt_inv -b /tmp/zt_inv \
    -H "Host: $APP_HOST" \
    -H "X-CSRFToken: $NEW_CSRF" \
    -H "Content-Type: application/json" \
    -X POST "$BASE/api/v1/appauth/password/set/" \
    -d "{\"new_password\": \"$STAFF_PASS\", \"confirm_password\": \"$STAFF_PASS\"}" -o /dev/null
fi
APP_CSRF=$(grep csrftoken /tmp/zt_inv | awk '{print $NF}')

# Test 1: /invoices/ endpoint accessible
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -b /tmp/zt_inv \
  -H "Host: $APP_HOST" \
  "$BASE/invoices/?view=table&action=get_table_data&page=1&page_size=10")
if [ "$STATUS" = "200" ]; then
  pass "GET /invoices/ returns HTTP 200"
else
  fail "GET /invoices/ returned $STATUS (expected 200)"
fi

# Test 2: Create Invoice (need a Patient first)
PT_RESP=$(curl -s -b /tmp/zt_inv \
  -H "Host: $APP_HOST" \
  "$BASE/patients/?view=table&action=get_table_data&page=1&page_size=10")
PATIENT_PK=$(echo "$PT_RESP" | python3 -c "
import sys,json; d=json.load(sys.stdin)
records = d.get('data', [])
if records: print(records[0].get('pk',''))
" 2>/dev/null || echo "")

if [ -z "$PATIENT_PK" ]; then
  PT_CREATE=$(curl -s -b /tmp/zt_inv \
    -H "Host: $APP_HOST" \
    -H "X-CSRFToken: $APP_CSRF" \
    -X POST "$BASE/patients/?form_type=create_form" \
    -F "first_name=Invoice" -F "last_name=TestPatient" \
    -F "date_of_birth=1990-01-01" -F "email=invtest@test.com")
  PT_UUID=$(echo "$PT_CREATE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['response'].get('object_uuid',''))" 2>/dev/null)
  PT_RESP2=$(curl -s -b /tmp/zt_inv \
    -H "Host: $APP_HOST" \
    "$BASE/patients/?view=table&action=get_table_data&page=1&page_size=50")
  PATIENT_PK=$(echo "$PT_RESP2" | python3 -c "
import sys,json; d=json.load(sys.stdin)
for r in d.get('data', []):
    if str(r.get('object_uuid','')) == '$PT_UUID':
        print(r.get('pk',''))
        break
" 2>/dev/null || echo "")
fi

INV_NUM="INV-$RUN_ID"
INV_RESP=$(curl -s -b /tmp/zt_inv \
  -H "Host: $APP_HOST" \
  -H "X-CSRFToken: $APP_CSRF" \
  -X POST "$BASE/invoices/?form_type=create_form" \
  -F "patient=$PATIENT_PK" \
  -F "invoice_number=$INV_NUM" \
  -F "date_issued=2026-07-01" \
  -F "due_date=2026-07-31" \
  -F "total_amount=350.00" \
  -F "notes=Test invoice")
if echo "$INV_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('success') == True" 2>/dev/null; then
  pass "POST /invoices/ create Invoice succeeds (patient=$PATIENT_PK)"
  INV_UUID=$(echo "$INV_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['response'].get('object_uuid',''))" 2>/dev/null)
else
  fail "POST /invoices/ failed: ${INV_RESP:0:300}"
  INV_UUID=""
fi

# Test 3: Invoice starts in Draft state
if [ -n "$INV_UUID" ]; then
  INV_DATA=$(curl -s -b /tmp/zt_inv \
    -H "Host: $APP_HOST" \
    "$BASE/invoices/?view=table&action=get_table_data&page=1&page_size=50")
  INV_STATUS=$(echo "$INV_DATA" | python3 -c "
import sys,json; d=json.load(sys.stdin)
for row in d.get('data', []):
    if str(row.get('object_uuid','')) == '$INV_UUID':
        print(row.get('workflow_status',''))
        break
" 2>/dev/null || echo "")
  if echo "$INV_STATUS" | python3 -c "import sys; s=sys.stdin.read().strip().lower(); exit(0 if 'draft' in s else 1)" 2>/dev/null; then
    pass "Invoice initial workflow status is Draft"
  else
    fail "Invoice workflow status is '$INV_STATUS' (expected Draft)"
  fi
fi

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
