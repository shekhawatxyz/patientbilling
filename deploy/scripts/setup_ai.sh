#!/usr/bin/env bash
# Usage: GEMINI_KEY="AIza..." bash deploy/scripts/setup_ai.sh
# Key is read from env — never hardcoded.
set -euo pipefail

if [[ -z "${GEMINI_KEY:-}" ]]; then
  echo "ERROR: GEMINI_KEY env var not set."
  echo "Run: GEMINI_KEY=\"your-key\" bash deploy/scripts/setup_ai.sh"
  exit 1
fi

APP_UUID="496d3013-cdd0-4531-92fd-3646714463c1"
COOKIE=/tmp/zt_ai_setup
BASE="http://localhost:8000"

echo "==> Authenticating as platform admin..."
CSRF=$(curl -s -c "$COOKIE" "$BASE/auth/login/" \
  | grep -o 'csrfmiddlewaretoken" value="[^"]*"' \
  | grep -o 'value="[^"]*"' | cut -d'"' -f2)
curl -s -c "$COOKIE" -b "$COOKIE" -X POST "$BASE/auth/login/" \
  -H "X-CSRFToken: $CSRF" -H "Referer: $BASE/auth/login/" \
  -F "username=platform_admin@zango.dev" -F "password=Zango@123" \
  -F "csrfmiddlewaretoken=$CSRF" -o /dev/null
CSRF2=$(grep csrftoken "$COOKIE" | awk '{print $NF}')
echo "    Done."

echo "==> Creating Gemini AI provider..."
PROVIDER_RESP=$(curl -s -b "$COOKIE" -H "X-CSRFToken: $CSRF2" \
  -H "Content-Type: application/json" \
  -X POST "$BASE/api/v1/apps/$APP_UUID/ai/providers/" \
  -d "{
    \"name\": \"Gemini Flash\",
    \"provider_type\": \"openai\",
    \"base_url\": \"https://generativelanguage.googleapis.com/v1beta/openai/\",
    \"api_key\": \"$GEMINI_KEY\",
    \"default_model\": \"gemini-2.0-flash\"
  }")
echo "    Response: $PROVIDER_RESP"
PROVIDER_ID=$(echo "$PROVIDER_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id') or d.get('data',{}).get('id',''))" 2>/dev/null || true)
if [[ -z "$PROVIDER_ID" ]]; then
  # Try listing providers to find it
  echo "    Creation response unclear, fetching provider list..."
  PROVIDER_ID=$(curl -s -b "$COOKIE" "$BASE/api/v1/apps/$APP_UUID/ai/providers/" \
    | python3 -c "import sys,json; items=json.load(sys.stdin); [print(p['id']) for p in (items if isinstance(items,list) else items.get('results',items.get('data',[]))) if 'Gemini' in p.get('name','')]" 2>/dev/null | head -1)
fi
echo "    Provider ID: $PROVIDER_ID"

echo "==> Syncing AI tools..."
curl -s -b "$COOKIE" -H "X-CSRFToken: $CSRF2" \
  -X POST "$BASE/api/v1/apps/$APP_UUID/ai/tools/?action=sync_tools" | python3 -m json.tool 2>/dev/null || true

echo "==> Creating prompts..."
curl -s -b "$COOKIE" -H "X-CSRFToken: $CSRF2" -H "Content-Type: application/json" \
  -X POST "$BASE/api/v1/apps/$APP_UUID/ai/prompts/" \
  -d '{"name":"ClaimValidatorPrompt","content":"You are a medical billing validator. Given claim details, check: required fields present, ICD-10 diagnosis codes valid, CPT codes on all line items, amounts consistent. Return JSON only: {\"valid\": bool, \"issues\": [str], \"code_suggestions\": [str], \"completeness_score\": 0-100}. Claim ID: {{claim_id}}"}' \
  | python3 -m json.tool 2>/dev/null || true

curl -s -b "$COOKIE" -H "X-CSRFToken: $CSRF2" -H "Content-Type: application/json" \
  -X POST "$BASE/api/v1/apps/$APP_UUID/ai/prompts/" \
  -d '{"name":"DenialAnalyzerPrompt","content":"You are a medical billing denial expert. Analyze the denied claim and identify root cause. Return JSON only: {\"root_cause\": str, \"category\": \"eligibility|authorization|coding|duplicate|timely_filing|other\", \"corrective_actions\": [str]}. Claim ID: {{claim_id}}"}' \
  | python3 -m json.tool 2>/dev/null || true

