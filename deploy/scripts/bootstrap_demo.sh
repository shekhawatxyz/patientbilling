#!/usr/bin/env bash
# Bootstrap a complete, zero-key local Patient Billing demo.
# Run after: docker compose -f deploy/docker_compose.yml up -d
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
BASE_URL="${BASE_URL:-http://localhost:8000}"
APP_HOST="${APP_HOST:-patientbilling.localhost}"
APP_UUID="496d3013-cdd0-4531-92fd-3646714463c1"
APP_URL="http://${APP_HOST}:8000/app"
PLATFORM_URL="${BASE_URL}/platform"
COMPOSE_FILE="$REPO_DIR/deploy/docker_compose.yml"

env_value() {
  local key="$1"
  if [[ -f "$REPO_DIR/deploy/.env" ]]; then
    sed -n -n "s/^${key}=//p" "$REPO_DIR/deploy/.env" | tail -n 1 | sed 's/^"//; s/"$//'
  fi
}

POSTGRES_DB="${POSTGRES_DB:-$(env_value POSTGRES_DB)}"
POSTGRES_USER="${POSTGRES_USER:-$(env_value POSTGRES_USER)}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-$(env_value POSTGRES_PASSWORD)}"
POSTGRES_HOST="${POSTGRES_HOST:-$(env_value POSTGRES_HOST)}"
POSTGRES_PORT="${POSTGRES_PORT:-$(env_value POSTGRES_PORT)}"
REDIS_HOST="${REDIS_HOST:-$(env_value REDIS_HOST)}"
REDIS_PORT="${REDIS_PORT:-$(env_value REDIS_PORT)}"
PLATFORM_COOKIE="${TMPDIR:-/tmp}/patientbilling-bootstrap-platform.$$"
CONFIG_COOKIE="${TMPDIR:-/tmp}/patientbilling-bootstrap-config.$$"
trap 'rm -f "$PLATFORM_COOKIE" "$CONFIG_COOKIE"' EXIT

compose() {
  if docker info >/dev/null 2>&1; then
    docker compose -f "$COMPOSE_FILE" "$@"
  elif command -v sg >/dev/null 2>&1; then
    sg docker -c "docker compose -f '$COMPOSE_FILE' $*"
  else
    echo "ERROR: Docker Compose access is required to initialize the local database." >&2
    exit 1
  fi
}

PLATFORM_USERNAME="${PLATFORM_USERNAME:-$(env_value PLATFORM_USERNAME)}"
PLATFORM_USER_PASSWORD="${PLATFORM_USER_PASSWORD:-$(env_value PLATFORM_USER_PASSWORD)}"
PLATFORM_USERNAME="${PLATFORM_USERNAME:-platform_admin@zango.dev}"
PLATFORM_USER_PASSWORD="${PLATFORM_USER_PASSWORD:-Zango@123}"

echo "==> Initializing the Zango database and public tenant..."
compose exec -T app bash -lc "cd /zango && zango start-project zango_project \
  --db_name='$POSTGRES_DB' --db_user='$POSTGRES_USER' --db_password='$POSTGRES_PASSWORD' \
  --db_host='$POSTGRES_HOST' --db_port='$POSTGRES_PORT' \
  --platform_username='$PLATFORM_USERNAME' --platform_user_password='$PLATFORM_USER_PASSWORD' \
  --redis_host='$REDIS_HOST' --redis_port='$REDIS_PORT' --platform_domain_url=localhost" >/dev/null
compose exec -T app bash -lc "cd /zango/zango_project && python manage.py shell -c 'import uuid; from django_tenants.utils import schema_exists; from zango.apps.shared.tenancy.models import TenantModel, Domain; tenant, created = TenantModel.objects.get_or_create(name=\"patientbilling\", defaults={\"uuid\": uuid.UUID(\"$APP_UUID\"), \"schema_name\": \"patientbilling\", \"description\": \"Patient Billing demo\", \"tenant_type\": \"app\", \"status\": \"deployed\"}); tenant.status = \"deployed\"; tenant.save(); Domain.objects.update_or_create(domain=\"$APP_HOST\", defaults={\"tenant\": tenant, \"is_primary\": True}); schema_exists(tenant.schema_name) or tenant.create_schema(check_if_exists=True)'" >/dev/null
compose exec -T app bash -lc 'cd /zango/zango_project && SINGLE_BEAT_REDIS_SERVER=redis://redis:6379/1 single-beat zango update-apps' >/dev/null
compose exec -T app bash -c 'cd zango_project && python manage.py ws_migrate --package appbuilder patientbilling' >/dev/null

