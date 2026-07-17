#!/bin/sh

set -eu

# Each Compose service has its own container filesystem. Copy the workspace's
# custom providers into the installed Zango package before importing the app.
PROVIDERS_DIR="$(python3 -c 'import os; import zango.ai.providers; print(os.path.dirname(zango.ai.providers.__file__))')"

if [ ! -d /zango/providers ]; then
    exit 0
fi

for provider_file in /zango/providers/*.py; do
    [ -f "$provider_file" ] || continue
    provider_slug=$(basename "$provider_file" .py)
    destination="$PROVIDERS_DIR/$provider_slug.py"

    sudo cp "$provider_file" "$destination" 2>/dev/null || cp "$provider_file" "$destination"

    import_line="from . import $provider_slug"
    if ! grep -Fq "$import_line" "$PROVIDERS_DIR/__init__.py" 2>/dev/null; then
        import_block=$(printf '\ntry:\n    from . import %s  # noqa: F401\nexcept ImportError:\n    pass\n' "$provider_slug")
        printf '%s' "$import_block" | sudo tee -a "$PROVIDERS_DIR/__init__.py" >/dev/null 2>/dev/null \
            || printf '%s' "$import_block" >> "$PROVIDERS_DIR/__init__.py"
    fi
done
