#!/usr/bin/env bash
# Configure AI provider + prompts + agents in the Zango App Panel.
#
# Usage — pick one:
#   ANTHROPIC_KEY="sk-ant-..."  bash deploy/scripts/setup_ai.sh   # recommended
#   OPENAI_KEY="sk-..."         bash deploy/scripts/setup_ai.sh   # gpt-4o-mini
#   GEMINI_KEY="AIza..."        bash deploy/scripts/setup_ai.sh   # requires paid quota
#   LOCAL_FAKE_AI=true           bash deploy/scripts/setup_ai.sh   # offline plumbing
#   LOCAL_FAKE_AI=restore        bash deploy/scripts/setup_ai.sh   # restore saved agents
#
# Real providers use an explicit $1 USD monthly budget cap. The local fake
# provider is explicitly zero-cost and uses a 0.00 budget.
set -euo pipefail

# Development-only setup script. The credentials below are local demo defaults,
# never production credentials. Resolve the stack relative to this file.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_FILE="$REPO_DIR/deploy/docker_compose.yml"
STATE_FILE="$REPO_DIR/deploy/.ai_provider_state.json"
RESTORE_MODE=false
if [[ "${LOCAL_FAKE_AI:-}" == "restore" ]]; then
  RESTORE_MODE=true
fi

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

if [[ "$RESTORE_MODE" == "true" ]]; then
  PROVIDER_SLUG="restore"
  PROVIDER_NAME="saved real providers"
  PROVIDER_MODEL="saved models"
  PROVIDER_API_KEY=""
  USE_GEMINI=false
elif [[ "${LOCAL_FAKE_AI:-}" == "true" ]]; then
  PROVIDER_SLUG="local_fake"
  PROVIDER_NAME="Local Fake (Offline)"
  PROVIDER_MODEL="local-deterministic-v1"
  PROVIDER_API_KEY=""
  USE_GEMINI=false
elif [[ -n "${ANTHROPIC_KEY:-}" ]]; then
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
  echo "ERROR: No API key set (or LOCAL_FAKE_AI=true for offline testing)."
  echo "  Anthropic (recommended): ANTHROPIC_KEY=\"sk-ant-...\" bash deploy/scripts/setup_ai.sh"
  echo "  OpenAI:                  OPENAI_KEY=\"sk-...\"        bash deploy/scripts/setup_ai.sh"
  echo "  Gemini (paid only):      GEMINI_KEY=\"AIza...\"       bash deploy/scripts/setup_ai.sh"
  echo "  Offline plumbing:        LOCAL_FAKE_AI=true bash deploy/scripts/setup_ai.sh"
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
echo "    Done. Active provider: $PROVIDER_SLUG | model: $PROVIDER_MODEL"

if [[ "$RESTORE_MODE" == "true" ]]; then
  if [[ ! -f "$STATE_FILE" ]]; then
    echo "ERROR: No saved provider state at $STATE_FILE."
    exit 1
  fi
  echo "==> Restoring previously active real providers..."
  while IFS=$'\t' read -r agent_id provider_id model; do
    [[ -n "$agent_id" && -n "$provider_id" ]] || {
      echo "ERROR: Invalid saved provider state." >&2
      exit 1
    }
    curl -fsS -b "$COOKIE" -H "X-CSRFToken: $CSRF2" -H "Content-Type: application/json" \
      -X PUT "$BASE/api/v1/apps/$APP_UUID/ai/agents/$agent_id/" \
      -d "{\"provider_id\": $provider_id, \"model\": \"$model\"}" \
      | python3 -m json.tool >/dev/null
    echo "    Restored agent $agent_id to provider $provider_id ($model)"
  done < <(python3 - "$STATE_FILE" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as state_file:
    state = json.load(state_file)
for agent in state.get("agents", []):
    print(agent["id"], agent["provider_id"], agent["model"], sep="\t")
PY
  )
  compose restart celery celery_beat
  echo "DONE. Real provider wiring restored from $STATE_FILE."
  exit 0
fi

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

# ── Install local fake provider (only when explicitly requested) ──────────────
if [[ "$PROVIDER_SLUG" == "local_fake" ]]; then
  echo "==> Installing local_fake provider in container..."
  compose exec -T app bash -c '
PROVIDERS_DIR=$(python3 -c "import zango.ai.providers, os; print(os.path.dirname(zango.ai.providers.__file__))")
sudo cp /zango/providers/local_fake.py "$PROVIDERS_DIR/local_fake.py" 2>/dev/null || cp /zango/providers/local_fake.py "$PROVIDERS_DIR/local_fake.py"
if ! grep -q "from . import local_fake" "$PROVIDERS_DIR/__init__.py" 2>/dev/null; then
  printf "\ntry:\n    from . import local_fake  # noqa: F401\nexcept ImportError:\n    pass\n" | sudo tee -a "$PROVIDERS_DIR/__init__.py" >/dev/null 2>/dev/null || printf "\ntry:\n    from . import local_fake  # noqa: F401\nexcept ImportError:\n    pass\n" >> "$PROVIDERS_DIR/__init__.py"
