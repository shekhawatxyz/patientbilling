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
command -v getent >/dev/null 2>&1 || error "getent is required to verify the $APP_HOST host mapping."

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
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
  else
    local arg quoted_arg command="docker compose --env-file $(printf '%q' "$ENV_FILE") -f $(printf '%q' "$COMPOSE_FILE")"
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

docker_compose version >/dev/null 2>&1 || error "Docker Compose v2 is required (the 'docker compose' command)."

[[ -f "$ENV_EXAMPLE" ]] || error "Missing $ENV_EXAMPLE."
[[ -f "$COMPOSE_FILE" ]] || error "Missing $COMPOSE_FILE."

if ! getent ahostsv4 "$APP_HOST" | awk '$1 == "127.0.0.1" { found=1 } END { exit(found ? 0 : 1) }'; then
  error "Add '127.0.0.1 $APP_HOST' to /etc/hosts, then run this script again."
fi

if [[ ! -e "$ENV_FILE" ]]; then
  cp "$ENV_EXAMPLE" "$ENV_FILE"
  echo "==> Created deploy/.env from deploy/.env.example"
elif [[ ! -f "$ENV_FILE" ]]; then
  error "$ENV_FILE exists but is not a regular file."
else
  echo "==> Reusing existing deploy/.env (its values will not be printed)"
fi

compose() {
  docker_compose "$@"
}

echo "==> Building the frontend bundle from package-lock.json..."
bash "$SCRIPT_DIR/build_frontend.sh"

echo "==> Starting PostgreSQL, Redis, app, Celery, and Celery Beat..."
compose up -d --build

echo "==> Waiting for all demo services to be running and healthy..."
for attempt in $(seq 1 "$READY_TIMEOUT"); do
  failed_service=""
  waiting_service=""
  for service in postgres redis app celery celery_beat; do
    container_id="$(compose ps -q "$service")"
    if [[ -z "$container_id" ]]; then
      waiting_service="$service"
      continue
    fi
    state="$(docker_inspect '{{.State.Status}}' "$container_id")"
    if [[ "$state" == "exited" || "$state" == "dead" ]]; then
      failed_service="$service"
      break
    fi
    if [[ "$state" != "running" ]]; then
      waiting_service="$service"
      continue
    fi
    health="$(docker_inspect '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container_id")"
    if [[ "$health" == "unhealthy" ]]; then
      failed_service="$service"
      break
    elif [[ "$health" != "healthy" && "$health" != "none" ]]; then
      waiting_service="$service"
    fi
  done

  [[ -z "$failed_service" ]] || {
    compose logs --tail=80 "$failed_service" >&2 || true
    error "The $failed_service service failed to start."
  }

  if [[ -z "$waiting_service" ]] && curl -fsS --connect-timeout 2 -o /dev/null "$PLATFORM_URL"; then
    echo "    Services are ready after ${attempt}s"
    break
  fi

  if [[ "$attempt" == "$READY_TIMEOUT" ]]; then
    compose ps >&2 || true
    compose logs --tail=80 app celery celery_beat >&2 || true
    error "The demo services did not become ready within ${READY_TIMEOUT}s."
  fi
  sleep 1
done

echo "==> Running the idempotent demo bootstrap with explicit offline AI..."
LOCAL_FAKE_AI=true SKIP_FRONTEND_BUILD=true bash "$SCRIPT_DIR/bootstrap_demo.sh"

echo
echo "Demo is ready (offline fake AI is active; no API key was used)."
echo "App URL:      $APP_URL"
echo "Platform URL: $PLATFORM_URL"
echo "Staff login:  staff@billing.local / Billing@123"
echo "Manager login: manager@billing.local / Billing@123"
echo
echo "To configure a real provider deliberately, add a key to deploy/.env and run:"
echo "  set -a; source deploy/.env; set +a; bash deploy/scripts/setup_ai.sh"
