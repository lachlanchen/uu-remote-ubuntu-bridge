#!/usr/bin/env bash

set -Eeuo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
temporary_dir="$(mktemp -d "${TMPDIR:-/tmp}/uurb-controller-clipboard.XXXXXX")"
wine_prefix="$temporary_dir/wine"
ready_file="$temporary_dir/x11-clipboard.port"
token="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
host_xvfb_pid=""
wine_xvfb_pid=""
helper_pid=""
companion_pid=""
fixture_pid=""

cleanup() {
    local status=$?
    local pid

    trap - EXIT
    for pid in "$fixture_pid" "$companion_pid" "$helper_pid" \
        "$wine_xvfb_pid" "$host_xvfb_pid"; do
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    if [[ -d "$wine_prefix" ]]; then
        WINEPREFIX="$wine_prefix" /opt/wine-stable/bin/wineserver -k \
            >/dev/null 2>&1 || true
    fi
    wait 2>/dev/null || true
    if [[ "${UURB_KEEP_TEST_TMP:-0}" == 1 || "$status" -ne 0 ]]; then
        printf 'isolated test artifacts: %s\n' "$temporary_dir" >&2
    elif [[ "$temporary_dir" == "${TMPDIR:-/tmp}/uurb-controller-clipboard."* ]]; then
        rm -rf -- "$temporary_dir"
    fi
    exit "$status"
}
trap cleanup EXIT

for command in flock timeout Xvfb xclip xdpyinfo \
    x86_64-w64-mingw32-gcc /opt/wine-stable/bin/wine \
    /opt/wine-stable/bin/wineboot; do
    command -v "$command" >/dev/null 2>&1 || {
        printf 'missing controller-clipboard test command: %s\n' "$command" >&2
        exit 1
    }
done

exec 9>"${TMPDIR:-/tmp}/uurb-isolated-x-display.lock"
flock -x 9
host_display=""
wine_display=""
for number in {88..99}; do
    if [[ ! -S "/tmp/.X11-unix/X$number" ]]; then
        if [[ -z "$host_display" ]]; then
            host_display=":$number"
        else
            wine_display=":$number"
            break
        fi
    fi
done
[[ -n "$host_display" && -n "$wine_display" ]] || {
    printf 'two free isolated X displays are required in :88..:99\n' >&2
    exit 1
}

"$repo_dir/scripts/build-compat.sh" "$temporary_dir/compat" >/dev/null
x86_64-w64-mingw32-gcc -std=c11 -O2 -Wall -Wextra -Werror \
    -municode -mwindows \
    -DUURB_FIXTURE_TEXT='L"Mac controller 中文\r\nsecond line"' \
    -o "$temporary_dir/GameViewer.exe" \
    "$repo_dir/tests/probes/uu_controller_clipboard_fixture.c" -luser32
x86_64-w64-mingw32-gcc -std=c11 -O2 -Wall -Wextra -Werror \
    -municode -mwindows \
    -DUURB_FIXTURE_TEXT='L"must not leave OtherApp"' \
    -o "$temporary_dir/OtherApp.exe" \
    "$repo_dir/tests/probes/uu_controller_clipboard_fixture.c" -luser32

Xvfb "$host_display" -screen 0 800x600x24 -ac -nolisten tcp \
    >"$temporary_dir/host-xvfb.log" 2>&1 &
host_xvfb_pid=$!
Xvfb "$wine_display" -screen 0 800x600x24 -ac -nolisten tcp \
    >"$temporary_dir/wine-xvfb.log" 2>&1 &
wine_xvfb_pid=$!
for _ in {1..50}; do
    if DISPLAY="$host_display" timeout 0.5 xdpyinfo >/dev/null 2>&1 9>&- &&
       DISPLAY="$wine_display" timeout 0.5 xdpyinfo >/dev/null 2>&1 9>&-; then
        break
    fi
    sleep 0.1
done
DISPLAY="$host_display" timeout 5 xdpyinfo >/dev/null 9>&-
DISPLAY="$wine_display" timeout 5 xdpyinfo >/dev/null 9>&-
flock -u 9

DISPLAY="$host_display" UURB_X11_CLIPBOARD_TOKEN="$token" \
    "$temporary_dir/compat/uu-x11-clipboard" --ready-file "$ready_file" \
    >"$temporary_dir/x11-clipboard.log" 2>&1 &
helper_pid=$!
for _ in {1..50}; do
    [[ -s "$ready_file" ]] && break
    sleep 0.1
done
[[ -s "$ready_file" ]]
port="$(tr -d '[:space:]' <"$ready_file")"

DISPLAY="$wine_display" WINEPREFIX="$wine_prefix" WINEDEBUG=-all \
    WINEDLLOVERRIDES='mscoree,mshtml=' \
    /opt/wine-stable/bin/wineboot -u >/dev/null 2>&1
DISPLAY="$wine_display" WINEPREFIX="$wine_prefix" WINEDEBUG=-all \
    WINEDLLOVERRIDES='mscoree,mshtml=' \
    UURB_X11_CLIPBOARD_PORT="$port" UURB_X11_CLIPBOARD_TOKEN="$token" \
    /opt/wine-stable/bin/wine \
    "$temporary_dir/compat/uu-wine-clipboard-bridge.exe" \
    >"$temporary_dir/companion.log" 2>&1 &
companion_pid=$!
sleep 0.2

DISPLAY="$wine_display" WINEPREFIX="$wine_prefix" WINEDEBUG=-all \
    WINEDLLOVERRIDES='mscoree,mshtml=' \
    /opt/wine-stable/bin/wine "$temporary_dir/GameViewer.exe" &
fixture_pid=$!
expected=$'Mac controller 中文\nsecond line'
observed=""
for _ in {1..80}; do
    observed="$(DISPLAY="$host_display" timeout 0.2 \
        xclip -selection clipboard -out 2>/dev/null || true)"
    [[ "$observed" == "$expected" ]] && break
    sleep 0.05
done
[[ "$observed" == "$expected" ]] || {
    printf 'GameViewer-owned Unicode text did not reach X11 exactly\n' >&2
    exit 1
}
wait "$fixture_pid"
fixture_pid=""

DISPLAY="$wine_display" WINEPREFIX="$wine_prefix" WINEDEBUG=-all \
    WINEDLLOVERRIDES='mscoree,mshtml=' \
    /opt/wine-stable/bin/wine "$temporary_dir/OtherApp.exe" &
fixture_pid=$!
sleep 0.5
observed="$(DISPLAY="$host_display" timeout 0.5 \
    xclip -selection clipboard -out 2>/dev/null || true)"
[[ "$observed" == "$expected" ]] || {
    printf 'non-GameViewer clipboard owner crossed the one-way boundary\n' >&2
    exit 1
}
wait "$fixture_pid"
fixture_pid=""

printf 'controller-clipboard=GameViewer Unicode multiline exact\n'
printf 'owner-filter=non-GameViewer ignored\n'
printf 'direction=Wine-to-X11-only\n'
