#!/usr/bin/env bash

# Resolve the only setting whose fresh-install default intentionally differs
# from the v0.1.0 behavior. This file is sourced by install.sh and can be
# tested without running the installer.
resolve_text_key_delay() {
    local environment_file="$1"
    local saved_value="${2:-}"

    if [[ -n "${UURB_TEXT_KEY_DELAY_MS:-}" ]]; then
        printf '%s\n' "$UURB_TEXT_KEY_DELAY_MS"
    elif [[ -n "$saved_value" ]]; then
        printf '%s\n' "$saved_value"
    elif [[ -f "$environment_file" ]]; then
        # v0.1.0 created this file without a pacing key.
        printf '0\n'
    else
        printf '8\n'
    fi
}
