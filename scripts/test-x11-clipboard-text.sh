#!/usr/bin/env bash

set -Eeuo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
temporary_dir="$(mktemp -d "${TMPDIR:-/tmp}/uurb-x11-clipboard.XXXXXX")"
wine_prefix="$temporary_dir/wine"
ready_file="$temporary_dir/x11-input.port"
broker_log="$temporary_dir/input-broker.log"
bridge_log="$temporary_dir/input-bridge.log"
editor_output="$temporary_dir/editor-output.txt"
token="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
xvfb_pid=""
openbox_pid=""
editor_pid=""
helper_pid=""
broker_pid=""
stale_primary_pid=""
clipboard_snooper_pid=""

cleanup() {
    local status=$?
    local pid

    trap - EXIT
    for pid in "$broker_pid" "$helper_pid" "$editor_pid" \
        "$clipboard_snooper_pid" \
        "$stale_primary_pid" \
        "$openbox_pid" "$xvfb_pid"; do
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
    elif [[ "$temporary_dir" == "${TMPDIR:-/tmp}/uurb-x11-clipboard."* ]]; then
        rm -rf -- "$temporary_dir"
    fi
    exit "$status"
}
trap cleanup EXIT

for command in flock timeout pgrep Xvfb openbox zenity xclip xdotool xdpyinfo python3 \
    x86_64-w64-mingw32-gcc /opt/wine-stable/bin/wine \
    /opt/wine-stable/bin/wineboot /opt/wine-stable/bin/winepath; do
    command -v "$command" >/dev/null 2>&1 || {
        printf 'missing clipboard-test command: %s\n' "$command" >&2
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
    -o "$temporary_dir/uu-clipboard-text-probe.exe" \
    "$repo_dir/tests/probes/uu_clipboard_text_probe.c"
x86_64-w64-mingw32-gcc -std=c11 -O2 -Wall -Wextra -Werror \
    -o "$temporary_dir/uu-long-text-probe.exe" \
    "$repo_dir/tests/probes/uu_long_text_probe.c" -luser32

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
DISPLAY="$display" openbox >"$temporary_dir/openbox.log" 2>&1 &
openbox_pid=$!
sleep 0.5

DISPLAY="$display" GDK_BACKEND=x11 NO_AT_BRIDGE=1 \
    zenity --text-info --editable \
    --title='UU clipboard text acceptance' --width=500 --height=300 \
    </dev/null >"$editor_output" 2>"$temporary_dir/editor.log" &
editor_pid=$!
editor_window=""
for _ in {1..50}; do
    editor_window="$(
        DISPLAY="$display" xdotool search \
            --name '^UU clipboard text acceptance$' 2>/dev/null | head -n 1 || true
    )"
    [[ -n "$editor_window" ]] && break
    sleep 0.1
done
if [[ -z "$editor_window" ]]; then
    printf 'isolated multiline editor did not appear\n' >&2
    exit 1
fi
DISPLAY="$display" xdotool windowmap --sync "$editor_window"
DISPLAY="$display" xdotool windowfocus --sync "$editor_window"
for _ in {1..30}; do
    focused_window="$(DISPLAY="$display" xdotool getwindowfocus 2>/dev/null || true)"
    [[ "$focused_window" == "$editor_window" ]] && break
    sleep 0.05
done
if [[ "${focused_window:-}" != "$editor_window" ]]; then
    printf 'isolated multiline editor did not receive focus\n' >&2
    exit 1
fi
sleep 0.1
DISPLAY="$display" xdotool type --clearmodifiers --delay 12 \
    'existing message:'

# Shift+Insert is selection-sensitive: VTE terminals read PRIMARY while other
# applications read CLIPBOARD. Seed a stale PRIMARY value so the acceptance
# test catches the exact regression where old desktop text was pasted instead
# of the semantic phone text.
printf '%s' 'stale-primary-must-never-be-pasted' | \
    DISPLAY="$display" xclip -selection primary -in -loops 0 \
        >"$temporary_dir/primary-fixture.log" 2>&1 &
stale_primary_pid=$!
sleep 0.2

DISPLAY="$display" UURB_X11_INPUT_TOKEN="$token" \
    "$temporary_dir/compat/uu-x11-input" --ready-file "$ready_file" \
    --min-hold-ms 0 >"$temporary_dir/x11-input.log" 2>&1 &
helper_pid=$!
for _ in {1..50}; do
    [[ -s "$ready_file" ]] && break
    sleep 0.1
done
[[ -s "$ready_file" ]]
port="$(tr -d '[:space:]' <"$ready_file")"

DISPLAY="$display" WINEPREFIX="$wine_prefix" WINEDEBUG=-all \
    WINEDLLOVERRIDES='mscoree,mshtml=' \
    /opt/wine-stable/bin/wineboot -u >/dev/null 2>&1
broker_log_windows="$(DISPLAY="$display" WINEPREFIX="$wine_prefix" \
    WINEDEBUG=-all /opt/wine-stable/bin/winepath -w "$broker_log")"
bridge_log_windows="$(DISPLAY="$display" WINEPREFIX="$wine_prefix" \
    WINEDEBUG=-all /opt/wine-stable/bin/winepath -w "$bridge_log")"
bridge_dll_windows="$(DISPLAY="$display" WINEPREFIX="$wine_prefix" \
    WINEDEBUG=-all /opt/wine-stable/bin/winepath -w \
    "$temporary_dir/compat/uu-input-bridge.dll")"
