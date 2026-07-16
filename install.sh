#!/usr/bin/env bash

set -Eeuo pipefail
umask 077

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
bridge_user="${USER:-$(id -un)}"
wine_prefix="${WINEPREFIX:-$HOME/.local/share/wineprefixes/uu-remote}"
wine_bin='/opt/wine-stable/bin/wine'
wineserver_bin='/opt/wine-stable/bin/wineserver'
grdctl_bin='/usr/bin/grdctl'
openssl_bin='/usr/bin/openssl'
python_bin='/usr/bin/python3'
secret_tool_bin='/usr/bin/secret-tool'
systemctl_user=(
    /usr/bin/env
    "DBUS_SESSION_BUS_ADDRESS=unix:path=${XDG_RUNTIME_DIR:-/run/user/$UID}/bus"
    /usr/bin/systemctl --user
)
uu_dir="$wine_prefix/drive_c/Program Files/Netease/GameViewer"
uu_bin="$uu_dir/bin"
release_manifest="${UURB_RELEASE_MANIFEST:-$repo_dir/patches/uu-remote-4.33.0.8907.json}"
installed_manifest="$wine_prefix/compat/release-manifest.json"
server_exe=''
healthd_exe=''
compat_build="$repo_dir/build/compat"
freerdp_build="$repo_dir/build/freerdp"
freerdp_install="$wine_prefix/drive_c/Program Files/FreeRDP"
uu_download_url=''
uu_installer_filename=''
uu_installer_sha256=''
healthd_sha256=''
rdp_port="${UURB_RDP_PORT:-3390}"
uu_installer=''
skip_packages=false
skip_account_login=false
start_service=true
fresh_install=false

usage() {
    cat <<'EOF'
usage: ./install.sh [options]

  --uu-installer PATH    use a previously downloaded audited installer
  --release-manifest PATH
                         use an approved release manifest
  --skip-packages        do not install Ubuntu/Wine package dependencies
  --skip-account-login   do not open UU for first-time account sign-in
  --no-start             install and verify files without starting the service
  -h, --help             show this help
EOF
}

while (($#)); do
    case "$1" in
        --uu-installer)
            uu_installer="${2:?--uu-installer requires a path}"
            shift 2
            ;;
        --release-manifest)
            release_manifest="${2:?--release-manifest requires a path}"
            shift 2
            ;;
        --skip-packages)
            skip_packages=true
            shift
            ;;
        --skip-account-login)
            skip_account_login=true
            shift
            ;;
        --no-start)
            start_service=false
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            printf 'unknown option: %s\n' "$1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ $EUID -eq 0 ]]; then
    printf 'Run this installer as the desktop user, not as root.\n' >&2
    exit 1
fi
if [[ "$(uname -m)" != x86_64 ]]; then
    printf 'Only x86_64 Ubuntu is currently supported.\n' >&2
    exit 1
fi
if [[ ! "$rdp_port" =~ ^[0-9]+$ ]]; then
    printf 'UURB_RDP_PORT must be numeric.\n' >&2
    exit 2
fi

install_winehq() {
    local codename
    local temporary

    if [[ -x "$wine_bin" ]]; then
        return
    fi
    # shellcheck source=/dev/null
    source /etc/os-release
    codename="${VERSION_CODENAME:?Ubuntu codename is unavailable}"
    temporary="$(mktemp -d)"

    sudo dpkg --add-architecture i386
    curl -fsSL https://dl.winehq.org/wine-builds/winehq.key \
        -o "$temporary/winehq.key"
    curl -fsSL \
        "https://dl.winehq.org/wine-builds/ubuntu/dists/$codename/winehq-$codename.sources" \
        -o "$temporary/winehq-$codename.sources"
    sudo install -d -m 0755 /etc/apt/keyrings
    sudo install -m 0644 "$temporary/winehq.key" \
        /etc/apt/keyrings/winehq-archive.key
    sudo install -m 0644 "$temporary/winehq-$codename.sources" \
        "/etc/apt/sources.list.d/winehq-$codename.sources"
    sudo apt-get update
    sudo apt-get install -y --install-recommends winehq-stable
    rm -rf "$temporary"
}

install_packages() {
    sudo apt-get update
    sudo apt-get install -y \
        aria2 ca-certificates cmake curl freerdp3-x11 gcc-mingw-w64-x86-64 \
        git gnome-remote-desktop jq libsecret-tools ninja-build openbox \
        openssl p7zip-full python3 tar x11-utils xauth xdotool xvfb zstd
    install_winehq
}