curl -s -b "$COOKIE" -H "X-CSRFToken: $CSRF2" -H "Content-Type: application/json" \
  -X POST "$BASE/api/v1/apps/$APP_UUID/ai/prompts/" \
  -d '{"name":"AppealDrafterPrompt","content":"You are a medical billing appeals specialist. Write a formal appeal letter for the denied claim, referencing the denial reason and providing clinical justification. Claim ID: {{claim_id}}"}' \
  | python3 -m json.tool 2>/dev/null || true

echo "==> Creating agent records..."
curl -s -b "$COOKIE" -H "X-CSRFToken: $CSRF2" -H "Content-Type: application/json" \
  -X POST "$BASE/api/v1/apps/$APP_UUID/ai/agents/" \
  -d "{\"name\":\"ClaimValidator\",\"provider\":\"$PROVIDER_ID\",\"system_prompt\":\"ClaimValidatorPrompt\",\"tools\":[\"get_claim_details\",\"get_patient_insurance\",\"update_claim_ai_result\"]}" \
  | python3 -m json.tool 2>/dev/null || true

curl -s -b "$COOKIE" -H "X-CSRFToken: $CSRF2" -H "Content-Type: application/json" \
  -X POST "$BASE/api/v1/apps/$APP_UUID/ai/agents/" \
  -d "{\"name\":\"DenialAnalyzer\",\"provider\":\"$PROVIDER_ID\",\"system_prompt\":\"DenialAnalyzerPrompt\",\"tools\":[\"get_claim_details\",\"update_claim_ai_result\"]}" \
  | python3 -m json.tool 2>/dev/null || true

curl -s -b "$COOKIE" -H "X-CSRFToken: $CSRF2" -H "Content-Type: application/json" \
  -X POST "$BASE/api/v1/apps/$APP_UUID/ai/agents/" \
  -d "{\"name\":\"AppealDrafter\",\"provider\":\"$PROVIDER_ID\",\"system_prompt\":\"AppealDrafterPrompt\",\"tools\":[\"get_claim_details\",\"get_patient_insurance\",\"update_claim_ai_result\"]}" \
  | python3 -m json.tool 2>/dev/null || true

echo "==> Registering Celery tasks in App Panel..."
curl -s -b "$COOKIE" -H "X-CSRFToken: $CSRF2" -H "Content-Type: application/json" \
  -X POST "$BASE/api/v1/apps/$APP_UUID/tasks/" \
  -d '{"name":"backend.agents.tasks.run_claim_validator","description":"Validate claim completeness via AI"}' \
  | python3 -m json.tool 2>/dev/null || true

curl -s -b "$COOKIE" -H "X-CSRFToken: $CSRF2" -H "Content-Type: application/json" \
  -X POST "$BASE/api/v1/apps/$APP_UUID/tasks/" \
  -d '{"name":"backend.agents.tasks.run_denial_analyzer","description":"Analyze claim denial root cause via AI"}' \
  | python3 -m json.tool 2>/dev/null || true

curl -s -b "$COOKIE" -H "X-CSRFToken: $CSRF2" -H "Content-Type: application/json" \
  -X POST "$BASE/api/v1/apps/$APP_UUID/tasks/" \
  -d '{"name":"backend.agents.tasks.run_appeal_drafter","description":"Draft appeal letter for denied claim via AI"}' \
  | python3 -m json.tool 2>/dev/null || true

echo ""
echo "==> Restarting Celery..."
sg docker -c "docker compose -f /home/parakram/src/patientbilling/deploy/docker_compose.yml restart celery celery_beat"

echo ""
echo "========================================"
echo "DONE. Provider ID: $PROVIDER_ID"
echo "Next: submit a claim via the app UI, then check:"
echo "  sg docker -c \"docker compose -f /home/parakram/src/patientbilling/deploy/docker_compose.yml logs celery --tail=50\""
echo "========================================"