fi
'
  compose restart app
  for i in $(seq 1 60); do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/auth/login/" 2>/dev/null)
    [[ "$HTTP_CODE" == "200" ]] && break
    sleep 1
  done
  CSRF=$(curl -s -c "$COOKIE" "$BASE/auth/login/" | grep -o 'csrfmiddlewaretoken" value="[^"]*"' | grep -o 'value="[^"]*"' | cut -d'"' -f2)
  curl -s -c "$COOKIE" -b "$COOKIE" -X POST "$BASE/auth/login/" \
    -H "X-CSRFToken: $CSRF" -H "Referer: $BASE/auth/login/" \
    -F "username=platform_admin@zango.dev" -F "password=Zango@123" \
    -F "csrfmiddlewaretoken=$CSRF" -o /dev/null
  CSRF2=$(grep csrftoken "$COOKIE" | awk '{print $NF}')
fi

# ── Create provider ───────────────────────────────────────────────────────────
echo "==> Active provider before provider-creation call: $PROVIDER_SLUG | model: $PROVIDER_MODEL"
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
  MONTHLY_BUDGET_USD="1.00"
  if [[ "$PROVIDER_SLUG" == "local_fake" ]]; then
    MONTHLY_BUDGET_USD="0.00"
  fi
PROVIDER_RESP=$(curl -s -b "$COOKIE" -H "X-CSRFToken: $CSRF2" \
  -H "Content-Type: application/json" \
  -X POST "$BASE/api/v1/apps/$APP_UUID/ai/providers/" \
  -d "{
    \"name\": \"$PROVIDER_NAME\",
    \"provider_slug\": \"$PROVIDER_SLUG\",
    \"config\": {\"api_key\": \"$PROVIDER_API_KEY\"},
    \"default_model\": \"$PROVIDER_MODEL\",
    \"monthly_budget_usd\": $MONTHLY_BUDGET_USD
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

# Save the real wiring before the first fake-provider mutation. Never overwrite
# an existing state file: repeated plumbing sessions must preserve the original
# provider that restore mode is expected to bring back.
AGENTS=$(curl -s -b "$COOKIE" "$BASE/api/v1/apps/$APP_UUID/ai/agents/")
if [[ "$PROVIDER_SLUG" == "local_fake" ]]; then
  if [[ -e "$STATE_FILE" ]]; then
    echo "    Preserving existing provider state at $STATE_FILE"
  else
    PROVIDERS=$(curl -s -b "$COOKIE" "$BASE/api/v1/apps/$APP_UUID/ai/providers/")
    python3 - "$STATE_FILE" "$AGENTS" "$PROVIDERS" <<'PY'
import json
import os
import sys

state_path, payload, provider_payload = sys.argv[1:]
data = json.loads(payload)
providers = json.loads(provider_payload)
records = data.get("response", {}).get("agents", {}).get("records", [])
provider_slugs = {
    str(provider["id"]): provider.get("provider_slug")
    for provider in providers.get("response", {}).get("providers", {}).get("records", [])
}
names = {"claim-validator", "denial-analyzer", "appeal-drafter"}
saved = [
    {
        "name": agent["name"],
        "id": agent["id"],
        "provider_id": agent["provider_id"],
        "model": agent.get("model", ""),
    }
    for agent in records
    if (
        agent.get("name") in names
        and agent.get("provider_id")
        and provider_slugs.get(str(agent["provider_id"])) != "local_fake"
    )
]
if not saved:
    raise SystemExit("No existing agent wiring found to save")
os.makedirs(os.path.dirname(state_path), exist_ok=True)
tmp_path = state_path + ".tmp"
with open(tmp_path, "w", encoding="utf-8") as state_file:
    json.dump({"agents": saved}, state_file, indent=2)
    state_file.write("\n")
os.replace(tmp_path, state_path)
print(f"    Saved {len(saved)} agent provider assignments to {state_path}")
PY
  fi
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
if [[ "$AGENTS" != *'"name": "claim-validator"'* ]]; then
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

if [[ "$PROVIDER_SLUG" == "local_fake" ]]; then
  echo "==> Repointing the three agents to local_fake for this plumbing session..."
  AGENTS=$(curl -s -b "$COOKIE" "$BASE/api/v1/apps/$APP_UUID/ai/agents/")
  while IFS=$'\t' read -r agent_id agent_name; do
    curl -fsS -b "$COOKIE" -H "X-CSRFToken: $CSRF2" -H "Content-Type: application/json" \
      -X PUT "$BASE/api/v1/apps/$APP_UUID/ai/agents/$agent_id/" \
      -d "{\"provider_id\": $PROVIDER_ID, \"model\": \"$PROVIDER_MODEL\"}" \
      | python3 -m json.tool >/dev/null
    echo "    Repointed $agent_name"
  done < <(python3 - "$AGENTS" <<'PY'
import json
import sys

data = json.loads(sys.argv[1])
for agent in data.get("response", {}).get("agents", {}).get("records", []):
    if agent.get("name") in {"claim-validator", "denial-analyzer", "appeal-drafter"}:
        print(agent["id"], agent["name"], sep="\t")
PY
  )
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
if [[ "$PROVIDER_SLUG" == "local_fake" ]]; then
  echo "IMPORTANT: This changed the shared app's agent wiring for plumbing tests."
  echo "Restore it afterward with: LOCAL_FAKE_AI=restore bash deploy/scripts/setup_ai.sh"
fi
echo "Next: submit a claim via the app UI, then check:"
echo "  docker compose -f $COMPOSE_FILE logs celery --tail=50"
echo "========================================"
