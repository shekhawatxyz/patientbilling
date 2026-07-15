#!/bin/bash

set -a
source /zango/.env
set +a

if [ -z "$PLATFORM_DOMAIN_URL" ]; then
    PLATFORM_DOMAIN_URL="localhost"
fi

# Install custom providers (Gemini etc.) into the Zango package before startup
PROVIDERS_DIR=$(python3 -c "import zango.ai.providers, os; print(os.path.dirname(zango.ai.providers.__file__))" 2>/dev/null)
if [ -n "$PROVIDERS_DIR" ] && [ -d /zango/providers ]; then
    for f in /zango/providers/*.py; do
        [ -f "$f" ] || continue
        slug=$(basename "$f" .py)
        dest="$PROVIDERS_DIR/$slug.py"
        cp "$f" "$dest"
        if ! grep -q "from . import $slug" "$PROVIDERS_DIR/__init__.py" 2>/dev/null; then
            printf "\ntry:\n    from . import %s  # noqa: F401\nexcept ImportError:\n    pass\n" "$slug" >> "$PROVIDERS_DIR/__init__.py"
        fi
    done
fi

cd "$PROJECT_NAME" 2>/dev/null

if [ -d "$PROJECT_NAME" ]; then
    echo "Restarting existing project..."
    if [ "${UPDATE_APPS_ON_STARTUP:-true}" = "true" ]; then
        echo "Updating apps..."
        SINGLE_BEAT_REDIS_SERVER=redis://${REDIS_HOST}:${REDIS_PORT}/1 single-beat zango update-apps
    fi
else
    cd /zango
    zango start-project $PROJECT_NAME \
        --db_name="$POSTGRES_DB" \
        --db_user="$POSTGRES_USER" \
        --db_password="$POSTGRES_PASSWORD" \
        --db_host="$POSTGRES_HOST" \
        --db_port="$POSTGRES_PORT" \
        --platform_username="$PLATFORM_USERNAME" \
        --platform_user_password="$PLATFORM_USER_PASSWORD" \
        --redis_host="$REDIS_HOST" \
        --redis_port="$REDIS_PORT" \
        --platform_domain_url="$PLATFORM_DOMAIN_URL"
    cd "$PROJECT_NAME"
fi

python manage.py runserver 0.0.0.0:8000
