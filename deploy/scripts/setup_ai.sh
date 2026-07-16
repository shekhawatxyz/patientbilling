#!/usr/bin/env bash
# Configure AI provider + prompts + agents in the Zango App Panel.
#
# Usage — pick one:
#   ANTHROPIC_KEY="sk-ant-..."  bash deploy/scripts/setup_ai.sh   # recommended
#   OPENAI_KEY="sk-..."         bash deploy/scripts/setup_ai.sh   # gpt-4o-mini
#   GEMINI_KEY="AIza..."        bash deploy/scripts/setup_ai.sh   # requires paid quota
#
# A $1 USD monthly budget cap is set automatically. Actual spend for testing
# is well under $0.05 total — the cap is just a safety net.
set -euo pipefail

# Development-only setup script. The credentials below are local demo defaults,
# never production credentials. Resolve the stack relative to this file.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_FILE="$REPO_DIR/deploy/docker_compose.yml"

compose() {
  if command -v docker >/dev/null 2>&1; then
    docker compose -f "$COMPOSE_FILE" "$@"
  elif command -v sg >/dev/null 2>&1; then
    sg docker -c "docker compose -f '$COMPOSE_FILE' $*"
  else
    echo "ERROR: Docker Compose is required." >&2
    exit 1
  fi
}

if [[ -n "${ANTHROPIC_KEY:-}" ]]; then
  PROVIDER_SLUG="anthropic"
  PROVIDER_NAME="Claude Haiku"
  PROVIDER_MODEL="claude-haiku-4-5-20251001"
  PROVIDER_API_KEY="$ANTHROPIC_KEY"
  USE_GEMINI=false
elif [[ -n "${OPENAI_KEY:-}" ]]; then
  PROVIDER_SLUG="openai"
  PROVIDER_NAME="GPT-4o Mini"
  PROVIDER_MODEL="gpt-4o-mini"
  PROVIDER_API_KEY="$OPENAI_KEY"
  USE_GEMINI=false
elif [[ -n "${GEMINI_KEY:-}" ]]; then
  PROVIDER_SLUG="gemini"
  PROVIDER_NAME="Gemini 2.0 Flash Lite"
  PROVIDER_MODEL="gemini-2.0-flash-lite"
  PROVIDER_API_KEY="$GEMINI_KEY"
  USE_GEMINI=true
else
  echo "ERROR: No API key set."
  echo "  Anthropic (recommended): ANTHROPIC_KEY=\"sk-ant-...\" bash deploy/scripts/setup_ai.sh"
  echo "  OpenAI:                  OPENAI_KEY=\"sk-...\"        bash deploy/scripts/setup_ai.sh"
  echo "  Gemini (paid only):      GEMINI_KEY=\"AIza...\"       bash deploy/scripts/setup_ai.sh"
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
echo "    Done. Using provider: $PROVIDER_SLUG ($PROVIDER_MODEL)"