DISPLAY="$display" WINEPREFIX="$wine_prefix" WINEDEBUG=-all \
    WINEDLLOVERRIDES='mscoree,mshtml=' \
    UU_INPUT_BROKER_LOG="$broker_log_windows" \
    UURB_X11_INPUT_PORT="$port" UURB_X11_INPUT_TOKEN="$token" \
    UURB_PHONE_TEXT_MODE=auto UURB_TEXT_KEY_DELAY_MS=8 \
    UURB_PHYSICAL_KEY_DELAY_MS=0 \
    /opt/wine-stable/bin/wine "$temporary_dir/compat/uu-input-broker.exe" \
    >"$temporary_dir/broker-stdio.log" 2>&1 &
broker_pid=$!
sleep 0.5

# GNOME and other desktop clipboard managers may read each new CLIPBOARD value
# before the focused application handles Shift+Insert. Read each fresh owner
# pair once, then become quiet. This catches one-shot ownership without
# fabricating a never-idle desktop that request-completion logic cannot safely
# distinguish from the target application.
(
    previous_pair=''
    while true; do
        owner_pair="$(pgrep -P "$helper_pid" -x xclip 2>/dev/null | sort -n | tr '\n' ':' || true)"
        if [[ "$owner_pair" != "$previous_pair" ]] &&
            [[ "$(tr -cd ':' <<<"$owner_pair" | wc -c)" -eq 2 ]]; then
            DISPLAY="$display" timeout 0.2 \
                xclip -selection clipboard -out >/dev/null 2>&1 || true
            previous_pair="$owner_pair"
        fi
        sleep 0.01
    done
) &
clipboard_snooper_pid=$!

DISPLAY="$display" WINEPREFIX="$wine_prefix" WINEDEBUG=-all \
    WINEDLLOVERRIDES='mscoree,mshtml=' \
    /opt/wine-stable/bin/wine \
    "$temporary_dir/uu-clipboard-text-probe.exe"
sleep 0.3

expected_primary='修订完成'
primary_text="$(
    DISPLAY="$display" timeout 1 \
        xclip -selection primary -out 2>/dev/null || true
)"
if [[ "$primary_text" != "$expected_primary" ]]; then
    if [[ "$primary_text" == 'stale-primary-must-never-be-pasted' ]]; then
        printf 'semantic helper did not replace the stale PRIMARY selection\n' >&2
    else
        printf 'semantic PRIMARY owner exposed an unexpected %s-character value\n' \
            "${#primary_text}" >&2
    fi
    exit 1
fi

expected_symbols='中文，符号：‘’“”！？@&?🙂'
DISPLAY="$display" WINEPREFIX="$wine_prefix" WINEDEBUG=-all \
    WINEDLLOVERRIDES='mscoree,mshtml=' \
    /opt/wine-stable/bin/wine \
    "$temporary_dir/uu-clipboard-text-probe.exe" symbols
sleep 0.3
symbol_primary="$(
    DISPLAY="$display" timeout 1 \
        xclip -selection primary -out 2>/dev/null || true
)"
if [[ "$symbol_primary" != "$expected_symbols" ]]; then
    printf 'semantic symbol text was not exposed exactly through PRIMARY\n' >&2
    exit 1
fi

DISPLAY="$display" WINEPREFIX="$wine_prefix" WINEDEBUG=-all \
    WINEDLLOVERRIDES='mscoree,mshtml=' \
    UU_INPUT_BRIDGE_LOG="$bridge_log_windows" \
    /opt/wine-stable/bin/wine "$temporary_dir/uu-long-text-probe.exe" \
    "$bridge_dll_windows" unicode
sleep 0.5

DISPLAY="$display" xdotool key --clearmodifiers alt+o
for _ in {1..30}; do
    kill -0 "$editor_pid" 2>/dev/null || break
    sleep 0.1
done
if kill -0 "$editor_pid" 2>/dev/null; then
    printf 'multiline editor did not accept the clipboard paste\n' >&2
    exit 1
fi
wait "$editor_pid" || true

python3 - "$editor_output" <<'PY'
from pathlib import Path
import sys

observed = Path(sys.argv[1]).read_text(encoding="utf-8").rstrip("\n")
expected = "existing message:修订完成中文，符号：‘’“”！？@&?🙂" + "你" * 1000
if observed != expected:
    raise SystemExit("prior text or multiline clipboard text changed")
print("clipboard-text=unicode+multiline revision exact")
print("prior-message=preserved while owned text was revised")
print("mobile-symbols=Chinese+smart-punctuation+emoji exact")
PY

if ! rg -q \
    'category=text .*route=x11-clipboard-text .*result=[1-9][0-9]* error=0' \
    "$broker_log"; then
    printf 'broker did not confirm the adaptive clipboard-text route\n' >&2
    exit 1
fi
printf 'broker-route=x11-clipboard-text error=0\n'
if ! rg -q \
    'category=text .*route=x11-clipboard-text .*clamped-edits=1 .*error=0' \
    "$broker_log"; then
    printf 'broker did not clamp composition editing to bridge-owned text\n' >&2
    exit 1
fi
if ! rg -q \
    'category=text .*count=2000 .*route=x11-clipboard-text .*result=2000 error=0' \
    "$broker_log"; then
    printf 'broker did not accept the complete bounded long Unicode batch\n' >&2
    exit 1
fi
if ! rg -q \
    'category=text .*count=2000 .*route=broker .*result=2000 error=0' \
    "$bridge_log"; then
    printf 'bridge did not report the complete long Unicode text call\n' >&2
    exit 1
fi
printf 'long-unicode-text=2000/2000 one-paste exact\n'
printf 'isolated Unicode multiline clipboard acceptance passed\n'
