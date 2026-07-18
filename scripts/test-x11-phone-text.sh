#!/usr/bin/env bash

set -Eeuo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
temporary_dir="$(mktemp -d "${TMPDIR:-/tmp}/uurb-x11-text.XXXXXX")"
wine_prefix="$temporary_dir/wine"
ready_file="$temporary_dir/x11-input.port"
broker_log="$temporary_dir/input-broker.log"
xev_log="$temporary_dir/xev.log"
token="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
xvfb_pid=""
xev_pid=""
helper_pid=""
broker_pid=""

cleanup() {
    local pid

    for pid in "$broker_pid" "$helper_pid" "$xev_pid" "$xvfb_pid"; do
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    if [[ -d "$wine_prefix" ]]; then
        WINEPREFIX="$wine_prefix" /opt/wine-stable/bin/wineserver -k \
            >/dev/null 2>&1 || true
    fi
    wait 2>/dev/null || true
    if [[ "$temporary_dir" == "${TMPDIR:-/tmp}/uurb-x11-text."* ]]; then
        rm -rf -- "$temporary_dir"
    fi
}
trap cleanup EXIT

for command in Xvfb xev xdotool xdpyinfo python3 stdbuf \
    x86_64-w64-mingw32-gcc /opt/wine-stable/bin/wine \
    /opt/wine-stable/bin/wineboot /opt/wine-stable/bin/winepath; do
    command -v "$command" >/dev/null 2>&1 || {
        printf 'missing acceptance-test command: %s\n' "$command" >&2
        exit 1
    }
done

display=""
for number in {88..99}; do
    if [[ ! -S "/tmp/.X11-unix/X$number" ]]; then
        display=":$number"
        break
    fi
done
if [[ -z "$display" ]]; then
    printf 'no free isolated X display in :88..:99\n' >&2
    exit 1
fi

"$repo_dir/scripts/build-compat.sh" "$temporary_dir/compat" >/dev/null
x86_64-w64-mingw32-gcc -std=c11 -O2 -Wall -Wextra -Werror \
    -o "$temporary_dir/uu-text-probe.exe" \
    "$repo_dir/tests/probes/uu_text_probe.c"

Xvfb "$display" -screen 0 800x600x24 -ac -nolisten tcp \
    >"$temporary_dir/xvfb.log" 2>&1 &
xvfb_pid=$!
for _ in {1..50}; do
    if DISPLAY="$display" xdpyinfo >/dev/null 2>&1; then
        break
    fi
    sleep 0.1
done
DISPLAY="$display" xdpyinfo >/dev/null

DISPLAY="$display" stdbuf -oL -eL xev -geometry 400x240 \
    >"$xev_log" 2>&1 &
xev_pid=$!
xev_window=""
for _ in {1..50}; do
    xev_window="$(DISPLAY="$display" xdotool search --name 'Event Tester' \
        2>/dev/null | head -n 1 || true)"
    [[ -n "$xev_window" ]] && break
    sleep 0.1
done
if [[ -z "$xev_window" ]]; then
    printf 'isolated X11 event window did not appear\n' >&2
    exit 1
fi
DISPLAY="$display" xdotool windowfocus "$xev_window"

DISPLAY="$display" UURB_X11_INPUT_TOKEN="$token" \
    "$temporary_dir/compat/uu-x11-input" --ready-file "$ready_file" \
    --min-hold-ms 0 >"$temporary_dir/x11-input.log" 2>&1 &
helper_pid=$!
for _ in {1..50}; do
    [[ -s "$ready_file" ]] && break
    sleep 0.1
done
if [[ ! -s "$ready_file" ]]; then
    printf 'isolated X11 helper did not become ready\n' >&2
    exit 1
fi
port="$(tr -d '[:space:]' < "$ready_file")"

DISPLAY="$display" WINEPREFIX="$wine_prefix" WINEDEBUG=-all \
    WINEDLLOVERRIDES='mscoree,mshtml=' \
    /opt/wine-stable/bin/wineboot -u >/dev/null 2>&1
broker_log_windows="$(DISPLAY="$display" WINEPREFIX="$wine_prefix" \
    WINEDEBUG=-all /opt/wine-stable/bin/winepath -w "$broker_log")"
DISPLAY="$display" WINEPREFIX="$wine_prefix" WINEDEBUG=-all \
    WINEDLLOVERRIDES='mscoree,mshtml=' \
    UU_INPUT_BROKER_LOG="$broker_log_windows" \
    UURB_X11_INPUT_PORT="$port" UURB_X11_INPUT_TOKEN="$token" \
    UURB_TEXT_KEY_DELAY_MS=8 UURB_PHYSICAL_KEY_DELAY_MS=0 \
    /opt/wine-stable/bin/wine "$temporary_dir/compat/uu-input-broker.exe" \
    >"$temporary_dir/broker-stdio.log" 2>&1 &
broker_pid=$!
sleep 0.5

DISPLAY="$display" WINEPREFIX="$wine_prefix" WINEDEBUG=-all \
    WINEDLLOVERRIDES='mscoree,mshtml=' \
    /opt/wine-stable/bin/wine "$temporary_dir/uu-text-probe.exe"
sleep 0.2

python3 - "$xev_log" <<'PY'
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(errors="replace")
matches = re.findall(
    r"(KeyPress|KeyRelease) event,.*?keysym 0x[0-9a-f]+, ([a-z])\)",
    text,
    flags=re.DOTALL,
)
expected = []
for character in "abcdefghijklmnopqrstuvwxyz":
    expected.extend((("KeyPress", character), ("KeyRelease", character)))
if matches != expected:
    raise SystemExit(
        f"X11 text mismatch: observed {len(matches)} of {len(expected)} "
        "expected transitions"
    )
print("x11-transitions=52/52 order=exact")
PY

if ! rg -q 'category=text .*route=x11-text .*result=52 error=0' \
    "$broker_log"; then
    printf 'broker did not confirm the direct X11 phone-text route\n' >&2
    exit 1
fi
printf 'broker-route=x11-text result=52 error=0\n'
printf 'isolated phone-text acceptance passed\n'
