#!/usr/bin/env bash

set -Eeuo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
bridge_user="${USER:-$(id -un)}"
wine_prefix="${WINEPREFIX:-$HOME/.local/share/wineprefixes/uu-remote}"
release_manifest="${UURB_RELEASE_MANIFEST:-$wine_prefix/compat/release-manifest.json}"
if [[ ! -f "$release_manifest" ]]; then
    release_manifest="$repo_dir/patches/uu-remote-4.33.0.8907.json"
fi
manifest_field() {
    /usr/bin/python3 "$repo_dir/scripts/patch-gameviewer.py" field "$1" \
        --manifest "$release_manifest"
}
release_version="$(manifest_field version)"
server="$wine_prefix/drive_c/Program Files/Netease/GameViewer/bin/$(manifest_field server.filename)"
healthd="$wine_prefix/drive_c/Program Files/Netease/GameViewer/bin/$(manifest_field health_monitor.filename)"
healthd_original_sha256="$(manifest_field health_monitor.original_sha256)"
healthd_stub="$repo_dir/build/compat/uu-healthd-stub.exe"
freerdp="$wine_prefix/drive_c/Program Files/FreeRDP/sdl-freerdp.exe"
# GameViewerServer is launched by Wine's service manager, which intentionally
# does not inherit UU_INPUT_BRIDGE_LOG. The injected DLL therefore uses the
# target process's normal GetTempPathW() location.
bridge_log="$wine_prefix/drive_c/users/$bridge_user/AppData/Local/Temp/uu-input-bridge.log"
broker_log="$wine_prefix/drive_c/users/$bridge_user/Temp/uu-input-broker.log"
stability_seconds=270
errors=0
systemctl_user=(
    /usr/bin/env
    "DBUS_SESSION_BUS_ADDRESS=unix:path=${XDG_RUNTIME_DIR:-/run/user/$UID}/bus"
    /usr/bin/systemctl --user
)

if [[ "${1:-}" == --quick ]]; then
    stability_seconds=0
    shift
elif [[ "${1:-}" == --stability-seconds ]]; then
    stability_seconds="${2:?--stability-seconds requires a number}"
    shift 2
fi
if (($#)) || [[ ! "$stability_seconds" =~ ^[0-9]+$ ]]; then
    printf 'usage: scripts/verify.sh [--quick|--stability-seconds N]\n' >&2
    exit 2
fi

pass() {
    printf 'PASS  %s\n' "$1"
}

fail() {
    printf 'FAIL  %s\n' "$1" >&2
    errors=$((errors + 1))
}

for _ in {1..180}; do
    if "${systemctl_user[@]}" is-active --quiet uu-remote-bridge.service && \
       pgrep -u "$UID" -f 'GameViewerServer\.exe' >/dev/null && \
       pgrep -u "$UID" -f 'sdl-freerdp\.exe' >/dev/null; then
        break
    fi
    sleep 0.25
done

if "${systemctl_user[@]}" is-active --quiet uu-remote-bridge.service; then
    pass 'systemd user service is active'
else
    fail 'systemd user service is not active'
fi

pass "approved UU release manifest $release_version is active"

if /usr/bin/python3 "$repo_dir/scripts/patch-gameviewer.py" verify "$server" \
    --manifest "$release_manifest" --expect patched >/dev/null; then
    pass 'GameViewerServer.exe is the audited patched build'
else
    fail 'GameViewerServer.exe verification failed'
fi

if [[ -f "$healthd.uu-original" ]] && \
   [[ "$(sha256sum "$healthd.uu-original" | awk '{print $1}')" == \
      "$healthd_original_sha256" ]] && \
   [[ -f "$healthd_stub" ]] && cmp -s "$healthd" "$healthd_stub"; then
    pass 'health monitor stub is installed with an audited backup'
else
    fail 'health monitor stub or backup verification failed'
fi

if [[ -f "$freerdp" ]] && \
   [[ "$(sha256sum "$freerdp" | awk '{print $1}')" == \
      1534187d731b2e4a6cb6d1107c0129727517fe3acf1441b5a2567aea5ea31d60 ]]; then
    pass 'pinned Windows FreeRDP SDL client is installed'
else
    fail 'Windows FreeRDP SDL client verification failed'
fi

if [[ -f "$bridge_log" ]] && \
   grep -q 'UU SendInput bridge active' "$bridge_log" && \
   grep -q 'UU Wine event-log compatibility active' "$bridge_log"; then
    pass 'input and Wine event-log hooks are active'
else
    fail 'input or Wine event-log hook did not initialize'
fi

if [[ -f "$broker_log" ]] && \
   grep -q 'UU input broker active' "$broker_log"; then
    pass 'local input broker is active'
else
    fail 'local input broker did not initialize'
fi

rdp_port="${UURB_RDP_PORT:-3390}"
configured_rdp_port="$(
    /usr/bin/gsettings get org.gnome.desktop.remote-desktop.rdp port | \
        /usr/bin/awk '{print $2}'
)"
if [[ "$configured_rdp_port" != "$rdp_port" ]]; then
    fail "GNOME RDP is configured for port $configured_rdp_port, expected $rdp_port"
elif /usr/bin/ss -H -ltnp "sport = :$rdp_port" 2>/dev/null | \
     /usr/bin/grep -q 'gnome-remote-de'; then
    pass "GNOME RDP relay owns localhost:$rdp_port"
else
    fail "GNOME RDP relay is unavailable on localhost:$rdp_port"
fi

server_pid="$(pgrep -o -u "$UID" -f 'GameViewerServer\.exe' || true)"
if [[ -n "$server_pid" ]]; then
    pass "UU server is running as process $server_pid"
else
    fail 'UU server is not running'
fi

if ((stability_seconds > 0)) && [[ -n "$server_pid" ]]; then
    printf 'WAIT  checking one server PID for %s seconds\n' "$stability_seconds"
    sleep "$stability_seconds"
    current_pid="$(pgrep -o -u "$UID" -f 'GameViewerServer\.exe' || true)"
    if [[ "$current_pid" == "$server_pid" ]]; then
        pass "UU server remained stable for $stability_seconds seconds"
    else
        fail "UU server changed from $server_pid to ${current_pid:-none}"
    fi
fi

if [[ -f "$bridge_log" ]] && \
   tail -500 "$bridge_log" | grep -q 'route=broker result=1 error=0'; then
    pass 'at least one real input event completed through the broker'
elif [[ -f "$bridge_log" ]] && \
     grep -q 'route=broker result=1 error=0' "$bridge_log"; then
    pass 'historical controller input completed through the broker'
else
    printf 'INFO  no remote input event has been observed yet\n'
fi

if ((errors > 0)); then
    printf '%s verification check(s) failed\n' "$errors" >&2
    exit 1
fi
printf 'All bridge verification checks passed.\n'
