#!/usr/bin/env bash

set -Eeuo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
bridge_user="${USER:-$(id -un)}"
wine_prefix="${WINEPREFIX:-$HOME/.local/share/wineprefixes/uu-remote}"
environment_file="$HOME/.config/uu-remote-bridge/environment"
saved_setting() {
    local name="$1"

    [[ -f "$environment_file" ]] || return 0
    /usr/bin/sed -n "s/^${name}=//p" "$environment_file" | \
        /usr/bin/tail -n 1
}
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
libei_backport="$wine_prefix/compat/libei/libei.so.1.2.1"
network_filter="$wine_prefix/compat/uu-network-filter.so"
x11_input_helper="$wine_prefix/compat/uu-x11-input"
x11_input_ready_file="${XDG_RUNTIME_DIR:-/run/user/$UID}/uu-remote-bridge/x11-input.port"
runtime_digest_file="$wine_prefix/compat/.runtime-source-sha256"
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

while (($#)); do
    case "$1" in
        --quick)
            stability_seconds=0
            shift
            ;;
        --stability-seconds)
            stability_seconds="${2:?--stability-seconds requires a number}"
            shift 2
            ;;
        *)
            printf 'unknown verifier option: %s\n' "$1" >&2
            exit 2
            ;;
    esac
done
if [[ ! "$stability_seconds" =~ ^[0-9]+$ ]]; then
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

expected_runtime_digest="$("$repo_dir/scripts/runtime-source-digest")"
installed_runtime_digest="$(cat "$runtime_digest_file" 2>/dev/null || true)"
if [[ "$installed_runtime_digest" == "$expected_runtime_digest" ]]; then
    pass 'installed runtime matches this source checkout'
else
    fail 'installed runtime is older or differs from this source checkout; reinstall it'
fi

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

saved_text_key_delay_ms="$(saved_setting UURB_TEXT_KEY_DELAY_MS)"
text_key_delay_ms="${UURB_TEXT_KEY_DELAY_MS:-${saved_text_key_delay_ms:-8}}"
broker_configuration="$(
    grep 'UU input broker active text-delay-ms=' "$broker_log" 2>/dev/null | \
        tail -n 1 || true
)"
if [[ "$text_key_delay_ms" =~ ^[0-9]+$ ]] &&
   ((text_key_delay_ms <= 50)) &&
   [[ "$broker_configuration" == *"text-delay-ms=$text_key_delay_ms "* ]]; then
    pass "input broker uses a ${text_key_delay_ms} ms text-key delay"
else
    fail 'input broker text-key pacing is missing or differs from saved settings'
fi

saved_physical_key_delay_ms="$(saved_setting UURB_PHYSICAL_KEY_DELAY_MS)"
physical_key_delay_ms="${UURB_PHYSICAL_KEY_DELAY_MS:-${saved_physical_key_delay_ms:-0}}"
if [[ "$physical_key_delay_ms" =~ ^[0-9]+$ ]] &&
   ((physical_key_delay_ms <= 50)) &&
   [[ "$broker_configuration" == *"physical-delay-ms=$physical_key_delay_ms "* ]]; then
    pass "input broker uses a ${physical_key_delay_ms} ms physical-key delay"
else
    fail 'input broker physical-key pacing is missing or differs from saved settings'
fi

saved_keyboard_route="$(saved_setting UURB_KEYBOARD_ROUTE)"
keyboard_route="${UURB_KEYBOARD_ROUTE:-${saved_keyboard_route:-rdp}}"
active_keyboard_route="$(
    /usr/bin/sed -n 's/.* keyboard-route=\([^[:space:]]*\).*/\1/p' \
        <<<"$broker_configuration"
)"
if [[ "$keyboard_route" != rdp && "$keyboard_route" != x11 &&
      "$keyboard_route" != auto ]]; then
    fail "saved keyboard route is invalid: $keyboard_route"
elif [[ "$active_keyboard_route" != rdp &&
        "$active_keyboard_route" != x11 ]]; then
    fail 'input broker did not report an active keyboard route'
elif [[ "$keyboard_route" == rdp && "$active_keyboard_route" != rdp ]]; then
    fail 'input broker unexpectedly bypasses the requested RDP keyboard route'
elif [[ "$keyboard_route" == x11 && "$active_keyboard_route" != x11 ]]; then
    fail 'the requested direct X11 keyboard route is not active'
elif [[ "$active_keyboard_route" == x11 ]]; then
    if [[ -x "$x11_input_helper" ]] &&
       pgrep -u "$UID" -f "$x11_input_helper" >/dev/null &&
       [[ -s "$x11_input_ready_file" ]]; then
        pass 'direct X11 physical-key helper is active'
    else
        fail 'input broker reports X11 routing but its native helper is unavailable'
    fi
else
    pass 'compatible RDP physical-key route is active'
fi

saved_rdp_port="$(saved_setting UURB_RDP_PORT)"
rdp_port="${UURB_RDP_PORT:-${saved_rdp_port:-3390}}"
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

