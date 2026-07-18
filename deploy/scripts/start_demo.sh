#!/usr/bin/env bash
# Clone-and-run entry point for the zero-cost local Patient Billing demo.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
DEPLOY_DIR="$REPO_DIR/deploy"
ENV_FILE="$DEPLOY_DIR/.env"
ENV_EXAMPLE="$DEPLOY_DIR/.env.example"
COMPOSE_FILE="$DEPLOY_DIR/docker_compose.yml"
APP_HOST="patientbilling.localhost"
APP_URL="http://${APP_HOST}:8000/app"
PLATFORM_URL="http://localhost:8000/platform"
READY_TIMEOUT="300"

error() {
  echo "ERROR: $*" >&2
  exit 1
}

command -v docker >/dev/null 2>&1 || error "Docker is required. Install Docker Desktop or Docker Engine first."
command -v node >/dev/null 2>&1 || error "Node.js is required to build the frontend bundle."
command -v npm >/dev/null 2>&1 || error "npm is required to build the frontend bundle."
command -v curl >/dev/null 2>&1 || error "curl is required for readiness checks."

NODE_MAJOR="$(node -p 'Number(process.versions.node.split(".")[0])' 2>/dev/null)"
[[ "$NODE_MAJOR" =~ ^[0-9]+$ && "$NODE_MAJOR" -ge 18 ]] || error "Node.js 18 or newer is required."

DOCKER_MODE=""
if docker info >/dev/null 2>&1; then
  DOCKER_MODE="direct"
elif command -v sg >/dev/null 2>&1 && sg docker -c "docker info" >/dev/null 2>&1; then
  DOCKER_MODE="sg"
else
  error "Docker is not running or this user cannot access the Docker daemon."
fi

docker_compose() {
  if [[ "$DOCKER_MODE" == "direct" ]]; then
    HOST_UID="$HOST_UID_VALUE" HOST_GID="$HOST_GID_VALUE" \
      docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
  else
    local arg quoted_arg command
    command="HOST_UID=$HOST_UID_VALUE HOST_GID=$HOST_GID_VALUE docker compose --env-file $(printf '%q' "$ENV_FILE") -f $(printf '%q' "$COMPOSE_FILE")"
    for arg in "$@"; do
      printf -v quoted_arg '%q' "$arg"
      command+=" $quoted_arg"
    done
    sg docker -c "$command"
  fi
}

docker_inspect() {
  local format="$1" container_id="$2"
  if [[ "$DOCKER_MODE" == "direct" ]]; then
    docker inspect --format "$format" "$container_id"
  else
    sg docker -c "docker inspect --format $(printf '%q' "$format") $(printf '%q' "$container_id")"
  fi
}

if [[ "$DOCKER_MODE" == "direct" ]]; then
  docker compose version >/dev/null 2>&1 || error "Docker Compose v2 is required (the 'docker compose' command)."
else
  sg docker -c "docker compose version" >/dev/null 2>&1 || error "Docker Compose v2 is required (the 'docker compose' command)."
fi

[[ -f "$ENV_EXAMPLE" ]] || error "Missing $ENV_EXAMPLE."
[[ -f "$COMPOSE_FILE" ]] || error "Missing $COMPOSE_FILE."

if ! node -e '
const dns = require("dns");
const host = process.argv[1];
dns.lookup(host, {all: true}, (err, addresses) => {
  if (err) process.exit(1);
  const loopback = addresses.some(({address}) =>
    address === "127.0.0.1" || address === "::1" || address === "::ffff:127.0.0.1"
  );
  process.exit(loopback ? 0 : 1);
});
' "$APP_HOST"; then
  error "Hostname resolution failed. Add exactly '127.0.0.1 $APP_HOST' to /etc/hosts, then run this script again."
fi

if [[ ! -e "$ENV_FILE" ]]; then
  cp "$ENV_EXAMPLE" "$ENV_FILE"
  echo "==> Created deploy/.env from deploy/.env.example"
elif [[ ! -f "$ENV_FILE" ]]; then
  error "$ENV_FILE exists but is not a regular file."
else
  echo "==> Reusing existing deploy/.env (its values will not be printed)"
fi

HOST_UID_VALUE="$(id -u)"
HOST_GID_VALUE="$(id -g)"
[[ "$HOST_UID_VALUE" =~ ^[0-9]+$ && "$HOST_GID_VALUE" =~ ^[0-9]+$ ]] || error "Could not determine the current host UID and GID."

compose() {
  docker_compose "$@"
}

echo "==> Building the frontend bundle from package-lock.json..."
bash "$SCRIPT_DIR/build_frontend.sh"

safe_diagnostics() {
  local service="$1"
  echo "    Diagnose with: docker compose -f deploy/docker_compose.yml ps $service" >&2
  echo "    Then inspect explicitly: docker compose -f deploy/docker_compose.yml logs --tail=80 $service" >&2
}

service_state() {
  local service="$1" container_id
  container_id="$(compose ps -q "$service")"
  [[ -n "$container_id" ]] || return 1
  docker_inspect '{{.State.Status}}' "$container_id"
}

require_running() {
  local service="$1" state
  state="$(service_state "$service" || true)"
  if [[ "$state" != "running" ]]; then
    safe_diagnostics "$service"
    error "The $service service is not running."
  fi
}

echo "==> Starting PostgreSQL and Redis..."
compose up -d postgres redis

echo "==> Waiting for PostgreSQL to become healthy..."
for attempt in $(seq 1 "$READY_TIMEOUT"); do
  postgres_id="$(compose ps -q postgres)"
  postgres_state="$(docker_inspect '{{.State.Status}}' "$postgres_id" 2>/dev/null || true)"
  postgres_health="$(docker_inspect '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$postgres_id" 2>/dev/null || true)"
  if [[ "$postgres_state" == "running" && "$postgres_health" == "healthy" ]]; then
    echo "    PostgreSQL is healthy after ${attempt}s"
    break
  fi
  if [[ "$attempt" == "$READY_TIMEOUT" ]]; then
    safe_diagnostics postgres
    error "PostgreSQL did not become healthy within ${READY_TIMEOUT}s."
  fi
  sleep 1
done

echo "==> Building and starting the app..."
compose up -d --build app

echo "==> Waiting for the platform endpoint..."
for attempt in $(seq 1 "$READY_TIMEOUT"); do
  require_running app
  if curl -fsS --connect-timeout 2 -o /dev/null "$PLATFORM_URL"; then
    echo "    Platform is ready after ${attempt}s"
    break
  fi
  if [[ "$attempt" == "$READY_TIMEOUT" ]]; then
    safe_diagnostics app
    error "The platform endpoint did not become ready within ${READY_TIMEOUT}s."
  fi
  sleep 1
done

echo "==> Starting Celery and Celery Beat..."
compose up -d celery celery_beat
require_running celery
require_running celery_beat

echo "==> Running the idempotent demo bootstrap with explicit offline AI..."
LOCAL_FAKE_AI=true SKIP_FRONTEND_BUILD=true bash "$SCRIPT_DIR/bootstrap_demo.sh"

require_running celery
require_running celery_beat
curl -fsS --connect-timeout 2 -o /dev/null "$APP_URL" || {
  safe_diagnostics app
  error "The application endpoint did not respond after bootstrap."
}

echo
echo "Demo is ready (offline fake AI is active; no API key was used)."
echo "App URL:      $APP_URL"
echo "Platform URL: $PLATFORM_URL"
echo "Staff login:  staff@billing.local / Billing@123"
echo "Manager login: manager@billing.local / Billing@123"
echo
echo "Real AI setup is separate and explicit; see README.md for provider commands."
