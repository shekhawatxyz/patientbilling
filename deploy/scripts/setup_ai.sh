#!/usr/bin/env bash
# Configure Gemini AI provider + prompts + agents in the Zango App Panel.
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

# ── Auth ──────────────────────────────────────────────────────────────────────
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

# ── Install Gemini provider into running container (if not already installed) ─
echo "==> Checking/installing Gemini provider in container..."
ALREADY_INSTALLED=$(sg docker -c "docker compose -f /home/parakram/src/patientbilling/deploy/docker_compose.yml exec -T app python3 -c '
from zango.ai.providers.registry import PROVIDER_REGISTRY
print(\"yes\" if \"gemini\" in PROVIDER_REGISTRY else \"no\")
'" 2>/dev/null | tr -d '[:space:]')

if [ "$ALREADY_INSTALLED" != "yes" ]; then
    echo "    Installing..."
    sg docker -c "docker compose -f /home/parakram/src/patientbilling/deploy/docker_compose.yml exec -T app bash -c '
PROVIDERS_DIR=\$(python3 -c \"import zango.ai.providers, os; print(os.path.dirname(zango.ai.providers.__file__))\")
sudo cp /zango/providers/gemini.py \"\$PROVIDERS_DIR/gemini.py\" 2>/dev/null || cp /zango/providers/gemini.py \"\$PROVIDERS_DIR/gemini.py\"
if ! grep -q \"from . import gemini\" \"\$PROVIDERS_DIR/__init__.py\" 2>/dev/null; then
    printf \"\ntry:\n    from . import gemini  # noqa: F401\nexcept ImportError:\n    pass\n\" | sudo tee -a \"\$PROVIDERS_DIR/__init__.py\" > /dev/null 2>/dev/null || printf \"\ntry:\n    from . import gemini  # noqa: F401\nexcept ImportError:\n    pass\n\" >> \"\$PROVIDERS_DIR/__init__.py\"
fi
echo \"    Installed at \$PROVIDERS_DIR/gemini.py\"
'"

    # Restart app to pick up the new provider
    echo "==> Restarting app container (waiting up to 60s for it to be ready)..."
    sg docker -c "docker compose -f /home/parakram/src/patientbilling/deploy/docker_compose.yml restart app"

    # Poll until app is ready
    for i in $(seq 1 60); do
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/auth/login/" 2>/dev/null)
        if [ "$HTTP_CODE" = "200" ]; then
            echo "    App ready after ${i}s"
            break
        fi
        sleep 1
    done

    # Re-auth after restart
    CSRF=$(curl -s -c "$COOKIE" "$BASE/auth/login/" \
      | grep -o 'csrfmiddlewaretoken" value="[^"]*"' \
      | grep -o 'value="[^"]*"' | cut -d'"' -f2)
    curl -s -c "$COOKIE" -b "$COOKIE" -X POST "$BASE/auth/login/" \
      -H "X-CSRFToken: $CSRF" -H "Referer: $BASE/auth/login/" \
      -F "username=platform_admin@zango.dev" -F "password=Zango@123" \
      -F "csrfmiddlewaretoken=$CSRF" -o /dev/null
    CSRF2=$(grep csrftoken "$COOKIE" | awk '{print $NF}')
else
    echo "    Gemini already installed — skipping restart"
fi

# ── Create Gemini provider ────────────────────────────────────────────────────
echo "==> Creating Gemini AI provider..."
PROVIDER_RESP=$(curl -s -b "$COOKIE" -H "X-CSRFToken: $CSRF2" \
  -H "Content-Type: application/json" \
  -X POST "$BASE/api/v1/apps/$APP_UUID/ai/providers/" \
  -d "{
    \"name\": \"Gemini Flash\",
    \"provider_slug\": \"gemini\",
    \"config\": {\"api_key\": \"$GEMINI_KEY\"},
    \"default_model\": \"gemini-2.0-flash\"
  }")
echo "    Response: $PROVIDER_RESP"
PROVIDER_ID=$(echo "$PROVIDER_RESP" | python3 -c "
import sys, json
d = json.load(sys.stdin)
# Check both common response shapes
v = d.get('response', d)
print(v.get('id') or v.get('provider', {}).get('id') or '')
" 2>/dev/null || true)

if [[ -z "$PROVIDER_ID" ]]; then
  echo "    Creation unclear — fetching provider list..."
  PROVIDER_ID=$(curl -s -b "$COOKIE" "$BASE/api/v1/apps/$APP_UUID/ai/providers/" \
    | python3 -c "
import sys, json
data = json.load(sys.stdin)
records = data.get('response', {}).get('providers', {}).get('records', [])
for p in records:
    if p.get('provider_slug') == 'gemini' or 'Gemini' in p.get('name', ''):
        print(p['id']); break
" 2>/dev/null || true)
fi
echo "    Provider ID: $PROVIDER_ID"

if [[ -z "$PROVIDER_ID" ]]; then
  echo "ERROR: Could not create or find Gemini provider. Check the response above."
  exit 1
fi

# ── Sync AI tools ─────────────────────────────────────────────────────────────
echo "==> Syncing AI tools..."
curl -s -b "$COOKIE" -H "X-CSRFToken: $CSRF2" \
  -X POST "$BASE/api/v1/apps/$APP_UUID/ai/tools/?action=sync_tools" \
  | python3 -m json.tool 2>/dev/null || true

# ── Create prompts (type must be "system") ────────────────────────────────────
echo "==> Creating prompts..."
curl -s -b "$COOKIE" -H "X-CSRFToken: $CSRF2" -H "Content-Type: application/json" \
  -X POST "$BASE/api/v1/apps/$APP_UUID/ai/prompts/" \
  -d '{
    "name": "claim-validator-prompt",
    "type": "system",
    "content": "You are a medical billing validator. Use the get_claim_details and get_patient_insurance tools to retrieve claim data, then check: all required fields present, ICD-10 diagnosis codes valid, CPT codes on all line items, amounts consistent. Call update_claim_ai_result with field=\"ai_validation_result\" and a JSON value: {\"valid\": bool, \"issues\": [str], \"code_suggestions\": [str], \"completeness_score\": 0-100}. Claim ID: {{claim_id}}"
  }' | python3 -m json.tool 2>/dev/null || true

curl -s -b "$COOKIE" -H "X-CSRFToken: $CSRF2" -H "Content-Type: application/json" \
  -X POST "$BASE/api/v1/apps/$APP_UUID/ai/prompts/" \
  -d '{
    "name": "denial-analyzer-prompt",
    "type": "system",
    "content": "You are a medical billing denial expert. Use get_claim_details to retrieve the denied claim, then identify root cause. Call update_claim_ai_result with field=\"ai_denial_analysis\" and a JSON value: {\"root_cause\": str, \"category\": \"eligibility|authorization|coding|duplicate|timely_filing|other\", \"corrective_actions\": [str]}. Claim ID: {{claim_id}}"
  }' | python3 -m json.tool 2>/dev/null || true

curl -s -b "$COOKIE" -H "X-CSRFToken: $CSRF2" -H "Content-Type: application/json" \
  -X POST "$BASE/api/v1/apps/$APP_UUID/ai/prompts/" \
  -d '{
    "name": "appeal-drafter-prompt",
    "type": "system",
    "content": "You are a medical billing appeals specialist. Use get_claim_details and get_patient_insurance to retrieve claim data, then write a formal appeal letter. Call update_claim_ai_result with field=\"ai_appeal_draft\" and the complete appeal letter text as value. Claim ID: {{claim_id}}"
  }' | python3 -m json.tool 2>/dev/null || true

# ── Create agent records ───────────────────────────────────────────────────────
echo "==> Creating agent records..."
curl -s -b "$COOKIE" -H "X-CSRFToken: $CSRF2" -H "Content-Type: application/json" \
  -X POST "$BASE/api/v1/apps/$APP_UUID/ai/agents/" \
  -d "{
    \"name\": \"claim-validator\",
    \"provider_id\": $PROVIDER_ID,
    \"model\": \"gemini-2.0-flash\",
    \"system_prompt_name\": \"claim-validator-prompt\",
    \"tools\": [\"get_claim_details\", \"get_patient_insurance\", \"update_claim_ai_result\"]
  }" | python3 -m json.tool 2>/dev/null || true

curl -s -b "$COOKIE" -H "X-CSRFToken: $CSRF2" -H "Content-Type: application/json" \
  -X POST "$BASE/api/v1/apps/$APP_UUID/ai/agents/" \
  -d "{
    \"name\": \"denial-analyzer\",
    \"provider_id\": $PROVIDER_ID,
    \"model\": \"gemini-2.0-flash\",
    \"system_prompt_name\": \"denial-analyzer-prompt\",
    \"tools\": [\"get_claim_details\", \"update_claim_ai_result\"]
  }" | python3 -m json.tool 2>/dev/null || true