echo "==> Waiting for the app to be ready..."
for attempt in $(seq 1 120); do
  status=$(curl -sS --connect-timeout 2 -o /dev/null -w '%{http_code}' "$PLATFORM_URL" || true)
  if [[ "$status" =~ ^[23][0-9][0-9]$ ]]; then
    echo "    App responded after ${attempt}s"
    break
  fi
  if [[ "$attempt" == 120 ]]; then
    echo "ERROR: App did not become ready at $PLATFORM_URL" >&2
    exit 1
  fi
  sleep 1
done

echo "==> Authenticating as platform admin..."
CSRF=$(curl -fsS -c "$PLATFORM_COOKIE" "$BASE_URL/auth/login/" \
  | grep -o 'csrfmiddlewaretoken" value="[^"]*"' \
  | grep -o 'value="[^"]*"' | cut -d'"' -f2)
curl -fsS -c "$PLATFORM_COOKIE" -b "$PLATFORM_COOKIE" -X POST "$BASE_URL/auth/login/" \
  -H "X-CSRFToken: $CSRF" -H "Referer: $BASE_URL/auth/login/" \
  -F "username=$PLATFORM_USERNAME" -F "password=$PLATFORM_USER_PASSWORD" \
  -F "csrfmiddlewaretoken=$CSRF" -o /dev/null
CSRF2=$(grep csrftoken "$PLATFORM_COOKIE" | awk '{print $NF}')

api_success() {
  python3 -c 'import json, sys; data=json.load(sys.stdin); assert data.get("success") is True, data; print(json.dumps(data))'
}

echo "==> Syncing policies..."
curl -fsS -b "$PLATFORM_COOKIE" -X POST \
  "$BASE_URL/api/v1/apps/$APP_UUID/policies/?action=sync_policies" \
  -H "X-CSRFToken: $CSRF2" -H "Referer: $PLATFORM_URL/" | api_success >/dev/null

POLICIES=$(curl -fsS -b "$PLATFORM_COOKIE" "$BASE_URL/api/v1/apps/$APP_UUID/policies/")
policy_id() {
  printf '%s' "$POLICIES" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(next(p["id"] for p in d["response"]["policies"]["records"] if p["name"] == sys.argv[1]))' "$1"
}
APP_VIEW_POLICY=$(policy_id AppViewPolicy)
APP_VIEW_PACKAGE_POLICY=$(policy_id AppViewPolicy1)
ALLOW_ANYWHERE_POLICY=$(policy_id AllowFromAnywhere)
PATIENT_POLICY=$(policy_id PatientCrudViewPolicy)
PAYER_POLICY=$(policy_id InsurancePayerCrudViewPolicy)
CLAIM_POLICY=$(policy_id ClaimCrudViewPolicy)
INVOICE_POLICY=$(policy_id InvoiceCrudViewPolicy)
DASHBOARD_POLICY=$(policy_id DashboardPolicy)
ROLES_URL="$BASE_URL/api/v1/apps/$APP_UUID/roles/"
create_role_if_missing() {
  local name="$1" policies="$2"
  if curl -fsS -b "$PLATFORM_COOKIE" "$ROLES_URL" | python3 -c 'import json,sys; d=json.load(sys.stdin); raise SystemExit(0 if any(r.get("name") == sys.argv[1] for r in d["response"]["roles"]["records"]) else 1)' "$name"; then
    echo "    Reusing $name role"
  else
    curl -fsS -b "$PLATFORM_COOKIE" -X POST "$ROLES_URL" \
      -H "X-CSRFToken: $CSRF2" -H 'Content-Type: application/json' \
      -d "{\"name\":\"$name\",\"policies\":$policies}" | api_success >/dev/null
    echo "    Created $name role"
  fi
}
echo "==> Creating billing roles when absent..."
create_role_if_missing "BillingStaff" "[$ALLOW_ANYWHERE_POLICY,$APP_VIEW_POLICY,$PATIENT_POLICY,$PAYER_POLICY,$CLAIM_POLICY,$INVOICE_POLICY]"
create_role_if_missing "BillingManager" "[$ALLOW_ANYWHERE_POLICY,$APP_VIEW_POLICY,$DASHBOARD_POLICY,$PATIENT_POLICY,$PAYER_POLICY,$CLAIM_POLICY,$INVOICE_POLICY]"

