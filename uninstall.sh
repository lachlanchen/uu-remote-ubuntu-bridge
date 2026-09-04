#!/usr/bin/env bash

set -Eeuo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
bridge_user="${USER:-$(id -un)}"
wine_prefix="${WINEPREFIX:-$HOME/.local/share/wineprefixes/uu-remote}"
uu_bin="$wine_prefix/drive_c/Program Files/Netease/GameViewer/bin"
terminal_proxy="$uu_bin/powershell.exe"
installed_terminal_proxy="$wine_prefix/compat/uu-terminal-proxy.exe"
terminal_config="$uu_bin/uu-terminal-bridge.runtime"
release_manifest="${UURB_RELEASE_MANIFEST:-$wine_prefix/compat/release-manifest.json}"
if [[ ! -f "$release_manifest" ]]; then
    release_manifest="$repo_dir/patches/uu-remote-4.33.0.8907.json"
fi
manifest_field() {
    /usr/bin/python3 "$repo_dir/scripts/patch-gameviewer.py" field "$1" \
        --manifest "$release_manifest"
}
purge=false
dry_run=false
systemctl_user=(
    /usr/bin/env
    "DBUS_SESSION_BUS_ADDRESS=unix:path=${XDG_RUNTIME_DIR:-/run/user/$UID}/bus"
    /usr/bin/systemctl --user
)

while (($#)); do
    case "$1" in
        --purge)
            purge=true
            shift
            ;;
        --dry-run)
            dry_run=true
            shift
            ;;
        -h|--help)
            printf 'usage: ./uninstall.sh [--purge] [--dry-run]\n'
            exit 0
            ;;
        *)
            printf 'usage: ./uninstall.sh [--purge] [--dry-run]\n' >&2
            exit 2
            ;;
    esac
done

server="$uu_bin/$(manifest_field server.filename)"
if [[ -f "$server.uu-original" ]]; then
    /usr/bin/python3 "$repo_dir/scripts/patch-gameviewer.py" verify \
        "$server.uu-original" --manifest "$release_manifest" \
        --expect original >/dev/null
fi
healthd="$uu_bin/$(manifest_field health_monitor.filename)"
if [[ -f "$healthd.uu-original" ]]; then
    healthd_original_sha256="$(manifest_field health_monitor.original_sha256)"
    if [[ "$(sha256sum "$healthd.uu-original" | awk '{print $1}')" != \
          "$healthd_original_sha256" ]]; then
        printf 'Refusing to restore an unknown GameViewerHealthd.exe backup.\n' >&2
        exit 1
    fi
fi
release_version="$(manifest_field version)"
devcon="$uu_bin/drivers/devcon.exe"
devcon_backup="$devcon.uu-original"
case "$release_version" in
    4.33.0.8907|4.34.0.8979|4.39.1.1375|4.39.2.1561)
        devcon_original_sha256='46731d6ea59dd9b63ad641c79646bb5ff64e1b877a1226536e3fe34d1ab4ee10'
        ;;
    *)
        devcon_original_sha256=''
        ;;
esac
if [[ -f "$devcon_backup" ]] &&
   { [[ -z "$devcon_original_sha256" ]] ||
     [[ "$(sha256sum "$devcon_backup" | awk '{print $1}')" != \
        "$devcon_original_sha256" ]]; }; then
    printf 'Refusing to restore an unknown devcon.exe backup.\n' >&2
    exit 1
fi
if [[ -f "$devcon_backup" && -e "$devcon" ]] &&
   { [[ ! -f "$devcon" ]] ||
     [[ "$(sha256sum "$devcon" | awk '{print $1}')" != \
        "$devcon_original_sha256" ]]; }; then
    printf 'Refusing to overwrite an unknown live devcon.exe.\n' >&2
    exit 1
fi
if [[ -e "$terminal_proxy" ]] &&
   { [[ ! -f "$installed_terminal_proxy" ]] ||
     ! /usr/bin/cmp -s "$terminal_proxy" "$installed_terminal_proxy"; }; then
    printf 'Refusing to remove an unknown GameViewer bin/powershell.exe.\n' >&2
    exit 1
fi

