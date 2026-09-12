#!/usr/bin/env bash

set -Eeuo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
temporary_dir="$(mktemp -d "${TMPDIR:-/tmp}/uurb-controller-clipboard.XXXXXX")"
wine_prefix="$temporary_dir/wine"
ready_file="$temporary_dir/x11-clipboard.port"
token="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
wine_bin="${UURB_WINE_BIN:-/opt/wine-stable/bin/wine}"
wineboot_bin="${UURB_WINEBOOT_BIN:-/opt/wine-stable/bin/wineboot}"
wineserver_bin="${UURB_WINESERVER_BIN:-/opt/wine-stable/bin/wineserver}"
host_xvfb_pid=""
wine_xvfb_pid=""
helper_pid=""
companion_pid=""
fixture_pid=""
seed_pid=""
broken_helper_pid=""

cleanup() {
    local status=$?
    local pid

    trap - EXIT
    for pid in "$fixture_pid" "$companion_pid" "$helper_pid" \
        "$broken_helper_pid" "$seed_pid"; do
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    if [[ -d "$wine_prefix" ]]; then
        WINEPREFIX="$wine_prefix" "$wineserver_bin" -k \
            >/dev/null 2>&1 || true
    fi
    for pid in "$wine_xvfb_pid" "$host_xvfb_pid"; do
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    wait 2>/dev/null || true
    if [[ "${UURB_KEEP_TEST_TMP:-0}" == 1 || "$status" -ne 0 ]]; then
        printf 'isolated test artifacts: %s\n' "$temporary_dir" >&2
    elif [[ "$temporary_dir" == "${TMPDIR:-/tmp}/uurb-controller-clipboard."* ]]; then
        rm -rf -- "$temporary_dir"
    fi
    exit "$status"
}
trap cleanup EXIT

for command in flock timeout Xvfb xclip xdpyinfo gcc pgrep python3 \
    x86_64-w64-mingw32-gcc "$wine_bin" "$wineboot_bin" \
    "$wineserver_bin"; do
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
    -municode \
    -DUURB_FIXTURE_TEXT='L"Mac controller 中文\r\nsecond line"' \
    -o "$temporary_dir/GameViewer.exe" \
    "$repo_dir/tests/probes/uu_controller_clipboard_fixture.c" -luser32
x86_64-w64-mingw32-gcc -std=c11 -O2 -Wall -Wextra -Werror \
    -municode \
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
    "$wineboot_bin" -u >/dev/null 2>&1

sentinel='existing host clipboard'
printf '%s' "$sentinel" | DISPLAY="$host_display" \
    xclip -selection clipboard -in -loops 0 -verbose \
    >"$temporary_dir/seed-xclip.log" 2>&1 &
seed_pid=$!
for _ in {1..40}; do
    observed="$(DISPLAY="$host_display" timeout 0.2 \
        xclip -selection clipboard -out 2>/dev/null || true)"
    [[ "$observed" == "$sentinel" ]] && break
    sleep 0.05
done
[[ "$observed" == "$sentinel" ]]

# A connected client that sends no handshake must not monopolize the helper.
exec 8<>"/dev/tcp/127.0.0.1/$port"
sleep 1.2
exec 8>&- 8<&-

# Clipboard content already owned by GameViewer when the companion starts is
# the baseline, not an event to forward to the host.
DISPLAY="$wine_display" WINEPREFIX="$wine_prefix" WINEDEBUG=-all \
    WINEDLLOVERRIDES='mscoree,mshtml=' \
    "$wine_bin" "$temporary_dir/GameViewer.exe" \
    >"$temporary_dir/startup-fixture.log" 2>&1 &
fixture_pid=$!
for _ in {1..100}; do
    grep -q 'fixture clipboard ready' \
        "$temporary_dir/startup-fixture.log" 2>/dev/null && break
    kill -0 "$fixture_pid" 2>/dev/null || break
    sleep 0.05
done
grep -q 'fixture clipboard ready' "$temporary_dir/startup-fixture.log"
DISPLAY="$wine_display" WINEPREFIX="$wine_prefix" WINEDEBUG=-all \
    WINEDLLOVERRIDES='mscoree,mshtml=' \
    UURB_X11_CLIPBOARD_PORT="$port" UURB_X11_CLIPBOARD_TOKEN="$token" \
    "$wine_bin" \
    "$temporary_dir/compat/uu-wine-clipboard-bridge.exe" \
    >"$temporary_dir/companion.log" 2>&1 &
companion_pid=$!
for _ in {1..80}; do
    grep -q 'Wine clipboard companion ready' \
        "$temporary_dir/companion.log" 2>/dev/null && break
    kill -0 "$companion_pid" 2>/dev/null || break
    sleep 0.05
done
grep -q 'Wine clipboard companion ready' "$temporary_dir/companion.log"
sleep 0.25
observed="$(DISPLAY="$host_display" timeout 0.5 \
    xclip -selection clipboard -out 2>/dev/null || true)"
[[ "$observed" == "$sentinel" ]] || {
    printf 'clipboard content present before companion startup was replayed\n' >&2
    exit 1
}
wait "$fixture_pid"
fixture_pid=""

DISPLAY="$wine_display" WINEPREFIX="$wine_prefix" WINEDEBUG=-all \
    WINEDLLOVERRIDES='mscoree,mshtml=' \
    "$wine_bin" "$temporary_dir/GameViewer.exe" \
    >"$temporary_dir/gameviewer-fixture.log" 2>&1 &
