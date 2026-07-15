#!/bin/bash

set -a
source /zango/.env
set +a

if [ -z "$PLATFORM_DOMAIN_URL" ]; then
    PLATFORM_DOMAIN_URL="localhost"
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