stop_wine_prefix() {
    # Wine 11 can leave idle device-service processes behind after a silent
    # installer exits. An unbounded `wineserver -w` then waits forever.
    /usr/bin/timeout --kill-after=2s 10s \
        "$wineserver_bin" -k >/dev/null 2>&1 || true
    /usr/bin/timeout --kill-after=2s 10s \
        "$wineserver_bin" -w >/dev/null 2>&1 || true
}

download_verified() {
    local url="$1"
    local expected="$2"
    local destination="$3"
    local attempt

    if [[ -f "$destination" ]] &&
       printf '%s  %s\n' "$expected" "$destination" | sha256sum -c - \
           >/dev/null 2>&1; then
        return
    fi

    mkdir -p "$(dirname -- "$destination")"
    for attempt in 1 2; do
        if command -v aria2c >/dev/null 2>&1; then
            aria2c --allow-overwrite=true --auto-file-renaming=false \
                --continue=true --max-connection-per-server=8 \
                --max-tries=5 --min-split-size=1M --retry-wait=2 --split=8 \
                --dir="$(dirname -- "$destination")" \
                --out="$(basename -- "$destination").part" "$url"
        else
            curl --continue-at - --fail --location --retry 3 \
                --output "$destination.part" "$url"
        fi
        if printf '%s  %s\n' "$expected" "$destination.part" | \
            sha256sum -c -; then
            mv "$destination.part" "$destination"
            rm -f "$destination.part.aria2"
            return
        fi
        rm -f "$destination.part" "$destination.part.aria2"
        printf 'download hash mismatch; retrying %s (%s/2)\n' \
            "$url" "$attempt" >&2
    done

    printf 'download verification failed: %s\n' "$url" >&2
    exit 1
}

if [[ "$skip_packages" == false ]]; then
    install_packages
fi

for command in curl sha256sum /usr/bin/systemctl \
    timeout \
    "$grdctl_bin" "$openssl_bin" "$python_bin" "$secret_tool_bin" \
    "$wine_bin" "$wineserver_bin"; do
    if ! command -v "$command" >/dev/null 2>&1; then
        printf 'missing required command: %s\n' "$command" >&2
        exit 1
    fi
done

release_manifest="$(realpath "$release_manifest")"
manifest_field() {
    "$python_bin" "$repo_dir/scripts/patch-gameviewer.py" field "$1" \
        --manifest "$release_manifest"
}

uu_download_url="$(manifest_field installer.url)"
uu_installer_filename="$(manifest_field installer.filename)"
uu_installer_sha256="$(manifest_field installer.sha256)"
server_exe="$uu_bin/$(manifest_field server.filename)"
healthd_exe="$uu_bin/$(manifest_field health_monitor.filename)"
healthd_sha256="$(manifest_field health_monitor.original_sha256)"

export WINEPREFIX="$wine_prefix"
export WINEDEBUG=-all
export WINEDLLOVERRIDES='winedbg.exe=d;mscoree,mshtml='

"${systemctl_user[@]}" stop uu-remote-bridge.service >/dev/null 2>&1 || true
stop_wine_prefix

if [[ ! -f "$uu_dir/GameViewer.exe" ]]; then
    fresh_install=true
    mkdir -p "$repo_dir/build/downloads"
    if [[ -z "$uu_installer" ]]; then
        uu_installer="$repo_dir/build/downloads/$uu_installer_filename"
        download_verified "$uu_download_url" "$uu_installer_sha256" \
            "$uu_installer"
    else
        uu_installer="$(realpath "$uu_installer")"
    fi
    printf '%s  %s\n' "$uu_installer_sha256" "$uu_installer" | \
        sha256sum -c -
    mkdir -p "$wine_prefix"
    "$wine_bin" wineboot -u
    "$wine_bin" winecfg -v win10
    "$wine_bin" "$uu_installer" /S
    stop_wine_prefix
fi
if [[ ! -f "$server_exe" || ! -f "$healthd_exe" ]]; then
    printf 'UU Remote installation did not produce the expected files.\n' >&2
    exit 1
fi
"$python_bin" "$repo_dir/scripts/patch-gameviewer.py" verify "$server_exe" \
    --manifest "$release_manifest" >/dev/null

"$repo_dir/scripts/build-compat.sh" "$compat_build"
"$repo_dir/scripts/build-winpr.sh" "$freerdp_build"

mkdir -p "$wine_prefix/compat" "$freerdp_install"
install -m 0644 "$release_manifest" "$installed_manifest"
install -m 0755 \
    "$compat_build/uu-input-bridge.dll" \
    "$compat_build/uu-input-broker.exe" \
    "$compat_build/uu-injector.exe" \
    "$compat_build/uu-service-control.exe" \
    "$wine_prefix/compat/"