# ── Install Gemini provider (only when GEMINI_KEY is used) ────────────────────
if [ "$USE_GEMINI" = "true" ]; then
  echo "==> Checking/installing Gemini provider in container..."
  ALREADY_INSTALLED=$(compose exec -T app python3 -c '
from zango.ai.providers.registry import PROVIDER_REGISTRY
print("yes" if "gemini" in PROVIDER_REGISTRY else "no")
' 2>/dev/null | tr -d '[:space:]')

  if [ "$ALREADY_INSTALLED" != "yes" ]; then
      echo "    Installing..."
      compose exec -T app bash -c '
PROVIDERS_DIR=$(python3 -c "import zango.ai.providers, os; print(os.path.dirname(zango.ai.providers.__file__))")
sudo cp /zango/providers/gemini.py "$PROVIDERS_DIR/gemini.py" 2>/dev/null || cp /zango/providers/gemini.py "$PROVIDERS_DIR/gemini.py"
if ! grep -q "from . import gemini" "$PROVIDERS_DIR/__init__.py" 2>/dev/null; then
    printf "\ntry:\n    from . import gemini  # noqa: F401\nexcept ImportError:\n    pass\n" | sudo tee -a "$PROVIDERS_DIR/__init__.py" > /dev/null 2>/dev/null || printf "\ntry:\n    from . import gemini  # noqa: F401\nexcept ImportError:\n    pass\n" >> "$PROVIDERS_DIR/__init__.py"
fi
echo "    Installed at $PROVIDERS_DIR/gemini.py"
'

      echo "==> Restarting app container (waiting up to 60s for it to be ready)..."
      compose restart app

      for i in $(seq 1 60); do
          HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/auth/login/" 2>/dev/null)
          if [ "$HTTP_CODE" = "200" ]; then
              echo "    App ready after ${i}s"
              break
          fi
          sleep 1
      done

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
fi

# ── Create provider ───────────────────────────────────────────────────────────
echo "==> Creating $PROVIDER_NAME provider..."
EXISTING_PROVIDER=$(curl -s -b "$COOKIE" "$BASE/api/v1/apps/$APP_UUID/ai/providers/")
PROVIDER_ID=$(echo "$EXISTING_PROVIDER" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for provider in data.get('response', {}).get('providers', {}).get('records', []):
    if provider.get('provider_slug') == '$PROVIDER_SLUG':
        print(provider['id']); break
" 2>/dev/null || true)
if [[ -n "$PROVIDER_ID" ]]; then
  PROVIDER_RESP="Reusing existing provider $PROVIDER_ID"
else
PROVIDER_RESP=$(curl -s -b "$COOKIE" -H "X-CSRFToken: $CSRF2" \
  -H "Content-Type: application/json" \
  -X POST "$BASE/api/v1/apps/$APP_UUID/ai/providers/" \
  -d "{
    \"name\": \"$PROVIDER_NAME\",
    \"provider_slug\": \"$PROVIDER_SLUG\",
    \"config\": {\"api_key\": \"$PROVIDER_API_KEY\"},
    \"default_model\": \"$PROVIDER_MODEL\",
    \"monthly_budget_usd\": 1.00
  }")
fi
echo "    Response: $PROVIDER_RESP"
if [[ -z "$PROVIDER_ID" ]]; then
PROVIDER_ID=$(echo "$PROVIDER_RESP" | python3 -c "
import sys, json
d = json.load(sys.stdin)
v = d.get('response', d)
print(v.get('id') or v.get('provider', {}).get('id') or '')
" 2>/dev/null || true)
fi

if [[ -z "$PROVIDER_ID" ]]; then
  echo "    Creation unclear — fetching provider list..."
  PROVIDER_ID=$(curl -s -b "$COOKIE" "$BASE/api/v1/apps/$APP_UUID/ai/providers/" \
    | python3 -c "
import sys, json
data = json.load(sys.stdin)
records = data.get('response', {}).get('providers', {}).get('records', [])
slug = '$PROVIDER_SLUG'
for p in records:
    if p.get('provider_slug') == slug:
        print(p['id']); break
" 2>/dev/null || true)
fi
echo "    Provider ID: $PROVIDER_ID"

if [[ -z "$PROVIDER_ID" ]]; then
  echo "ERROR: Could not create or find $PROVIDER_NAME provider. Check the response above."
  exit 1
fi

# ── Sync AI tools ─────────────────────────────────────────────────────────────
echo "==> Syncing AI tools..."
curl -s -b "$COOKIE" -H "X-CSRFToken: $CSRF2" \
  -X POST "$BASE/api/v1/apps/$APP_UUID/ai/tools/sync/" \
  | python3 -m json.tool 2>/dev/null || true

# ── Create prompts ────────────────────────────────────────────────────────────
echo "==> Creating prompts..."
PROMPTS=$(curl -s -b "$COOKIE" "$BASE/api/v1/apps/$APP_UUID/ai/prompts/")
if [[ "$PROMPTS" != *'claim-validator-prompt'* ]]; then
curl -s -b "$COOKIE" -H "X-CSRFToken: $CSRF2" -H "Content-Type: application/json" \
  -X POST "$BASE/api/v1/apps/$APP_UUID/ai/prompts/" \
  -d '{
    "name": "claim-validator-prompt",
    "type": "system",
    "content": "You are a medical billing validator. First call get_claim_details to retrieve claim data, then call get_patient_insurance for insurance info. Check: all required fields present, ICD-10 diagnosis codes valid, CPT codes on all line items, amounts consistent. You MUST finish by calling the update_claim_ai_result tool with a JSON string value: {\"valid\": bool, \"issues\": [str], \"code_suggestions\": [str], \"completeness_score\": 0-100}. Do not respond with plain text as your final answer - you must call update_claim_ai_result as your last action. Claim ID: {{claim_id}}"
  }' | python3 -m json.tool 2>/dev/null || true
fi

if [[ "$PROMPTS" != *'denial-analyzer-prompt'* ]]; then
curl -s -b "$COOKIE" -H "X-CSRFToken: $CSRF2" -H "Content-Type: application/json" \
  -X POST "$BASE/api/v1/apps/$APP_UUID/ai/prompts/" \
  -d '{
    "name": "denial-analyzer-prompt",
    "type": "system",
    "content": "You are a medical billing denial expert. First call get_claim_details to retrieve the denied claim, then identify the root cause. You MUST finish by calling the update_claim_ai_result tool with a JSON string value: {\"root_cause\": str, \"category\": \"eligibility|authorization|coding|duplicate|timely_filing|other\", \"corrective_actions\": [str]}. Do not respond with plain text as your final answer - you must call update_claim_ai_result as your last action. Claim ID: {{claim_id}}"
  }' | python3 -m json.tool 2>/dev/null || true
fi

if [[ "$PROMPTS" != *'appeal-drafter-prompt'* ]]; then
curl -s -b "$COOKIE" -H "X-CSRFToken: $CSRF2" -H "Content-Type: application/json" \
  -X POST "$BASE/api/v1/apps/$APP_UUID/ai/prompts/" \
  -d '{
    "name": "appeal-drafter-prompt",
    "type": "system",
    "content": "You are a medical billing appeals specialist. First call get_claim_details and get_patient_insurance to retrieve claim data, then write a formal appeal letter. You MUST finish by calling the update_claim_ai_result tool with the complete appeal letter text as value. Do not respond with plain text as your final answer - you must call update_claim_ai_result as your last action. Claim ID: {{claim_id}}"
  }' | python3 -m json.tool 2>/dev/null || true
fi

# ── Create agent records ──────────────────────────────────────────────────────
echo "==> Creating agent records..."
AGENTS=$(curl -s -b "$COOKIE" "$BASE/api/v1/apps/$APP_UUID/ai/agents/")
if [[ "$AGENTS" != *'claim-validator'* ]]; then
curl -s -b "$COOKIE" -H "X-CSRFToken: $CSRF2" -H "Content-Type: application/json" \
  -X POST "$BASE/api/v1/apps/$APP_UUID/ai/agents/" \
  -d "{
    \"name\": \"claim-validator\",
    \"provider_id\": $PROVIDER_ID,
    \"model\": \"$PROVIDER_MODEL\",
    \"system_prompt_name\": \"claim-validator-prompt\",
    \"tools\": [\"get_claim_details\", \"get_patient_insurance\", \"update_claim_ai_result\"]
  }" | python3 -m json.tool 2>/dev/null || true
