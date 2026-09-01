#!/usr/bin/env bash

set -Eeuo pipefail

temporary_dir="$(mktemp -d "${TMPDIR:-/tmp}/uurb-vnc-clipboard.XXXXXX")"
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
    for attempt in {1..20}; do
        local any_alive=0
        for pid in "${pids[@]}"; do
            if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
                any_alive=1
                break
            fi
        done
        (( any_alive == 0 )) && break
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
    elif [[ "$temporary_dir" == "${TMPDIR:-/tmp}/uurb-vnc-clipboard."* ]]; then
        rm -rf -- "$temporary_dir"
    fi
    exit "$status"
}
trap cleanup EXIT INT TERM

for command in flock Xvfb openbox ss timeout vncviewer x11vnc xclip xdotool \
    xdpyinfo zenity; do
    command -v "$command" >/dev/null 2>&1 || {
        printf 'missing VNC clipboard-test command: %s\n' "$command" >&2
        exit 1
    }
done

exec 9>"${TMPDIR:-/tmp}/uurb-isolated-x-display.lock"
if ! flock -w 5 -x 9; then
    printf 'timed out waiting for the isolated X-display allocation lock\n' >&2
    exit 1
fi
displays=()
for number in {130..159}; do
    if [[ ! -S "/tmp/.X11-unix/X$number" ]]; then
        displays+=(":$number")
        ((${#displays[@]} == 2)) && break
    fi
done
if ((${#displays[@]} != 2)); then
    printf 'two free isolated X displays were not available\n' >&2
    exit 1
fi
target_display="${displays[0]}"
private_display="${displays[1]}"

vnc_port=""
# Keep the RFB display number below 100. RealVNC Viewer accepts HOST:DISPLAY,
# and some builds do not reliably interpret three-digit display numbers.
for candidate in {5970..5999}; do
    if ! ss -H -ltn "sport = :$candidate" | grep -q .; then
        vnc_port="$candidate"
        break
    fi
done
if [[ -z "$vnc_port" ]]; then
    printf 'no free isolated VNC port was available\n' >&2
    exit 1
fi

for display in "$target_display" "$private_display"; do
    Xvfb "$display" -screen 0 900x600x24 -ac -nolisten tcp \
        >"$temporary_dir/xvfb-${display#:}.log" 2>&1 9>&- &
    pids+=("$!")
done
for display in "$target_display" "$private_display"; do
    for _ in {1..50}; do
        DISPLAY="$display" timeout 0.5 xdpyinfo >/dev/null 2>&1 9>&- && break
        sleep 0.1
    done
    DISPLAY="$display" timeout 1 xdpyinfo >/dev/null 9>&-
done
flock -u 9
exec 9>&-

for display in "$target_display" "$private_display"; do
    DISPLAY="$display" openbox \
        >"$temporary_dir/openbox-${display#:}.log" 2>&1 &
    pids+=("$!")
done

editor_output="$temporary_dir/editor-output.txt"
DISPLAY="$target_display" zenity --text-info --editable \
    --title='UU VNC clipboard acceptance' --width=500 --height=300 \
    >"$editor_output" 2>"$temporary_dir/editor.log" &
editor_pid=$!
pids+=("$editor_pid")

x11vnc -norc -display "$target_display" -localhost -no6 -nopw -forever \
    -shared -repeat -nobell -modtweak -xkb -add_keysyms \
    -seldir recv -debug_sel \
    -rfbport "$vnc_port" >"$temporary_dir/x11vnc.log" 2>&1 &
pids+=("$!")
for _ in {1..50}; do
    ss -H -ltn "sport = :$vnc_port" | grep -q . && break
    sleep 0.1
done
ss -H -ltn "sport = :$vnc_port" | grep -q .

vnc_display=$((vnc_port - 5900))
DISPLAY="$private_display" DBUS_SESSION_BUS_ADDRESS=unix:path=/dev/null \
    vncviewer '-Log=*:stderr:100' -AllowMainClose=1 \
    -LogToAddressBook=0 -FullScreen=0 \
    -EnableToolbar=0 -AcceptBell=0 -AudioVolume=0 -WarnUnencrypted=0 \
    -VerifyId=0 -Shared=1 -Scaling=Fit -DynamicResolution=0 \
    -GrabKeyboard=1 -SendKeyEvents=1 -SendPointerEvents=1 \
    -ClientCutText=1 -ServerCutText=0 -SendPrimary=0 \
    -SendInitialClipboard=0 -ServerClipboardGraceTime=5000 \
    -MenuKey= -UpdateScreenshot=0 -ShowSplash=0 -EnableAnalytics=0 \
    -ShareFiles=0 -EnableRemotePrinting=0 -ChangeServerDefaultPrinter=0 \
    "127.0.0.1:$vnc_display" >"$temporary_dir/vncviewer.log" 2>&1 &
viewer_pid=$!
pids+=("$viewer_pid")
for _ in {1..50}; do
    grep -q 'Got connection from client' "$temporary_dir/x11vnc.log" && break
    sleep 0.1
done
grep -q 'Got connection from client' "$temporary_dir/x11vnc.log"

viewer_window=""
for _ in {1..50}; do
    viewer_window="$(
        DISPLAY="$private_display" xdotool search --onlyvisible \
            --pid "$viewer_pid" 2>/dev/null | tail -n 1 || true
    )"
    [[ -n "$viewer_window" ]] && break
    sleep 0.1
done
[[ -n "$viewer_window" ]]
DISPLAY="$private_display" xdotool windowactivate --sync "$viewer_window"
sleep 0.3

client_text='client-to-target clipboard'
DISPLAY="$private_display" zenity --entry \
    --title='UU private clipboard source' --entry-text="$client_text" \
    >"$temporary_dir/private-entry-output.txt" \
    2>"$temporary_dir/private-entry.log" &
private_entry_pid=$!
pids+=("$private_entry_pid")
private_entry_window=""
for _ in {1..50}; do
    private_entry_window="$(
        DISPLAY="$private_display" xdotool search \
            --name '^UU private clipboard source$' 2>/dev/null | \
            head -n 1 || true
    )"
    [[ -n "$private_entry_window" ]] && break
    sleep 0.1
done
[[ -n "$private_entry_window" ]]
DISPLAY="$private_display" xdotool windowactivate --sync "$private_entry_window"
DISPLAY="$private_display" xdotool key --clearmodifiers ctrl+a ctrl+c
sleep 0.2
private_local="$(
    DISPLAY="$private_display" timeout 1 \
        xclip -selection clipboard -out 2>/dev/null || true
)"
if [[ "$private_local" != "$client_text" ]]; then
    printf 'test could not establish the private-display clipboard\n' >&2
    exit 1
fi
viewer_window=""
for _ in {1..30}; do
    viewer_window="$(
        DISPLAY="$private_display" xdotool search --onlyvisible \
            --pid "$viewer_pid" 2>/dev/null | tail -n 1 || true
    )"
    if [[ -n "$viewer_window" ]] && \
        DISPLAY="$private_display" xdotool getwindowname "$viewer_window" \
            >/dev/null 2>&1; then
        break
    fi
    viewer_window=""
    sleep 0.1
done
[[ -n "$viewer_window" ]]
DISPLAY="$private_display" xdotool windowactivate --sync "$viewer_window"
sleep 0.3
for _ in {1..40}; do
    grep -Fq "xcut_receive: '$client_text'" "$temporary_dir/x11vnc.log" && \
        break
    sleep 0.1
done
if ! grep -Fq "xcut_receive: '$client_text'" \
    "$temporary_dir/x11vnc.log"; then
    printf 'VNC server did not receive the client clipboard packet\n' >&2
    exit 1
fi

semantic_text='semantic 你好 text'
printf '%s' "$semantic_text" | DISPLAY="$target_display" \
    xclip -selection clipboard -in -loops 0 >/dev/null 2>&1 &
pids+=("$!")
sleep 0.3
private_observed="$(
    DISPLAY="$private_display" timeout 1 \
        xclip -selection clipboard -out 2>/dev/null || true
)"
if [[ "$private_observed" != "$client_text" ]]; then
    printf 'target clipboard unexpectedly fed back into the VNC client\n' >&2
    exit 1
fi

editor_window=""
for _ in {1..50}; do
    editor_window="$(
        DISPLAY="$target_display" xdotool search \
            --name '^UU VNC clipboard acceptance$' 2>/dev/null | \
            head -n 1 || true
    )"
    [[ -n "$editor_window" ]] && break
    sleep 0.1
done
[[ -n "$editor_window" ]]
DISPLAY="$target_display" xdotool windowactivate --sync "$editor_window"
DISPLAY="$target_display" xdotool key --clearmodifiers shift+Insert
sleep 0.2
DISPLAY="$target_display" xdotool key --clearmodifiers alt+o
for _ in {1..30}; do
    kill -0 "$editor_pid" 2>/dev/null || break
    sleep 0.1
done
wait "$editor_pid" || true

observed="$(sed -e '${/^$/d;}' "$editor_output")"
if [[ "$observed" != "$semantic_text" ]]; then
    printf 'semantic target clipboard paste was replaced or corrupted\n' >&2
    exit 1
fi

printf 'vnc-clipboard=client-cut-text received server-feedback=disabled\n'
printf 'semantic-target-paste=unicode exact clipboard-loop=absent\n'
printf 'isolated VNC clipboard acceptance passed\n'
