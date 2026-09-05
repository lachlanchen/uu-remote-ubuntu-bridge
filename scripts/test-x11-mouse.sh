#!/usr/bin/env bash

set -Eeuo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
temporary_dir="$(mktemp -d "${TMPDIR:-/tmp}/uurb-x11-mouse.XXXXXX")"
wine_prefix="$temporary_dir/wine"
ready_file="$temporary_dir/x11-input.port"
broker_log="$temporary_dir/input-broker.log"
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
    if [[ "$temporary_dir" == "${TMPDIR:-/tmp}/uurb-x11-mouse."* ]]; then
        rm -rf -- "$temporary_dir"
    fi
}
trap cleanup EXIT

for command in flock timeout Xvfb xev xdotool xdpyinfo python3 stdbuf \
    x86_64-w64-mingw32-gcc /opt/wine-stable/bin/wine \
    /opt/wine-stable/bin/wineboot /opt/wine-stable/bin/winepath; do
    command -v "$command" >/dev/null 2>&1 || {
        printf 'missing acceptance-test command: %s\n' "$command" >&2
        exit 1
    }
done

exec 9>"${TMPDIR:-/tmp}/uurb-isolated-x-display.lock"
flock -x 9
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
    -o "$temporary_dir/uu-mouse-probe.exe" \
    "$repo_dir/tests/probes/uu_mouse_probe.c"

Xvfb "$display" -screen 0 800x600x24 -ac -nolisten tcp \
    >"$temporary_dir/xvfb.log" 2>&1 &
xvfb_pid=$!
for _ in {1..50}; do
    if DISPLAY="$display" timeout 0.5 xdpyinfo >/dev/null 2>&1 9>&-; then
        break
    fi
    sleep 0.1
done
DISPLAY="$display" timeout 5 xdpyinfo >/dev/null 9>&-
flock -u 9

DISPLAY="$display" stdbuf -oL -eL xev -root \
    >"$temporary_dir/xev.log" 2>&1 &
xev_pid=$!

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
    /opt/wine-stable/bin/wine "$temporary_dir/uu-mouse-probe.exe"
sleep 0.2

python3 - "$display" "$temporary_dir/xev.log" <<'PY'
import re
import subprocess
import sys
from pathlib import Path

display, xev_path = sys.argv[1:]
location = subprocess.check_output(
    ["xdotool", "getmouselocation", "--shell"],
    env={"DISPLAY": display},
    text=True,
)
values = dict(line.split("=", 1) for line in location.splitlines())
x = int(values["X"])
y = int(values["Y"])
if abs(x - 405) > 1 or abs(y - 303) > 1:
    raise SystemExit(f"absolute pointer mismatch: observed {x},{y}")

text = Path(xev_path).read_text(errors="replace")
transitions = re.findall(
    r"(ButtonPress|ButtonRelease) event,.*?button ([0-9]+)",
    text,
    flags=re.DOTALL,
)
expected = [
    ("ButtonPress", "1"),
    ("ButtonRelease", "1"),
    ("ButtonPress", "4"),
    ("ButtonRelease", "4"),
    ("ButtonPress", "6"),
    ("ButtonRelease", "6"),
]
if transitions != expected:
    raise SystemExit(f"mouse button mismatch: {transitions!r}")
print(f"x11-pointer={x},{y} buttons=left,wheel-up,wheel-left")
PY

if ! rg -q 'category=mouse .*route=x11-mouse .*result=6 error=0' \
    "$broker_log"; then
    printf 'broker did not confirm the direct X11 mouse route\n' >&2
    exit 1
fi
printf 'broker-route=x11-mouse result=6 error=0\n'
printf 'isolated mouse acceptance passed\n'
