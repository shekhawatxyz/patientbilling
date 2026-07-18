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
ENV_FILE="$REPO_DIR/deploy/.env"

if [[ "${SKIP_FRONTEND_BUILD:-false}" == "true" ]]; then
  echo "==> Reusing the frontend bundle built by the startup command..."
else
  echo "==> Building the frontend bundle..."
  bash "$SCRIPT_DIR/build_frontend.sh"
fi

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
APP_COOKIE="${TMPDIR:-/tmp}/patientbilling-bootstrap-app.$$"
MANAGER_COOKIE="${TMPDIR:-/tmp}/patientbilling-bootstrap-manager.$$"
trap 'rm -f "$PLATFORM_COOKIE" "$CONFIG_COOKIE" "$APP_COOKIE" "$MANAGER_COOKIE"' EXIT

compose() {
  if docker info >/dev/null 2>&1; then
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
  elif command -v sg >/dev/null 2>&1; then
    local arg quoted_arg command="docker compose --env-file $(printf '%q' "$ENV_FILE") -f $(printf '%q' "$COMPOSE_FILE")"
    for arg in "$@"; do
      printf -v quoted_arg '%q' "$arg"
      command+=" $quoted_arg"
    done
    sg docker -c "$command"
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

# update-apps does not reliably apply package migrations to a newly-created tenant.
# WorkflowState and AppRoutesModel are owned by these packages, so activate their
# migrations explicitly before any bootstrap API calls can read those tables.
for package in workflow appbuilder; do
  compose exec -T app bash -lc "cd /zango/zango_project && python manage.py ws_migrate patientbilling --package $package" >/dev/null
done

compose exec -T app bash -lc 'cd /zango/zango_project && SINGLE_BEAT_REDIS_SERVER=redis://redis:6379/1 single-beat zango update-apps' >/dev/null

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
echo "    Offline AI is active; no paid provider was selected. The dashboard will identify this mode."

echo "==> Waiting for the app after AI provider setup..."
for attempt in $(seq 1 120); do
  status=$(curl -sS --connect-timeout 2 -o /dev/null -w '%{http_code}' "$PLATFORM_URL" || true)
  if [[ "$status" =~ ^[23][0-9][0-9]$ ]]; then
    echo "    App responded after ${attempt}s"
    break
  fi
  if [[ "$attempt" == 120 ]]; then
    echo "ERROR: App did not become ready after AI provider setup" >&2
    exit 1
  fi
  sleep 1
done

echo "==> Seeding demo payers, patients, claims, invoices, and payments..."

APP_CSRF=$(curl -fsS -c "$APP_COOKIE" -H "Host: $APP_HOST" \
  "$BASE_URL/api/v1/appauth/login/" >/dev/null; grep csrftoken "$APP_COOKIE" | awk '{print $NF}')
curl -fsS -c "$APP_COOKIE" -b "$APP_COOKIE" -H "Host: $APP_HOST" \
  -H "X-CSRFToken: $APP_CSRF" -H 'Content-Type: application/json' \
  -X POST "$BASE_URL/api/v1/appauth/login/" \
  -d '{"email":"staff@billing.local","password":"Billing@123"}' \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("success") is True, d' \
  >/dev/null
APP_CSRF=$(grep csrftoken "$APP_COOKIE" | awk '{print $NF}')

MANAGER_CSRF=$(curl -fsS -c "$MANAGER_COOKIE" -H "Host: $APP_HOST" \
  "$BASE_URL/api/v1/appauth/login/" >/dev/null; grep csrftoken "$MANAGER_COOKIE" | awk '{print $NF}')
curl -fsS -c "$MANAGER_COOKIE" -b "$MANAGER_COOKIE" -H "Host: $APP_HOST" \
  -H "X-CSRFToken: $MANAGER_CSRF" -H 'Content-Type: application/json' \
  -X POST "$BASE_URL/api/v1/appauth/login/" \
  -d '{"email":"manager@billing.local","password":"Billing@123"}' \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("success") is True, d' \
  >/dev/null
MANAGER_CSRF=$(grep csrftoken "$MANAGER_COOKIE" | awk '{print $NF}')

table_pk() {
  local endpoint="$1" field="$2" value="$3"
  curl -fsS -b "$APP_COOKIE" -H "Host: $APP_HOST" \
    "$BASE_URL/$endpoint/?view=table&action=get_table_data&page=1&page_size=200" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); field,value=sys.argv[1:]; print(next(str(row["pk"]) for row in d.get("data",[]) if str(row.get(field,"")) == value))' "$field" "$value"
}

create_payer() {
  local name="$1" payer_id="$2" email="$3"
  if table_pk "payers" "payer_id" "$payer_id" >/dev/null 2>&1; then
    return
  fi
  curl -fsS -b "$APP_COOKIE" -H "Host: $APP_HOST" -H "X-CSRFToken: $APP_CSRF" \
    -X POST "$BASE_URL/payers/?form_type=create_form" \
    --data-urlencode "name=$name" --data-urlencode "payer_id=$payer_id" \
    --data-urlencode "contact_email=$email" | api_success >/dev/null
}