grd_pid="$(
    pgrep -o -u "$UID" -f \
        "gnome-remote-desktop-daemon --rdp-port $rdp_port" || true
)"
saved_grd_fd_restart_threshold="$(
    saved_setting UURB_GRD_FD_RESTART_THRESHOLD
)"
grd_fd_restart_threshold="${UURB_GRD_FD_RESTART_THRESHOLD:-${saved_grd_fd_restart_threshold:-4096}}"
if [[ -n "$grd_pid" ]]; then
    grd_fd_count="$(
        /usr/bin/find "/proc/$grd_pid/fd" -maxdepth 1 -type l \
            -printf '.\n' 2>/dev/null | /usr/bin/wc -l
    )"
    grd_soft_limit="$(
        /usr/bin/awk '$1 == "Max" && $2 == "open" && $3 == "files" {print $4}' \
            "/proc/$grd_pid/limits"
    )"
    if [[ -f "$libei_backport" ]] &&
       /usr/bin/grep -Fq "$libei_backport" "/proc/$grd_pid/maps"; then
        pass 'GNOME RDP uses the isolated patched libei keymap-FD backport'
    else
        fail 'GNOME RDP is not using the patched libei keymap-FD backport'
    fi
    if [[ "$grd_soft_limit" =~ ^[0-9]+$ ]] &&
       ((grd_soft_limit >= 65536)); then
        pass "GNOME RDP descriptor limit is $grd_soft_limit"
    else
        fail "GNOME RDP descriptor limit is only ${grd_soft_limit:-unknown}"
    fi
    if ((grd_fd_restart_threshold == 0)); then
        printf 'INFO  GNOME RDP descriptor restart guard is disabled\n'
    elif ((grd_fd_count < grd_fd_restart_threshold)); then
        pass "GNOME RDP uses $grd_fd_count/$grd_fd_restart_threshold guarded descriptors"
    else
        fail "GNOME RDP uses $grd_fd_count descriptors, at or above the $grd_fd_restart_threshold restart threshold"
    fi
fi

server_pid="$(pgrep -o -u "$UID" -f 'GameViewerServer\.exe' || true)"
if [[ -n "$server_pid" ]]; then
    pass "UU server is running as process $server_pid"
else
    fail 'UU server is not running'
fi

saved_network_interface="$(saved_setting UURB_NETWORK_INTERFACE)"
network_interface="${UURB_NETWORK_INTERFACE:-${saved_network_interface:-all}}"
active_network_interface=''
if [[ -n "$server_pid" && -r "/proc/$server_pid/environ" ]]; then
    active_network_interface="$(
        /usr/bin/tr '\0' '\n' <"/proc/$server_pid/environ" | \
            /usr/bin/sed -n 's/^UURB_NETWORK_INTERFACE=//p' | \
            /usr/bin/tail -n 1
    )"
fi
if [[ "$network_interface" == all ]]; then
    printf 'INFO  UU can use all host network interfaces\n'
elif [[ ! -f "$network_filter" ]]; then
    fail 'the configured UU network-interface filter is missing'
elif [[ -n "$server_pid" ]] &&
     /usr/bin/grep -Fq "$network_filter" "/proc/$server_pid/maps" &&
     [[ -n "$active_network_interface" ]] &&
     [[ -d "/sys/class/net/$active_network_interface" ]] &&
     { [[ "$network_interface" == default ]] ||
       [[ "$active_network_interface" == "$network_interface" ]]; }; then
    pass "UU network-interface filter is active ($network_interface -> $active_network_interface)"
else
    fail "UU network-interface filter is not active ($network_interface)"
fi

account_state="$({
    find "$wine_prefix/drive_c/users/$bridge_user/AppData/Local/GameViewer" \
        -maxdepth 1 -type f -name 'setting_*.ini' \
        ! -name 'setting_guest_anonymous_id.ini' -print -quit 2>/dev/null
} || true)"
if [[ -n "$account_state" ]]; then
    pass 'UU account state is present'
else
    printf 'INFO  UU account login has not been observed yet\n'
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
    if [[ -n "$grd_pid" ]]; then
        current_grd_pid="$(
            pgrep -o -u "$UID" -f \
                "gnome-remote-desktop-daemon --rdp-port $rdp_port" || true
        )"
        if [[ "$current_grd_pid" != "$grd_pid" ]]; then
            fail 'GNOME RDP changed during the descriptor-stability check'
        else
            current_grd_fd_count="$(
                /usr/bin/find "/proc/$grd_pid/fd" -maxdepth 1 -type l \
                    -printf '.\n' 2>/dev/null | /usr/bin/wc -l
            )"
            grd_fd_growth=$((current_grd_fd_count - grd_fd_count))
            if ((grd_fd_growth <= 16)); then
                pass "GNOME RDP descriptor growth stayed bounded (${grd_fd_growth} over ${stability_seconds}s)"
            else
                fail "GNOME RDP leaked $grd_fd_growth descriptors over ${stability_seconds}s"
            fi
        fi
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