install -m 0755 "$compat_build/winlogon.exe" \
    "$wine_prefix/compat/winlogon.exe"
install -m 0755 "$compat_build/winlogon.exe.so" \
    "$wine_prefix/compat/winlogon.exe.so"
install -m 0755 "$freerdp_build/"*.dll "$freerdp_build/sdl-freerdp.exe" \
    "$freerdp_install/"
install -m 0755 "$compat_build/winpr-sspi-shim.dll" \
    "$freerdp_install/winpr-sspi-shim.dll"
mkdir -p "$freerdp_install/ossl-modules"
install -m 0755 "$freerdp_build/ossl-modules/legacy.dll" \
    "$freerdp_install/ossl-modules/legacy.dll"

healthd_backup="$healthd_exe.uu-original"
healthd_current_hash="$(sha256sum "$healthd_exe" | awk '{print $1}')"
if [[ "$healthd_current_hash" == "$healthd_sha256" ]]; then
    [[ -f "$healthd_backup" ]] || cp -p "$healthd_exe" "$healthd_backup"
elif [[ ! -f "$healthd_backup" ]] || \
     [[ "$(sha256sum "$healthd_backup" | awk '{print $1}')" != "$healthd_sha256" ]]; then
    printf 'Refusing to replace an unknown GameViewerHealthd.exe build.\n' >&2
    exit 1
fi
install -m 0755 "$compat_build/uu-healthd-stub.exe" "$healthd_exe"

"$python_bin" "$repo_dir/scripts/patch-gameviewer.py" patch "$server_exe" \
    --manifest "$installed_manifest"

install -d -m 0755 "$HOME/.local/bin" "$HOME/.config/systemd/user"
install -m 0755 "$repo_dir/scripts/uu-remote-bridge" \
    "$HOME/.local/bin/uu-remote-bridge"
install -m 0755 "$repo_dir/scripts/uu-remote" "$HOME/.local/bin/uu-remote"
install -m 0644 "$repo_dir/systemd/uu-remote-bridge.service" \
    "$HOME/.config/systemd/user/uu-remote-bridge.service"

tls_dir="$HOME/.local/share/gnome-remote-desktop"
tls_cert="$tls_dir/rdp-tls.crt"
tls_key="$tls_dir/rdp-tls.key"
mkdir -p "$tls_dir"
if [[ ! -s "$tls_cert" || ! -s "$tls_key" ]]; then
    "$openssl_bin" req -new -newkey rsa:3072 -days 730 -nodes -x509 \
        -subj "/CN=$(hostname) UU Remote bridge" \
        -keyout "$tls_key" -out "$tls_cert"
    chmod 0600 "$tls_key"
fi

rdp_password="$("$secret_tool_bin" lookup service uu-desktop-bridge \
    username "$bridge_user" || true)"
if [[ -z "$rdp_password" ]]; then
    while true; do
        read -rsp 'Password for the local GNOME RDP relay: ' rdp_password
        printf '\n'
        read -rsp 'Repeat the relay password: ' confirmation
        printf '\n'
        if [[ -n "$rdp_password" && "$rdp_password" == "$confirmation" ]]; then
            unset confirmation
            break
        fi
        printf 'Passwords did not match or were empty.\n' >&2
    done
fi

"$grdctl_bin" rdp set-port "$rdp_port"
"$grdctl_bin" rdp set-tls-cert "$tls_cert"
"$grdctl_bin" rdp set-tls-key "$tls_key"
"$grdctl_bin" rdp set-credentials "$bridge_user" "$rdp_password"
"$grdctl_bin" rdp disable-view-only
"$grdctl_bin" rdp disable-port-negotiation
"$grdctl_bin" rdp enable
printf '%s' "$rdp_password" | "$secret_tool_bin" store \
    --label='UU Remote Ubuntu bridge RDP credential' \
    service uu-desktop-bridge username "$bridge_user"
unset rdp_password

"${systemctl_user[@]}" daemon-reload
"${systemctl_user[@]}" reenable uu-remote-bridge.service

if [[ "$fresh_install" == true && "$skip_account_login" == false ]]; then
    printf '\nUU Remote needs an authenticated account once.\n'
    printf 'Complete the official UU sign-in window, then close that window.\n'
    (cd "$uu_dir" && "$wine_bin" GameViewer.exe) || true
    stop_wine_prefix
fi

if [[ "$start_service" == true ]]; then
    "${systemctl_user[@]}" restart uu-remote-bridge.service
    "$repo_dir/scripts/verify.sh" --quick
fi

printf '\nInstalled UU Remote Ubuntu bridge.\n'
printf 'Service: systemctl --user status uu-remote-bridge.service\n'
printf 'Logs:    uu-remote logs\n'
