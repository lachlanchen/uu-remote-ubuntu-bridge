#!/usr/bin/env bash

set -Eeuo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
bridge_user="${USER:-$(id -un)}"
wine_prefix="${WINEPREFIX:-$HOME/.local/share/wineprefixes/uu-remote}"
uu_bin="$wine_prefix/drive_c/Program Files/Netease/GameViewer/bin"
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

if [[ "$dry_run" == true ]]; then
    printf 'PASS  audited server and health-monitor backups can be restored.\n'
    printf 'INFO  purge=%s; no service, file, credential, or RDP setting changed.\n' \
        "$purge"
    exit 0
fi

"${systemctl_user[@]}" disable --now uu-remote-bridge.service \
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

rm -f \
    "$HOME/.local/bin/uu-remote" \
    "$HOME/.local/bin/uu-remote-bridge" \
    "$HOME/.local/libexec/uu-connection-status" \
    "$HOME/.local/libexec/uu-remote-stop-wine-prefix" \
    "$HOME/.local/bin/uu-keyring-unlock" \
    "$HOME/.config/systemd/user/uu-keyring-unlock.service" \
    "$HOME/.config/systemd/user/uu-remote-bridge.service"
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
