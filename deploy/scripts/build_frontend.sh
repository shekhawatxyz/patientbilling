#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
FRONTEND_DIR="$REPO_DIR/deploy/zango_project/workspaces/patientbilling/frontend"
STATIC_DIR="$REPO_DIR/deploy/zango_project/workspaces/patientbilling/static/js"

command -v npm >/dev/null 2>&1 || {
  echo "ERROR: npm is required to build the frontend bundle." >&2
  exit 1
}

echo "==> Installing frontend dependencies from package-lock.json..."
cd "$FRONTEND_DIR"
npm ci

echo "==> Building the Zango frontend bundle..."
npm run build:zango

mkdir -p "$STATIC_DIR"
cp zango-build/zango-app.min.js "$STATIC_DIR/zango-app.min.js"
echo "Frontend bundle ready: $STATIC_DIR/zango-app.min.js"