create_patient() {
  local first="$1" last="$2" dob="$3" email="$4" phone="$5" provider="$6" policy="$7" group="$8"
  if table_pk "patients" "email" "$email" >/dev/null 2>&1; then
    return
  fi
  curl -fsS -b "$APP_COOKIE" -H "Host: $APP_HOST" -H "X-CSRFToken: $APP_CSRF" \
    -X POST "$BASE_URL/patients/?form_type=create_form" \
    --data-urlencode "first_name=$first" --data-urlencode "last_name=$last" \
    --data-urlencode "date_of_birth=$dob" --data-urlencode "email=$email" \
    --data-urlencode "phone=$phone" --data-urlencode "address=42 Demo Street, Bengaluru" \
    --data-urlencode "insurance_provider=$provider" \
    --data-urlencode "insurance_policy_number=$policy" \
    --data-urlencode "insurance_group_number=$group" | api_success >/dev/null
}

create_claim() {
  local patient_email="$1" payer_id="$2" claim_number="$3" amount="$4" diagnosis="$5" notes="$6"
  if table_pk "claims" "claim_number" "$claim_number" >/dev/null 2>&1; then
    return
  fi
  local patient_pk payer_pk
  patient_pk=$(table_pk "patients" "email" "$patient_email")
  payer_pk=$(table_pk "payers" "payer_id" "$payer_id")
  curl -fsS -b "$APP_COOKIE" -H "Host: $APP_HOST" -H "X-CSRFToken: $APP_CSRF" \
    -X POST "$BASE_URL/claims/?form_type=create_form" \
    --data-urlencode "patient=$patient_pk" --data-urlencode "payer=$payer_pk" \
    --data-urlencode "claim_number=$claim_number" --data-urlencode "date_of_service=2026-06-15" \
    --data-urlencode "diagnosis_codes=$diagnosis" --data-urlencode "total_amount=$amount" \
    --data-urlencode "notes=$notes" | api_success >/dev/null
}

create_invoice() {
  local patient_email="$1" invoice_number="$2" amount="$3" due_date="$4" notes="$5"
  if table_pk "invoices" "invoice_number" "$invoice_number" >/dev/null 2>&1; then
    return
  fi
  local patient_pk
  patient_pk=$(table_pk "patients" "email" "$patient_email")
  curl -fsS -b "$APP_COOKIE" -H "Host: $APP_HOST" -H "X-CSRFToken: $APP_CSRF" \
    -X POST "$BASE_URL/invoices/?form_type=create_form" \
    --data-urlencode "patient=$patient_pk" --data-urlencode "invoice_number=$invoice_number" \
    --data-urlencode "date_issued=2026-07-01" --data-urlencode "due_date=$due_date" \
    --data-urlencode "total_amount=$amount" --data-urlencode "notes=$notes" \
    | api_success >/dev/null
}

create_payer "Blue Cross Demo" "SEED-PAYER-BCBS" "demo@bcbs.example"
create_payer "Aetna Demo" "SEED-PAYER-AETNA" "demo@aetna.example"
create_payer "UnitedHealth Demo" "SEED-PAYER-UHC" "demo@uhc.example"

create_patient "Asha" "Rao" "1988-03-12" "seed-asha@example.com" "+91 90000 00001" "Blue Cross Demo" "SEED-BCBS-001" "SEED-GRP-01"
create_patient "Rohan" "Mehta" "1979-11-04" "seed-rohan@example.com" "+91 90000 00002" "Aetna Demo" "SEED-AETNA-002" "SEED-GRP-02"
create_patient "Mira" "Iyer" "1992-07-26" "seed-mira@example.com" "+91 90000 00003" "UnitedHealth Demo" "SEED-UHC-003" "SEED-GRP-03"
create_patient "Kabir" "Shah" "1965-01-19" "seed-kabir@example.com" "+91 90000 00004" "Blue Cross Demo" "SEED-BCBS-004" "SEED-GRP-01"
create_patient "Nisha" "Patel" "2001-09-08" "seed-nisha@example.com" "+91 90000 00005" "Aetna Demo" "SEED-AETNA-005" "SEED-GRP-02"

create_claim "seed-asha@example.com" "SEED-PAYER-BCBS" "SEED-CLM-001" "425.00" '["J06.9"]' "Routine respiratory visit"
create_claim "seed-rohan@example.com" "SEED-PAYER-AETNA" "SEED-CLM-002" "780.00" '["M54.5"]' "Back pain evaluation"
create_claim "seed-mira@example.com" "SEED-PAYER-UHC" "SEED-CLM-003" "1250.00" '["E11.9"]' "Diabetes follow-up"
create_claim "seed-kabir@example.com" "SEED-PAYER-BCBS" "SEED-CLM-004" "310.00" '["I10"]' "Hypertension review"
create_claim "seed-nisha@example.com" "SEED-PAYER-AETNA" "SEED-CLM-005" "965.00" '["S93.4XXA"]' "Sprain treatment; authorization required"
create_claim "seed-asha@example.com" "SEED-PAYER-BCBS" "SEED-CLM-006" "540.00" '["K21.9"]' "Gastroenterology consultation"
create_claim "seed-rohan@example.com" "SEED-PAYER-AETNA" "SEED-CLM-007" "890.00" '["G43.909"]' "Migraine management"
create_claim "seed-mira@example.com" "SEED-PAYER-UHC" "SEED-CLM-008" "1500.00" '["N18.3"]' "Chronic care follow-up"