fixture_pid=$!
for _ in {1..100}; do
    grep -q 'fixture clipboard ready' \
        "$temporary_dir/gameviewer-fixture.log" 2>/dev/null && break
    kill -0 "$fixture_pid" 2>/dev/null || break
    sleep 0.05
done
grep -q 'fixture clipboard ready' "$temporary_dir/gameviewer-fixture.log"
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
observed_primary="$(DISPLAY="$host_display" timeout 0.5 \
    xclip -selection primary -out 2>/dev/null || true)"
[[ "$observed_primary" == "$expected" ]] || {
    printf 'GameViewer-owned Unicode text did not reach PRIMARY exactly\n' >&2
    exit 1
}
wait "$fixture_pid"
fixture_pid=""

DISPLAY="$wine_display" WINEPREFIX="$wine_prefix" WINEDEBUG=-all \
    WINEDLLOVERRIDES='mscoree,mshtml=' \
    "$wine_bin" "$temporary_dir/OtherApp.exe" \
    >"$temporary_dir/other-fixture.log" 2>&1 &
fixture_pid=$!
for _ in {1..100}; do
    grep -q 'fixture clipboard ready' \
        "$temporary_dir/other-fixture.log" 2>/dev/null && break
    kill -0 "$fixture_pid" 2>/dev/null || break
    sleep 0.05
done
grep -q 'fixture clipboard ready' "$temporary_dir/other-fixture.log"
sleep 0.5
observed="$(DISPLAY="$host_display" timeout 0.5 \
    xclip -selection clipboard -out 2>/dev/null || true)"
[[ "$observed" == "$expected" ]] || {
    printf 'non-GameViewer clipboard owner crossed the one-way boundary\n' >&2
    exit 1
}
wait "$fixture_pid"
fixture_pid=""

mapfile -t owner_pids < <(pgrep -P "$helper_pid" -x xclip || true)
[[ "${#owner_pids[@]}" -eq 2 ]] || {
    printf 'native helper does not supervise exactly two xclip owners\n' >&2
    exit 1
}
kill "$helper_pid"
wait "$helper_pid"
helper_pid=""
for pid in "${owner_pids[@]}"; do
    for _ in {1..40}; do
        kill -0 "$pid" 2>/dev/null || break
        sleep 0.05
    done
    if kill -0 "$pid" 2>/dev/null; then
        printf 'xclip owner survived native-helper shutdown: %s\n' "$pid" >&2
        exit 1
    fi
done

# A missing or failed xclip must produce an owner error and preserve the
# current host selection rather than acknowledging data it did not install.
broken_ready_file="$temporary_dir/broken-x11-clipboard.port"
broken_token="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
gcc -std=c11 -O2 -Wall -Wextra -Werror \
    -DUURB_XCLIP_PATH='"/nonexistent/uurb-xclip"' \
    -I "$repo_dir/src" -o "$temporary_dir/uu-x11-clipboard-broken" \
    "$repo_dir/src/uu_x11_clipboard.c" -ldl
printf '%s' "$sentinel" | DISPLAY="$host_display" \
    xclip -selection clipboard -in -loops 0 -verbose \
    >"$temporary_dir/broken-seed-xclip.log" 2>&1 &
seed_pid=$!
DISPLAY="$host_display" UURB_X11_CLIPBOARD_TOKEN="$broken_token" \
    "$temporary_dir/uu-x11-clipboard-broken" \
    --ready-file "$broken_ready_file" \
    >"$temporary_dir/broken-x11-clipboard.log" 2>&1 &
broken_helper_pid=$!
for _ in {1..50}; do
    [[ -s "$broken_ready_file" ]] && break
    sleep 0.1
done
[[ -s "$broken_ready_file" ]]
broken_port="$(tr -d '[:space:]' <"$broken_ready_file")"
python3 - "$broken_port" "$broken_token" <<'PY'
import socket
import struct
import sys

magic = 0x43425555
port = int(sys.argv[1])
token = sys.argv[2].encode("ascii")

def receive_exact(connection, size):
    chunks = []
    while size:
        chunk = connection.recv(size)
        if not chunk:
            raise SystemExit("clipboard helper closed before its response")
        chunks.append(chunk)
        size -= len(chunk)
    return b"".join(chunks)

with socket.create_connection(("127.0.0.1", port), timeout=2) as connection:
    connection.sendall(struct.pack("<II64s", magic, 1, token))
    assert struct.unpack("<IIII", receive_exact(connection, 16)) == (magic, 0, 1, 0)
    payload = b"must not be acknowledged"
    connection.sendall(struct.pack("<IIII", magic, 77, len(payload), 0) + payload)
    assert struct.unpack("<IIII", receive_exact(connection, 16)) == (
        magic, 77, 0, 0x3003
    )
PY
observed="$(DISPLAY="$host_display" timeout 0.5 \
    xclip -selection clipboard -out 2>/dev/null || true)"
[[ "$observed" == "$sentinel" ]] || {
    printf 'failed xclip launch displaced the host clipboard\n' >&2
    exit 1
}
kill "$broken_helper_pid"
wait "$broken_helper_pid"
broken_helper_pid=""

printf 'controller-clipboard=GameViewer Unicode multiline exact\n'
printf 'owner-filter=non-GameViewer ignored\n'
printf 'startup-baseline=existing content ignored\n'
printf 'selection-owners=CLIPBOARD and PRIMARY confirmed\n'
printf 'failure-mode=xclip failure rejected\n'
printf 'lifecycle=deadlines bounded and owner children reaped\n'
printf 'direction=Wine-to-X11-only\n'
