#!/usr/bin/env bash

set -Eeuo pipefail
umask 077
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
temporary_dir="$(mktemp -d "${TMPDIR:-/tmp}/uurb-updater-guard.XXXXXX")"
export WINEPREFIX="$temporary_dir/prefix" WINEDEBUG=-all DISPLAY=
export WINEDLLOVERRIDES='winedbg.exe=d;mscoree,mshtml='
wine_bin=/opt/wine-stable/bin/wine
cleanup() {
    local status=$?
    trap - EXIT
    timeout 10 /opt/wine-stable/bin/wineserver -k >/dev/null 2>&1 || true
    timeout 10 /opt/wine-stable/bin/wineserver -w >/dev/null 2>&1 || true
    if ((status == 0)); then
        rm -rf -- "$temporary_dir"
    else
        printf 'Guard test artifacts retained: %s\n' "$temporary_dir" >&2
    fi
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT TERM HUP
x86_64-w64-mingw32-gcc -O2 -Wall -Wextra -Werror \
    "$repo_dir/tests/probes/uu_exit_probe.c" -o "$temporary_dir/Upgrade.exe"
timeout --kill-after=5s 120 "$wine_bin" wineboot -u >"$temporary_dir/boot.log" 2>&1
status=0
timeout 20 "$wine_bin" "$temporary_dir/Upgrade.exe" || status=$?
[[ "$status" == 42 ]]
status=0
WINEDLLOVERRIDES="upgrade.exe=d;$WINEDLLOVERRIDES" \
    timeout 20 "$wine_bin" "$temporary_dir/Upgrade.exe" \
    >"$temporary_dir/disabled.log" 2>&1 || status=$?
# Wine returns STATUS_DLL_NOT_FOUND's low byte, even with diagnostics disabled.
[[ "$status" == 53 ]]
cp "$temporary_dir/Upgrade.exe" "$temporary_dir/Ordinary.exe"
status=0
WINEDLLOVERRIDES="upgrade.exe=d;$WINEDLLOVERRIDES" \
    timeout 20 "$wine_bin" "$temporary_dir/Ordinary.exe" || status=$?
[[ "$status" == 42 ]]
printf 'vendor-updater-guard=blocked harmless Upgrade.exe; ordinary execution=42\n'