if [[ "$dry_run" == true ]]; then
    printf 'PASS  audited server, health-monitor, and driver-helper backups can be restored.\n'
    printf 'INFO  purge=%s; no service, file, credential, or RDP setting changed.\n' \
        "$purge"
    exit 0
fi

"${systemctl_user[@]}" disable --now uu-remote-bridge.service \
    >/dev/null 2>&1 || true
"${systemctl_user[@]}" disable --now uu-remote-console.service \
    >/dev/null 2>&1 || true
if [[ -x "$repo_dir/scripts/configure-updater.sh" ]]; then
    if [[ "$purge" == true ]]; then
        "$repo_dir/scripts/configure-updater.sh" disable --purge-state
    else
        "$repo_dir/scripts/configure-updater.sh" disable
    fi
fi
if [[ -f "$HOME/.config/uu-remote-bridge/login-keyring-password.cred" ]] || \
   "${systemctl_user[@]}" is-enabled --quiet uu-keyring-unlock.service; then
    "$repo_dir/scripts/configure-unattended.sh" disable
fi
"$repo_dir/scripts/stop-wine-prefix" \
    "$wine_prefix" /opt/wine-stable/bin/wineserver || true

if [[ -f "$server.uu-original" ]]; then
    /usr/bin/python3 "$repo_dir/scripts/patch-gameviewer.py" restore "$server" \
        --manifest "$release_manifest"
fi
if [[ -f "$healthd.uu-original" ]]; then
    install -m 0755 "$healthd.uu-original" "$healthd"
fi
if [[ -f "$devcon_backup" ]]; then
    install -m 0755 "$devcon_backup" "$devcon"
fi
if [[ -f "$terminal_proxy" ]] &&
   /usr/bin/cmp -s "$terminal_proxy" "$installed_terminal_proxy"; then
    rm -f "$terminal_proxy" "$terminal_config"
fi
if [[ "$purge" == false && -f "$wine_prefix/system.reg" ]]; then
    WINEPREFIX="$wine_prefix" WINEDEBUG=-all \
        /opt/wine-stable/bin/wine reg add \
        'HKEY_LOCAL_MACHINE\System\CurrentControlSet\Services\winebth' \
        /v Start /t REG_DWORD /d 3 /f >/dev/null
    "$repo_dir/scripts/stop-wine-prefix" \
        "$wine_prefix" /opt/wine-stable/bin/wineserver || true
fi

rm -f \
    "$HOME/.local/bin/uu-remote" \
    "$HOME/.local/bin/uu-remote-bridge" \
    "$HOME/.local/bin/uu-remote-console" \
    "$HOME/.local/bin/uu-remote-upgrade" \
    "$HOME/.local/bin/uu-agent" \
    "$HOME/.local/libexec/uu-clean-wine-device-registry" \
    "$HOME/.local/libexec/uu-connection-status" \
    "$HOME/.local/libexec/uu-inspect-wine-device-registry.py" \
    "$HOME/.local/libexec/uu-remote-stop-wine-prefix" \
    "$HOME/.local/bin/uu-keyring-unlock" \
    "$HOME/.config/systemd/user/uu-keyring-unlock.service" \
    "$HOME/.config/systemd/user/uu-remote-bridge.service" \
    "$HOME/.config/systemd/user/uu-remote-console.service" \
    "$HOME/.local/share/applications/uu-remote.desktop" \
    "$HOME/Desktop/UU Remote.desktop"
rm -rf \
    "$HOME/.config/uu-remote-bridge" \
    "$wine_prefix/compat" \
    "$wine_prefix/drive_c/Program Files/FreeRDP"
"${systemctl_user[@]}" daemon-reload

if [[ "$purge" == true ]]; then
    printf 'Purging the dedicated Wine prefix and bridge credentials.\n'
    rm -rf "$wine_prefix"
    /usr/bin/secret-tool clear service uu-desktop-bridge \
        username "$bridge_user" || true
    /usr/bin/grdctl rdp disable || true
    /usr/bin/grdctl rdp clear-credentials || true
fi

printf 'UU Remote Ubuntu bridge removed. The UU installation was %s.\n' \
    "$([[ "$purge" == true ]] && printf purged || printf preserved)"
