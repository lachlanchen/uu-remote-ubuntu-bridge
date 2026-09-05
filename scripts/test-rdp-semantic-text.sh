#!/usr/bin/env bash

set -Eeuo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
temporary_dir="$(mktemp -d "${TMPDIR:-/tmp}/uurb-rdp-semantic.XXXXXX")"
wine_prefix="$temporary_dir/wine"
ready_file="$temporary_dir/x11-input.port"
broker_log="$temporary_dir/input-broker.log"
relay_marker="$temporary_dir/relay-paste.marker"
observed_text="$temporary_dir/observed.txt"
token="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
pids=()

cleanup() {
    local status=$?
    local pid
    local attempt

    trap - EXIT INT TERM
    for pid in "${pids[@]}"; do
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    if [[ -d "$wine_prefix" ]]; then
        WINEPREFIX="$wine_prefix" /opt/wine-stable/bin/wineserver -k \
            >/dev/null 2>&1 || true
    fi
    for attempt in {1..20}; do
        local any_alive=0
        for pid in "${pids[@]}"; do
            if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
                any_alive=1
                break
            fi
        done
        ((any_alive == 0)) && break
        sleep 0.05
    done
    for pid in "${pids[@]}"; do
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill -KILL "$pid" 2>/dev/null || true
        fi
        wait "$pid" 2>/dev/null || true
    done
    if [[ "${UURB_KEEP_TEST_TMP:-0}" == 1 || "$status" -ne 0 ]]; then
        printf 'isolated test artifacts: %s\n' "$temporary_dir" >&2
    elif [[ "$temporary_dir" == "${TMPDIR:-/tmp}/uurb-rdp-semantic."* ]]; then
        rm -rf -- "$temporary_dir"
    fi
    exit "$status"
}
trap cleanup EXIT INT TERM

for command in flock timeout Xvfb openbox xclip xdotool xdpyinfo rg \
    x86_64-w64-mingw32-gcc /opt/wine-stable/bin/wine \
    /opt/wine-stable/bin/wineboot /opt/wine-stable/bin/winepath; do
    command -v "$command" >/dev/null 2>&1 || {
        printf 'missing RDP semantic-test command: %s\n' "$command" >&2
        exit 1
    }
done

exec 9>"${TMPDIR:-/tmp}/uurb-isolated-x-display.lock"
if ! flock -w 5 -x 9; then
    printf 'timed out waiting for the isolated X-display allocation lock\n' >&2
    exit 1
