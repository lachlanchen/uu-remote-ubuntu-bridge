#!/usr/bin/env bash

set -Eeuo pipefail

architecture="$(uname -m)"
printf 'Host CPU architecture: %s\n' "$architecture"
if [[ "$architecture" != x86_64 ]]; then
    printf '%s\n' \
        'Unsupported host: this bridge requires x86_64 Ubuntu 24.04.' \
        'The UU Windows client, injected DLLs, and pinned Wine/FreeRDP runtime are x86-64.' \
        'ARM64/aarch64 (including Oracle Ampere VPS) is not a supported runtime.' \
        'Installing Wine or cross-compiling the DLLs does not provide x86 CPU emulation.' \
        'Do not bypass this check. See docs/compatibility.md for alternatives.' >&2
    exit 1
fi
if [[ ! -r /etc/os-release ]]; then
    printf 'Cannot identify this operating system.\n' >&2
    exit 1
fi
# shellcheck source=/dev/null
source /etc/os-release
if [[ "${ID:-}" != ubuntu || "${VERSION_ID:-}" != 24.04 ]]; then
    printf 'Only Ubuntu 24.04 is currently supported; detected %s %s.\n' \
        "${ID:-unknown}" "${VERSION_ID:-unknown}" >&2
    exit 1
fi
printf '%s\n' \
    'Supported OS/CPU baseline: Ubuntu 24.04 x86_64.' \
    'Runtime still requires a logged-in GNOME 46 desktop, Wine, and relay dependencies.' \
    'This read-only check does not install packages or prove remote-control acceptance.'
if [[ $EUID -eq 0 ]]; then
    printf 'Run the actual installer as the desktop user, not root.\n'
fi