fi

if [[ "$AGENTS" != *'denial-analyzer'* ]]; then
curl -s -b "$COOKIE" -H "X-CSRFToken: $CSRF2" -H "Content-Type: application/json" \
  -X POST "$BASE/api/v1/apps/$APP_UUID/ai/agents/" \
  -d "{
    \"name\": \"denial-analyzer\",
    \"provider_id\": $PROVIDER_ID,
    \"model\": \"$PROVIDER_MODEL\",
    \"system_prompt_name\": \"denial-analyzer-prompt\",
    \"tools\": [\"get_claim_details\", \"update_claim_ai_result\"]
  }" | python3 -m json.tool 2>/dev/null || true
fi

if [[ "$AGENTS" != *'appeal-drafter'* ]]; then
curl -s -b "$COOKIE" -H "X-CSRFToken: $CSRF2" -H "Content-Type: application/json" \
  -X POST "$BASE/api/v1/apps/$APP_UUID/ai/agents/" \
  -d "{
    \"name\": \"appeal-drafter\",
    \"provider_id\": $PROVIDER_ID,
    \"model\": \"$PROVIDER_MODEL\",
    \"system_prompt_name\": \"appeal-drafter-prompt\",
    \"tools\": [\"get_claim_details\", \"get_patient_insurance\", \"update_claim_ai_result\"]
  }" | python3 -m json.tool 2>/dev/null || true
fi

# ── Sync tasks + restart Celery ───────────────────────────────────────────────
echo "==> Syncing Celery tasks..."
curl -s -b "$COOKIE" -H "X-CSRFToken: $CSRF2" \
  -X POST "$BASE/api/v1/apps/$APP_UUID/tasks/" \
  | python3 -m json.tool 2>/dev/null || true

echo "==> Restarting Celery..."
compose restart celery celery_beat

echo ""
echo "========================================"
echo "DONE. Provider: $PROVIDER_NAME ($PROVIDER_SLUG, ID: $PROVIDER_ID)"
echo "Next: submit a claim via the app UI, then check:"
echo "  docker compose -f $COMPOSE_FILE logs celery --tail=50"
echo "========================================"