fi
displays=()
for number in {160..189}; do
    if [[ ! -S "/tmp/.X11-unix/X$number" ]]; then
        displays+=(":$number")
        ((${#displays[@]} == 2)) && break
    fi
done
if ((${#displays[@]} != 2)); then
    printf 'two free isolated X displays were not available\n' >&2
    exit 1
fi
clipboard_display="${displays[0]}"
injection_display="${displays[1]}"

"$repo_dir/scripts/build-compat.sh" "$temporary_dir/compat" >/dev/null
x86_64-w64-mingw32-gcc -std=c11 -O2 -Wall -Wextra -Werror \
    -Wl,--no-insert-timestamp -municode -mwindows \
    -o "$temporary_dir/uu-rdp-relay-probe.exe" \
    "$repo_dir/tests/probes/uu_rdp_relay_probe.c" -luser32
x86_64-w64-mingw32-gcc -std=c11 -O2 -Wall -Wextra -Werror \
    -Wl,--no-insert-timestamp \
    -o "$temporary_dir/uu-rdp-semantic-probe.exe" \
    "$repo_dir/tests/probes/uu_rdp_semantic_probe.c"
x86_64-w64-mingw32-gcc -std=c11 -O2 -Wall -Wextra -Werror \
    -Wl,--no-insert-timestamp \
    -o "$temporary_dir/uu-text-probe.exe" \
    "$repo_dir/tests/probes/uu_text_probe.c"

for display in "$clipboard_display" "$injection_display"; do
    Xvfb "$display" -screen 0 800x600x24 -ac -nolisten tcp \
        >"$temporary_dir/xvfb-${display#:}.log" 2>&1 9>&- &
    pids+=("$!")
done
for display in "$clipboard_display" "$injection_display"; do
    for _ in {1..50}; do
        DISPLAY="$display" timeout 0.5 xdpyinfo >/dev/null 2>&1 9>&- && break
        sleep 0.1
    done
    DISPLAY="$display" timeout 1 xdpyinfo >/dev/null 9>&-
done
flock -u 9
exec 9>&-

for display in "$clipboard_display" "$injection_display"; do
    DISPLAY="$display" openbox \
        >"$temporary_dir/openbox-${display#:}.log" 2>&1 &
    pids+=("$!")
done

DISPLAY="$injection_display" WINEPREFIX="$wine_prefix" WINEDEBUG=-all \
    WINEDLLOVERRIDES='mscoree,mshtml=' \
    /opt/wine-stable/bin/wineboot -u >/dev/null 2>&1
marker_windows="$(DISPLAY="$injection_display" WINEPREFIX="$wine_prefix" \
    WINEDEBUG=-all /opt/wine-stable/bin/winepath -w "$relay_marker")"
broker_log_windows="$(DISPLAY="$injection_display" WINEPREFIX="$wine_prefix" \
    WINEDEBUG=-all /opt/wine-stable/bin/winepath -w "$broker_log")"

DISPLAY="$injection_display" WINEPREFIX="$wine_prefix" WINEDEBUG=-all \
    WINEDLLOVERRIDES='mscoree,mshtml=' UURB_RELAY_MARKER="$marker_windows" \
    /opt/wine-stable/bin/wine "$temporary_dir/uu-rdp-relay-probe.exe" \
    >"$temporary_dir/relay.log" 2>&1 &
relay_pid=$!
pids+=("$relay_pid")
relay_window=""
for _ in {1..50}; do
    relay_window="$(DISPLAY="$injection_display" xdotool search --onlyvisible \
        --name '^Ubuntu-Desktop-Relay$' 2>/dev/null | head -n 1 || true)"
    [[ -n "$relay_window" ]] && break
    sleep 0.1
done
if [[ -z "$relay_window" ]]; then
    printf 'isolated RDP relay window did not appear\n' >&2
    exit 1
fi

DISPLAY="$clipboard_display" XAUTHORITY=/dev/null \
    UURB_X11_INPUT_TOKEN="$token" \
    "$temporary_dir/compat/uu-x11-input" --ready-file "$ready_file" \
    --min-hold-ms 0 --inject-display "$injection_display" \
    --inject-xauthority /dev/null >"$temporary_dir/x11-input.log" 2>&1 &
helper_pid=$!
pids+=("$helper_pid")
for _ in {1..50}; do
    [[ -s "$ready_file" ]] && break
    sleep 0.1
done
if [[ ! -s "$ready_file" ]]; then
    printf 'dual-display semantic helper did not become ready\n' >&2
    exit 1
fi
port="$(tr -d '[:space:]' <"$ready_file")"

DISPLAY="$injection_display" WINEPREFIX="$wine_prefix" WINEDEBUG=-all \
    WINEDLLOVERRIDES='mscoree,mshtml=' \
    UU_INPUT_BROKER_LOG="$broker_log_windows" \
    UURB_X11_INPUT_PORT="$port" UURB_X11_INPUT_TOKEN="$token" \
    UURB_X11_INPUT_SEMANTIC_ONLY=1 UURB_PHONE_TEXT_MODE=auto \
    UURB_TEXT_KEY_DELAY_MS=8 UURB_PHYSICAL_KEY_DELAY_MS=0 \
    /opt/wine-stable/bin/wine "$temporary_dir/compat/uu-input-broker.exe" \
    >"$temporary_dir/broker-stdio.log" 2>&1 &
broker_pid=$!
pids+=("$broker_pid")
sleep 0.5

(
    for _ in {1..300}; do
        [[ -f "$relay_marker" ]] && break
        sleep 0.01
    done
    [[ -f "$relay_marker" ]]
    DISPLAY="$clipboard_display" timeout 2 \
        xclip -selection clipboard -out >"$observed_text"
) &
clipboard_reader_pid=$!
pids+=("$clipboard_reader_pid")

DISPLAY="$injection_display" WINEPREFIX="$wine_prefix" WINEDEBUG=-all \
    WINEDLLOVERRIDES='mscoree,mshtml=' timeout 10 \
    /opt/wine-stable/bin/wine "$temporary_dir/uu-rdp-semantic-probe.exe"
wait "$clipboard_reader_pid"

expected_text='UU broker 中文 123'
observed="$(<"$observed_text")"
if [[ "$observed" != "$expected_text" ]]; then
    printf 'dual-display semantic text did not arrive exactly\n' >&2
    exit 1
fi
if ! rg -q \
    'category=text .*count=32 .*route=rdp-clipboard-text .*result=32 error=0' \
    "$broker_log"; then
    printf 'broker did not confirm the RDP semantic clipboard route\n' >&2
    exit 1
fi
if ! rg -q 'semantic-clipboard=relay' "$broker_log"; then
    printf 'broker did not report semantic-only relay mode\n' >&2
    exit 1
fi

DISPLAY="$injection_display" WINEPREFIX="$wine_prefix" WINEDEBUG=-all \
    WINEDLLOVERRIDES='mscoree,mshtml=' timeout 10 \
    /opt/wine-stable/bin/wine "$temporary_dir/uu-text-probe.exe"
if ! rg -q 'category=text .*count=52 .*route=rdp .*result=52 error=0' \
    "$broker_log"; then
    printf 'routine phone text did not remain on the RDP route\n' >&2
    exit 1
fi

printf 'semantic-text=%s exact\n' "$expected_text"
printf 'broker-route=rdp-clipboard-text result=32 error=0\n'
printf 'routine-text-route=rdp result=52 error=0\n'
printf 'isolated dual-display RDP semantic acceptance passed\n'
