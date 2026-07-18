#!/usr/bin/env bash

set -euo pipefail

if [[ "$#" -eq 0 ]]; then
    first_file="deploy/.env"
    second_file="deploy/.env.example"
elif [[ "$#" -eq 2 ]]; then
    first_file="$1"
    second_file="$2"
else
    printf 'Usage: %s [ENV_FILE ENV_EXAMPLE_FILE]\n' "$0" >&2
    exit 2
fi

for env_file in "$first_file" "$second_file"; do
    if [[ ! -r "$env_file" ]]; then
        printf 'Cannot read env file: %s\n' "$env_file" >&2
        exit 2
    fi
done

# Compare names only; values never enter either diff input or its output.
diff \
    <(grep -o '^[A-Z_][A-Z_0-9]*' "$first_file" | sort) \
    <(grep -o '^[A-Z_][A-Z_0-9]*' "$second_file" | sort)
