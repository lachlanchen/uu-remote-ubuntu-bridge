#!/usr/bin/env bash
set -Eeuo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
for command in x86_64-w64-mingw32-gcc xvfb-run timeout \
    /opt/wine-stable/bin/wine /opt/wine-stable/bin/wineserver; do
    command -v "$command" >/dev/null || {
        printf 'missing cursor-log test command: %s\n' "$command" >&2
        exit 1
    }
done
temporary_dir="$(mktemp -d "${TMPDIR:-/tmp}/uurb-cursor-log.XXXXXX")"
export WINEPREFIX="$temporary_dir/wine"
export WINEDEBUG=-all
export WINEDLLOVERRIDES='mscoree,mshtml='
cleanup() {
    local status=$?
    trap - EXIT
    /opt/wine-stable/bin/wineserver -k >/dev/null 2>&1 || true
    timeout 10 /opt/wine-stable/bin/wineserver -w >/dev/null 2>&1 || true
    if [[ "$status" -eq 0 && "${UURB_KEEP_TEST_TMP:-0}" != 1 ]]; then
        rm -rf -- "$temporary_dir"
    else
        printf 'isolated cursor-log artifacts: %s\n' "$temporary_dir" >&2
    fi
    exit "$status"
}
trap cleanup EXIT

x86_64-w64-mingw32-gcc -std=c11 -O2 -Wall -Wextra -Werror \
    -o "$temporary_dir/cursor-log-probe.exe" \
    "$repo_dir/tests/probes/uu_cursor_log_probe.c" -luser32 -lgdi32
cd -- "$temporary_dir"
timeout 90 xvfb-run -a bash -c '
    status=0
    /opt/wine-stable/bin/wine "$1" cursor-log.txt || status=$?
    /opt/wine-stable/bin/wineserver -k || true
    timeout 10 /opt/wine-stable/bin/wineserver -w || true
    exit "$status"
' _ \
    "$temporary_dir/cursor-log-probe.exe"
