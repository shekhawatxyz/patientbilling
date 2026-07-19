#!/bin/sh

set -eu

ENV_FILE="/zango/.env"
if [ "${ENV:-}" = "prod" ]; then
    ENV_FILE="/zango/.env.prod"
fi

set -a
. "$ENV_FILE"
set +a

error() {
    echo "ERROR: $1" >&2
    exit 1
}

if [ -z "${PLATFORM_DOMAIN_URL:-}" ]; then
    PLATFORM_DOMAIN_URL="localhost"
fi

# Install custom providers into the Zango package before startup.
if ! /zango/scripts/sync_providers.sh; then
    error "Provider synchronization failed during container startup."
fi

cd /zango

# Recovery after a partial start-project: if the public tenant was created but platform
# user creation did not complete, retries may not create the user again. From the project
# directory, recreate it explicitly with:
#   python manage.py shell -c 'from zango.cli.start_project import create_platform_user; create_platform_user("username", "password")'
# Run this only when the public tenant has no platform user yet.
echo "Initializing project database..."
if ! zango start-project "$PROJECT_NAME" \
        --db_name="$POSTGRES_DB" \
        --db_user="$POSTGRES_USER" \
        --db_password="$POSTGRES_PASSWORD" \
        --db_host="$POSTGRES_HOST" \
        --db_port="$POSTGRES_PORT" \
        --platform_username="$PLATFORM_USERNAME" \
        --platform_user_password="$PLATFORM_USER_PASSWORD" \
        --redis_host="$REDIS_HOST" \
        --redis_port="$REDIS_PORT" \
        --platform_domain_url="$PLATFORM_DOMAIN_URL"; then
    error "Project initialization failed during start-project."
fi

cd "$PROJECT_NAME" || error "Initialized project directory is unavailable."

WORKSPACE_NAME="${WORKSPACE_NAME:-patientbilling}"

if [ "${UPDATE_APPS_ON_STARTUP:-true}" = "true" ]; then
    echo "Updating apps..."
    if ! SINGLE_BEAT_REDIS_SERVER="redis://${REDIS_HOST}:${REDIS_PORT}/1" \
        single-beat zango update-apps; then
        error "Application update failed during update-apps."
    fi
fi

echo "Ensuring workflow and AppBuilder package migrations are applied..."
workspace_present=$(python manage.py shell -c \
    "from zango.apps.shared.tenancy.models import TenantModel; print('yes' if TenantModel.objects.filter(name='$WORKSPACE_NAME').exists() else 'no')")
if [ "$workspace_present" = "yes" ]; then
    for package in workflow appbuilder; do
        if ! python manage.py ws_migrate "$WORKSPACE_NAME" --package "$package"; then
            error "Package migration failed for $package."
        fi
    done
else
    echo "Workspace $WORKSPACE_NAME does not exist yet; deferring package migrations to bootstrap."
fi

# --insecure: DEBUG=False (PAT-86) disables Django's automatic static-file
# serving; --insecure restores it without reverting DEBUG. This is a demo-grade
# stopgap -- the prod-grade path is Caddy `file_server`/WhiteNoise serving
# static assets directly instead of falling through to Django (see PAT-94).
exec python manage.py runserver --insecure 0.0.0.0:8000
