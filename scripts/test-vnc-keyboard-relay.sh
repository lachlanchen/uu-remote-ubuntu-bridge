#!/usr/bin/env bash

set -Eeuo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
temporary_dir="$(mktemp -d "${TMPDIR:-/tmp}/uurb-vnc-keyboard.XXXXXX")"
pids=()

cleanup() {
    local status=$?
    local pid

    for pid in "${pids[@]}"; do
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    wait 2>/dev/null || true
    if [[ "${UURB_KEEP_TEST_TMP:-0}" == 1 || "$status" -ne 0 ]]; then
        printf 'isolated test artifacts: %s\n' "$temporary_dir" >&2
    elif [[ "$temporary_dir" == "${TMPDIR:-/tmp}/uurb-vnc-keyboard."* ]]; then
        rm -rf -- "$temporary_dir"
    fi
    trap - EXIT
    exit "$status"
}
trap cleanup EXIT

for command in flock Xvfb python3 setxkbmap ss stdbuf x11vnc xdotool xdpyinfo \
    xev; do
    command -v "$command" >/dev/null 2>&1 || {
        printf 'missing VNC keyboard-test command: %s\n' "$command" >&2
        exit 1
    }
done

exec 9>"${TMPDIR:-/tmp}/uurb-isolated-x-display.lock"
flock -x 9
display=""
for number in {111..127}; do
    if [[ ! -S "/tmp/.X11-unix/X$number" ]]; then
        display=":$number"
        break
    fi
done
if [[ -z "$display" ]]; then
    printf 'a free isolated X display was not available\n' >&2
    exit 1
fi

vnc_port=""
for candidate in {5960..5999}; do
    if ! ss -H -ltn "sport = :$candidate" | grep -q .; then
        vnc_port="$candidate"
        break
    fi
done
if [[ -z "$vnc_port" ]]; then
    printf 'no free isolated VNC port was available\n' >&2
    exit 1
fi

Xvfb "$display" -screen 0 900x600x24 -ac -nolisten tcp \
    >"$temporary_dir/xvfb.log" 2>&1 &
pids+=("$!")
for _ in {1..50}; do
    if DISPLAY="$display" xdpyinfo >/dev/null 2>&1; then
        break
    fi
    sleep 0.1
done
DISPLAY="$display" xdpyinfo >/dev/null
flock -u 9

target_layout="${UURB_TEST_TARGET_LAYOUT:-jp}"
DISPLAY="$display" setxkbmap -model pc105 -layout "$target_layout"
DISPLAY="$display" stdbuf -oL -eL xev -geometry 500x300 \
    >"$temporary_dir/xev.log" 2>&1 &
pids+=("$!")

x11vnc_options=(
    -norc
    -display "$display"
    -localhost
    -no6
    -nopw
    -forever
    -shared
    -repeat
    -nobell
    -modtweak
    -add_keysyms
    -rfbport "$vnc_port"
)
case "${UURB_TEST_X11VNC_XKB:-auto}" in
    auto) ;;
    xkb) x11vnc_options+=(-xkb) ;;
    noxkb) x11vnc_options+=(-noxkb) ;;
    *)
        printf 'UURB_TEST_X11VNC_XKB must be auto, xkb, or noxkb\n' >&2
        exit 2
        ;;
esac

if [[ -n "${UURB_TEST_MODTWEAK_LOWEST:-}" ]]; then
    export MODTWEAK_LOWEST="$UURB_TEST_MODTWEAK_LOWEST"
fi
x11vnc "${x11vnc_options[@]}" >"$temporary_dir/x11vnc.log" 2>&1 &
x11vnc_pid=$!
pids+=("$x11vnc_pid")
for _ in {1..50}; do
    if ss -H -ltn "sport = :$vnc_port" | grep -q .; then
        break
    fi
    sleep 0.1
done

target_window=""
for _ in {1..50}; do
    target_window="$(
        DISPLAY="$display" xdotool search \
            --name 'Event Tester' 2>/dev/null | head -n 1 || true
    )"
    if [[ -n "$target_window" ]]; then
        break
    fi
    sleep 0.1
done
if [[ -z "$target_window" ]]; then
    printf 'the isolated event window did not appear\n' >&2
    exit 1
fi
DISPLAY="$display" xdotool windowfocus "$target_window"

printf -v symbols '%s%s%s' '()$&@"?!' "'" '{}#%*+_\|~<>'
symbols+='你好'
expected=(
    parenleft parenright dollar ampersand at quotedbl
    question exclam apostrophe braceleft braceright numbersign percent
    asterisk plus underscore backslash bar asciitilde less greater
    U4F60 U597D
)
python3 "$repo_dir/tests/probes/rfb_key_probe.py" "$vnc_port" "$symbols"
sleep 0.5

mapfile -t observed < <(
    sed -n '/^KeyPress event/,/^$/ {
        s/.*keysym 0x[0-9a-fA-F]*, \([^)]*\)).*/\1/p
    }' "$temporary_dir/xev.log" |
        grep -v -E '^(Shift|Control|Alt|Meta|Super|ISO_Level)' || true
)
if [[ "${observed[*]}" != "${expected[*]}" ]]; then
    printf 'VNC symbol mismatch\n' >&2
    printf 'expected: %s\n' "${expected[*]}" >&2
    printf 'observed: %s\n' "${observed[*]}" >&2
    exit 1
fi

printf 'vnc-symbols=%s/%s order=exact target-layout=%s xkb=%s lowest=%s\n' \
    "${#observed[@]}" "${#expected[@]}" "$target_layout" \
    "${UURB_TEST_X11VNC_XKB:-auto}" \
    "${UURB_TEST_MODTWEAK_LOWEST:-unset}"
printf 'isolated VNC keyboard acceptance passed\n'