ROLES=$(curl -fsS -b "$PLATFORM_COOKIE" "$ROLES_URL")
ANONYMOUS_ROLE=$(printf '%s' "$ROLES" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(next(r["id"] for r in d["response"]["roles"]["records"] if r["name"] == "AnonymousUsers"))')
curl -fsS -b "$PLATFORM_COOKIE" -X PUT "${ROLES_URL}${ANONYMOUS_ROLE}/" \
  -H "X-CSRFToken: $CSRF2" -H 'Content-Type: application/json' \
  -d "{\"policies\":[$ALLOW_ANYWHERE_POLICY,$APP_VIEW_POLICY,$APP_VIEW_PACKAGE_POLICY]}" \
  | api_success >/dev/null

ROLES=$(curl -fsS -b "$PLATFORM_COOKIE" "$ROLES_URL")
STAFF_ROLE=$(printf '%s' "$ROLES" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(next(r["id"] for r in d["response"]["roles"]["records"] if r["name"] == "BillingStaff"))')
MANAGER_ROLE=$(printf '%s' "$ROLES" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(next(r["id"] for r in d["response"]["roles"]["records"] if r["name"] == "BillingManager"))')

echo "==> Creating demo users when absent..."
USERS_URL="$BASE_URL/api/v1/apps/$APP_UUID/users/"
USERS=$(curl -fsS -b "$PLATFORM_COOKIE" "$USERS_URL")
create_user_if_missing() {
  local email="$1" name="$2" mobile="$3" role="$4"
  if printf '%s' "$USERS" | python3 -c 'import json,sys; d=json.load(sys.stdin); email=sys.argv[1]; raise SystemExit(0 if any(u.get("email") == email for u in d["response"]["users"]["records"]) else 1)' "$email"; then
    echo "    Reusing $email"
  else
    curl -fsS -b "$PLATFORM_COOKIE" -X POST "$USERS_URL" \
      -H "X-CSRFToken: $CSRF2" -H "Content-Type: application/x-www-form-urlencoded" \
      --data-urlencode "name=$name" --data-urlencode "email=$email" \
      --data-urlencode "mobile=$mobile" --data-urlencode 'password=Billing@123' \
      --data-urlencode "roles=$role" | api_success >/dev/null
    echo "    Created $email"
  fi
}
create_user_if_missing "staff@billing.local" "Billing Staff" "+919000000001" "$STAFF_ROLE"
create_user_if_missing "manager@billing.local" "Billing Manager" "+919000000002" "$MANAGER_ROLE"

set_demo_password_if_pending() {
  local email="$1"
  local cookie="${TMPDIR:-/tmp}/patientbilling-${email%%@*}-$$"
  trap 'rm -f "$cookie"' RETURN
  curl -sS -c "$cookie" -H "Host: $APP_HOST" "$BASE_URL/api/v1/appauth/login/" >/dev/null
  local csrf response
  csrf=$(grep csrftoken "$cookie" | awk '{print $NF}')
  response=$(curl -sS -c "$cookie" -b "$cookie" \
    -H "Host: $APP_HOST" -H "X-CSRFToken: $csrf" -H 'Content-Type: application/json' \
    -X POST "$BASE_URL/api/v1/appauth/login/" \
    -d "{\"email\":\"$email\",\"password\":\"Billing@123\"}")
  if printf '%s' "$response" | python3 -c 'import json,sys; d=json.load(sys.stdin); raise SystemExit(0 if d.get("response",{}).get("data",{}).get("next_step",{}).get("id") == "set_password" else 1)'; then
    csrf=$(grep csrftoken "$cookie" | awk '{print $NF}')
    curl -fsS -c "$cookie" -b "$cookie" \
      -H "Host: $APP_HOST" -H "X-CSRFToken: $csrf" -H 'Content-Type: application/json' \
      -X POST "$BASE_URL/api/v1/appauth/password/set/" \
      -d '{"new_password":"Billing@123","confirm_password":"Billing@123"}' >/dev/null
    echo "    Activated password for $email"
  fi
  rm -f "$cookie"
  trap - RETURN
}
set_demo_password_if_pending "staff@billing.local"
set_demo_password_if_pending "manager@billing.local"

echo "==> Getting the signed AppBuilder configuration URL..."
CONFIG_URL=$(curl -fsS -b "$PLATFORM_COOKIE" \
  "$BASE_URL/api/v1/apps/$APP_UUID/packages/?action=config_url&package_name=appbuilder" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["response"]["url"])')
CONFIG_BASE=$(printf '%s' "$CONFIG_URL" | cut -d'?' -f1)
CONFIG_TOKEN=$(printf '%s' "$CONFIG_URL" | sed 's/.*token=//')
config_url() { printf '%s%s&token=%s' "$CONFIG_BASE" "$1" "$CONFIG_TOKEN"; }

ROUTES_PAYLOAD=$(cat <<'JSON'
{"routes":[
  {"name":"Dashboard","path":"/app/dashboard","page_type":"custom","component":"Dashboard","extra_params":{}},
  {"name":"Claims","path":"/app/claims","page_type":"custom","component":"ClaimsPage","extra_params":{}},
  {"name":"Patients","path":"/app/patients","page_type":"custom","component":"PatientsPage","extra_params":{}},
  {"name":"Invoices","path":"/app/invoices","page_type":"custom","component":"InvoicesPage","extra_params":{}},
  {"name":"Insurance Payers","path":"/app/payers","page_type":"crud","extra_params":{"api_endpoint":"/payers/payers/"}}
]}
JSON
)

echo "==> Registering AppBuilder routes when absent..."
ROUTES=$(curl -fsS -b "$PLATFORM_COOKIE" "$(config_url 'routes/api/?action=get_routes')")
if printf '%s' "$ROUTES" | python3 -c 'import json,sys; d=json.load(sys.stdin); expected={"Dashboard","Claims","Patients","Invoices","Insurance Payers"}; raise SystemExit(0 if expected <= {r.get("name") for r in d["response"].get("routes",[])} else 1)'; then
  echo "    Reusing existing 5 routes"
else
  curl -fsS -b "$PLATFORM_COOKIE" -X POST "$(config_url 'routes/api/?action=save_routes')" \
    -H "X-CSRFToken: $CSRF2" -H 'Content-Type: application/json' -d "$ROUTES_PAYLOAD" | api_success >/dev/null
  ROUTES=$(curl -fsS -b "$PLATFORM_COOKIE" "$(config_url 'routes/api/?action=get_routes')")
  echo "    Registered 5 routes"
fi

ROUTE_IDS=$(printf '%s' "$ROUTES" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps({r["name"]:r["route_id"] for r in d["response"]["routes"]}))')
STAFF_MENU=$(python3 - "$ROUTE_IDS" <<'PY'
import json, sys
r = json.loads(sys.argv[1])
print(json.dumps({"user_role": int(sys.argv[2]) if len(sys.argv) > 2 else 0, "menu": [
    {"route_id": r[n], "name": n, "uri": p, "icon": i, "children": []}
    for n, p, i in [("Claims", "/app/claims", "📋"), ("Patients", "/app/patients", "👤"), ("Invoices", "/app/invoices", "💰"), ("Insurance Payers", "/app/payers", "🏥")]
]}))
PY
)
MANAGER_MENU=$(python3 - "$ROUTE_IDS" <<'PY'
import json, sys
r = json.loads(sys.argv[1])
print(json.dumps({"menu": [
    {"route_id": r[n], "name": n, "uri": p, "icon": i, "children": []}
    for n, p, i in [("Dashboard", "/app/dashboard", "📊"), ("Claims", "/app/claims", "📋"), ("Patients", "/app/patients", "👤"), ("Invoices", "/app/invoices", "💰"), ("Insurance Payers", "/app/payers", "🏥")]
]}))
PY
)

echo "==> Registering the two role menus when absent..."
MENUS=$(curl -fsS -b "$PLATFORM_COOKIE" "$(config_url 'api/?action=get_configs')")
create_menu_if_missing() {
  local role_id="$1" role_name="$2" menu="$3"
  if printf '%s' "$MENUS" | python3 -c 'import json,sys; d=json.load(sys.stdin); raise SystemExit(0 if any(m.get("user_role") == sys.argv[1] for m in d["response"]) else 1)' "$role_name"; then
    echo "    Reusing $role_name menu"
  else
    curl -fsS -b "$PLATFORM_COOKIE" -X POST "$(config_url 'api/?action=create_config')" \
      -H "X-CSRFToken: $CSRF2" -H 'Content-Type: application/json' \
      -d "$(printf '%s' "$menu" | python3 -c 'import json,sys; d=json.load(sys.stdin); d["user_role"]=int(sys.argv[1]); print(json.dumps(d))' "$role_id")" | api_success >/dev/null
    echo "    Created $role_name menu"
  fi
}
create_menu_if_missing "$STAFF_ROLE" "BillingStaff" "$STAFF_MENU"
create_menu_if_missing "$MANAGER_ROLE" "BillingManager" "$MANAGER_MENU"

echo "==> Registering the zero-key local_fake AI agents..."
LOCAL_FAKE_AI=true bash "$SCRIPT_DIR/setup_ai.sh"

echo
echo "========================================"
echo "Demo bootstrap complete"
echo "App URL:      $APP_URL"
echo "Platform URL: $PLATFORM_URL"
echo "Staff login:  staff@billing.local / Billing@123"
echo "Manager login: manager@billing.local / Billing@123"
echo "========================================"