create_invoice "seed-asha@example.com" "SEED-INV-001" "425.00" "2026-07-31" "Self-pay consultation invoice"
create_invoice "seed-kabir@example.com" "SEED-INV-002" "640.00" "2026-08-15" "Follow-up services invoice"

compose exec -T app bash -lc "cd /zango/zango_project && python manage.py shell < /zango/scripts/seed_demo_payments.py" >/dev/null

transition_claim() {
  local cookie="$1" csrf="$2" object_uuid="$3" transition="$4"
  curl -fsS -b "$cookie" -H "Host: $APP_HOST" -H "X-CSRFToken: $csrf" \
    -X POST "$BASE_URL/claims/?view=workflow&action=process_transition&transition_name=$transition&transition_type=status&object_uuid=$object_uuid" \
    | api_success >/dev/null
}

CLAIM_001_UUID=$(curl -fsS -b "$APP_COOKIE" -H "Host: $APP_HOST" "$BASE_URL/claims/?view=table&action=get_table_data&page=1&page_size=200" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(next(r["object_uuid"] for r in d["data"] if r.get("claim_number") == "SEED-CLM-001"))')
CLAIM_002_UUID=$(curl -fsS -b "$APP_COOKIE" -H "Host: $APP_HOST" "$BASE_URL/claims/?view=table&action=get_table_data&page=1&page_size=200" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(next(r["object_uuid"] for r in d["data"] if r.get("claim_number") == "SEED-CLM-002"))')
CLAIM_003_UUID=$(curl -fsS -b "$APP_COOKIE" -H "Host: $APP_HOST" "$BASE_URL/claims/?view=table&action=get_table_data&page=1&page_size=200" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(next(r["object_uuid"] for r in d["data"] if r.get("claim_number") == "SEED-CLM-003"))')
CLAIM_004_UUID=$(curl -fsS -b "$APP_COOKIE" -H "Host: $APP_HOST" "$BASE_URL/claims/?view=table&action=get_table_data&page=1&page_size=200" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(next(r["object_uuid"] for r in d["data"] if r.get("claim_number") == "SEED-CLM-004"))')
CLAIM_005_UUID=$(curl -fsS -b "$APP_COOKIE" -H "Host: $APP_HOST" "$BASE_URL/claims/?view=table&action=get_table_data&page=1&page_size=200" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(next(r["object_uuid"] for r in d["data"] if r.get("claim_number") == "SEED-CLM-005"))')

claim_status() { curl -fsS -b "$APP_COOKIE" -H "Host: $APP_HOST" "$BASE_URL/claims/?view=table&action=get_table_data&page=1&page_size=200" | python3 -c 'import json,sys; d=json.load(sys.stdin); u=sys.argv[1]; r=next(r for r in d["data"] if str(r.get("object_uuid")) == u); s=r.get("workflow_status",""); print((s.get("status_label","") if isinstance(s,dict) else s).lower())' "$1"; }
ensure_claim_status() {
  local uuid="$1" target="$2"
  local status
  while true; do
    status=$(claim_status "$uuid")
    case "$status" in
      *"draft"*) [[ "$target" == "draft" ]] && break; transition_claim "$APP_COOKIE" "$APP_CSRF" "$uuid" submit ;;
      *"submitted"*) [[ "$target" == "submitted" ]] && break; transition_claim "$MANAGER_COOKIE" "$MANAGER_CSRF" "$uuid" begin_review ;;
      *"under review"*) [[ "$target" == "under_review" ]] && break; transition_claim "$MANAGER_COOKIE" "$MANAGER_CSRF" "$uuid" "$([[ "$target" == "approved" ]] && echo approve || echo deny)" ;;
      *"approved"*|*"denied"*|*"appealed"*) break ;;
      *) echo "ERROR: unexpected seed claim status '$status' for $uuid" >&2; exit 1 ;;
    esac
  done
}
ensure_claim_status "$CLAIM_001_UUID" submitted
ensure_claim_status "$CLAIM_002_UUID" under_review
ensure_claim_status "$CLAIM_003_UUID" approved
ensure_claim_status "$CLAIM_004_UUID" denied
ensure_claim_status "$CLAIM_005_UUID" draft

echo "    Seed data is present; SEED-CLM-004 was submitted and denied through Celery."

echo
echo "========================================"
echo "Demo bootstrap complete"
echo "App URL:      $APP_URL"
echo "Platform URL: $PLATFORM_URL"
echo "Staff login:  staff@billing.local / Billing@123"
echo "Manager login: manager@billing.local / Billing@123"
echo "========================================"
