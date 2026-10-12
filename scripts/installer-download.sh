#!/usr/bin/env bash
# Sourced installer helpers; no Wine, desktop, or service side effects.

select_install_manifest() {
    local requested="$1" installed="$2" product="$3" repository="$4"
    if [[ -n "$requested" ]]; then
        printf '%s\n' "$requested"
    elif [[ -f "$installed" && -f "$product" ]]; then
        # A plain reinstall must not silently select a different binary patch.
        printf '%s\n' "$installed"
    else
        # Maintainer-accepted fresh-install baseline, not the moving CDN version.
        printf '%s/patches/uu-remote-4.42.1.2835.json\n' "$repository"
    fi
}

download_verified() {
    local url="$1" expected="$2" destination="$3" temporary actual
    if [[ -f "$destination" ]] &&
       printf '%s  %s\n' "$expected" "$destination" | sha256sum -c - >/dev/null 2>&1; then
        return 0
    fi
    mkdir -p "$(dirname -- "$destination")"
    temporary="$(mktemp "$destination.part.XXXXXX")" || return 1
    # NetEase's endpoint moves between releases. Never combine HTTP ranges or
    # resume a previous release's partial file, even after a transient failure.
    if ! curl --fail --location --show-error --connect-timeout 20 \
        --max-time 900 --retry 0 --output "$temporary" "$url"; then
        rm -f -- "$temporary"
        printf 'UU installer download failed; existing cached files were preserved.\n' >&2
        return 1
    fi
    actual="$(sha256sum "$temporary" | awk '{print $1}')"
    if [[ "$actual" != "$expected" ]]; then
        rm -f -- "$temporary"
        printf 'UU installer hash mismatch: expected %s, received %s.\n' "$expected" "$actual" >&2
        printf '%s\n' \
            'The official latest URL can serve a different release during a rollout.' \
            'No installer was executed. Use --uu-installer PATH with its matching approved --release-manifest PATH.' \
            'Do not edit the approved hash or bypass verification to accept a newer download.' >&2
        return 1
    fi
    mv -f -- "$temporary" "$destination"
}
