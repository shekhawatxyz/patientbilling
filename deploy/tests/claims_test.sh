#!/usr/bin/env bash
# TDD test — claims module
set -uo pipefail

BASE="http://localhost:8000"
APP_HOST="patientbilling.localhost"
PASS=0; FAIL=0
RUN_ID=$(date +%s)

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

STAFF_EMAIL="staff@billing.local"
STAFF_PASS="Billing@123"

echo "=== claims module tests ==="

# --- App user login ---
curl -s -c /tmp/zt_app \
  -H "Host: $APP_HOST" \
  "$BASE/api/v1/appauth/login/" -o /dev/null
APP_CSRF=$(grep csrftoken /tmp/zt_app | awk '{print $NF}')

LOGIN_RESP=$(curl -s -c /tmp/zt_app -b /tmp/zt_app \
  -H "Host: $APP_HOST" \
  -H "X-CSRFToken: $APP_CSRF" \
  -H "Content-Type: application/json" \
  -X POST "$BASE/api/v1/appauth/login/" \
  -d "{\"email\": \"$STAFF_EMAIL\", \"password\": \"$STAFF_PASS\"}")

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

# Test 1: /payers/ endpoint accessible
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -b /tmp/zt_app \
  -H "Host: $APP_HOST" \
  "$BASE/payers/?view=table&action=get_table_data&page=1&page_size=10")
if [ "$STATUS" = "200" ]; then
  pass "GET /payers/ returns HTTP 200"
else
  fail "GET /payers/ returned $STATUS (expected 200)"
fi

# Test 2: Create InsurancePayer (idempotent — fixed payer_id)
PAYER_RESP=$(curl -s -b /tmp/zt_app \
  -H "Host: $APP_HOST" \
  -H "X-CSRFToken: $APP_CSRF" \
  -X POST "$BASE/payers/?form_type=create_form" \
  -F "name=Blue Cross Blue Shield" \
  -F "payer_id=BCBS001" \
  -F "contact_email=claims@bcbs.com")
if echo "$PAYER_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('success') == True" 2>/dev/null; then
  pass "POST /payers/ create InsurancePayer succeeds"
else
  # May already exist from a prior run — that's fine, we'll look it up
  if echo "$PAYER_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'already exists' in str(d)" 2>/dev/null; then
    pass "POST /payers/ InsurancePayer already exists (idempotent)"
  else
    fail "POST /payers/ failed: ${PAYER_RESP:0:200}"
  fi
fi
# Always look up the payer pk by payer_id (works whether just created or pre-existing)
PAYER_TABLE=$(curl -s -b /tmp/zt_app \
  -H "Host: $APP_HOST" \
  "$BASE/payers/?view=table&action=get_table_data&page=1&page_size=50")
PAYER_PK=$(echo "$PAYER_TABLE" | python3 -c "
import sys,json; d=json.load(sys.stdin)
for r in d.get('data', []):
    if r.get('payer_id') == 'BCBS001':
        print(r.get('pk', ''))
        break
" 2>/dev/null || echo "")

# Test 3: /claims/ endpoint accessible
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -b /tmp/zt_app \
  -H "Host: $APP_HOST" \
  "$BASE/claims/?view=table&action=get_table_data&page=1&page_size=10")
if [ "$STATUS" = "200" ]; then
  pass "GET /claims/ returns HTTP 200"
else
  fail "GET /claims/ returned $STATUS (expected 200)"
fi

# Test 4: Create a Claim
# Get patient pk from table (or create one)
PT_RESP=$(curl -s -b /tmp/zt_app \
  -H "Host: $APP_HOST" \
  "$BASE/patients/?view=table&action=get_table_data&page=1&page_size=10")
PATIENT_PK=$(echo "$PT_RESP" | python3 -c "
import sys,json; d=json.load(sys.stdin)
records = d.get('data', [])
if records: print(records[0].get('pk',''))
" 2>/dev/null || echo "")

if [ -z "$PATIENT_PK" ]; then
  PT_CREATE=$(curl -s -b /tmp/zt_app \
    -H "Host: $APP_HOST" \
    -H "X-CSRFToken: $APP_CSRF" \
    -X POST "$BASE/patients/?form_type=create_form" \
    -F "first_name=Claim" -F "last_name=TestPatient" \
    -F "date_of_birth=1985-06-15" -F "email=claimtest@test.com")
  PT_UUID=$(echo "$PT_CREATE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['response'].get('object_uuid',''))" 2>/dev/null)
  PT_RESP2=$(curl -s -b /tmp/zt_app \
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

CLAIM_NUM="CLM-$RUN_ID"
CLAIM_RESP=$(curl -s -b /tmp/zt_app \
  -H "Host: $APP_HOST" \
  -H "X-CSRFToken: $APP_CSRF" \
  -X POST "$BASE/claims/?form_type=create_form" \
  -F "patient=$PATIENT_PK" \
  -F "payer=$PAYER_PK" \
  -F "claim_number=$CLAIM_NUM" \
  -F "date_of_service=2026-07-01" \
  -F "diagnosis_codes=[\"Z00.00\"]" \
  -F "total_amount=500.00" \
  -F "notes=Test claim")
if echo "$CLAIM_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('success') == True" 2>/dev/null; then
  pass "POST /claims/ create Claim succeeds (patient=$PATIENT_PK payer=$PAYER_PK)"
  CLAIM_UUID=$(echo "$CLAIM_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['response'].get('object_uuid',''))" 2>/dev/null)
else
  fail "POST /claims/ failed: ${CLAIM_RESP:0:300}"
  CLAIM_UUID=""
fi

# Test 5: Claim starts in Draft workflow state
if [ -n "$CLAIM_UUID" ]; then
  CLAIM_DATA=$(curl -s -b /tmp/zt_app \
    -H "Host: $APP_HOST" \
    "$BASE/claims/?view=table&action=get_table_data&page=1&page_size=50")
  CLAIM_STATUS=$(echo "$CLAIM_DATA" | python3 -c "
import sys,json; d=json.load(sys.stdin)
for row in d.get('data', []):
    if str(row.get('object_uuid','')) == '$CLAIM_UUID':
        print(row.get('workflow_status',''))
        break
" 2>/dev/null || echo "")
  if echo "$CLAIM_STATUS" | python3 -c "import sys; s=sys.stdin.read().strip().lower(); exit(0 if 'draft' in s else 1)" 2>/dev/null; then
    pass "Claim initial workflow status is Draft"
  else
    fail "Claim workflow status is '$CLAIM_STATUS' (expected Draft)"
  fi
fi

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