curl -s -b "$COOKIE" -H "X-CSRFToken: $CSRF2" -H "Content-Type: application/json" \
  -X POST "$BASE/api/v1/apps/$APP_UUID/ai/agents/" \
  -d "{
    \"name\": \"appeal-drafter\",
    \"provider_id\": $PROVIDER_ID,
    \"model\": \"gemini-2.0-flash\",
    \"system_prompt_name\": \"appeal-drafter-prompt\",
    \"tools\": [\"get_claim_details\", \"get_patient_insurance\", \"update_claim_ai_result\"]
  }" | python3 -m json.tool 2>/dev/null || true

# ── Sync tasks ────────────────────────────────────────────────────────────────
echo "==> Syncing Celery tasks..."
curl -s -b "$COOKIE" -H "X-CSRFToken: $CSRF2" \
  -X POST "$BASE/api/v1/apps/$APP_UUID/tasks/" \
  | python3 -m json.tool 2>/dev/null || true

# ── Restart Celery ────────────────────────────────────────────────────────────
echo "==> Restarting Celery..."
sg docker -c "docker compose -f /home/parakram/src/patientbilling/deploy/docker_compose.yml restart celery celery_beat"

echo ""
echo "========================================"
echo "DONE. Provider ID: $PROVIDER_ID"
echo "Next: submit a claim via the app UI, then check:"
echo "  sg docker -c \"docker compose -f /home/parakram/src/patientbilling/deploy/docker_compose.yml logs celery --tail=50\""
echo "========================================"
