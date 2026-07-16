#!/usr/bin/env bash

set -Eeuo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
bridge_user="${USER:-$(id -un)}"
wine_prefix="${WINEPREFIX:-$HOME/.local/share/wineprefixes/uu-remote}"
uu_bin="$wine_prefix/drive_c/Program Files/Netease/GameViewer/bin"
purge=false

if [[ "${1:-}" == --purge ]]; then
    purge=true
elif (($#)); then
    printf 'usage: ./uninstall.sh [--purge]\n' >&2
    exit 2
fi

systemctl --user disable --now uu-remote-bridge.service >/dev/null 2>&1 || true
/opt/wine-stable/bin/wineserver -k >/dev/null 2>&1 || true

server="$uu_bin/GameViewerServer.exe"
if [[ -f "$server.uu-original" ]]; then
    python3 "$repo_dir/scripts/patch-gameviewer.py" restore "$server"
fi
healthd="$uu_bin/GameViewerHealthd.exe"
if [[ -f "$healthd.uu-original" ]]; then
    healthd_original_sha256='ba4cdef465b3714940b154d6d40d7cfca4d65c3d639a6254bb0fb7be69bd19e6'
    if [[ "$(sha256sum "$healthd.uu-original" | awk '{print $1}')" != \
          "$healthd_original_sha256" ]]; then
        printf 'Refusing to restore an unknown GameViewerHealthd.exe backup.\n' >&2
        exit 1
    fi
    install -m 0755 "$healthd.uu-original" "$healthd"
fi

rm -f \
    "$HOME/.local/bin/uu-remote" \
    "$HOME/.local/bin/uu-remote-bridge" \
    "$HOME/.config/systemd/user/uu-remote-bridge.service"
rm -rf \
    "$wine_prefix/compat" \
    "$wine_prefix/drive_c/Program Files/FreeRDP"
systemctl --user daemon-reload

if [[ "$purge" == true ]]; then
    printf 'Purging the dedicated Wine prefix and bridge credentials.\n'
    rm -rf "$wine_prefix"
    secret-tool clear service uu-desktop-bridge username "$bridge_user" || true
    grdctl rdp disable || true
    grdctl rdp clear-credentials || true
fi

printf 'UU Remote Ubuntu bridge removed. The UU installation was %s.\n' \
    "$([[ "$purge" == true ]] && printf purged || printf preserved)"
