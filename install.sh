#!/usr/bin/env bash

set -Eeuo pipefail
umask 077

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/runtime-settings.sh
source "$repo_dir/scripts/runtime-settings.sh"
bridge_user="${USER:-$(id -un)}"
wine_prefix="${WINEPREFIX:-$HOME/.local/share/wineprefixes/uu-remote}"
config_dir="$HOME/.config/uu-remote-bridge"
environment_file="$config_dir/environment"
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
runtime_digest_file="$wine_prefix/compat/.runtime-source-sha256"
server_exe=''
healthd_exe=''
compat_build="$repo_dir/build/compat"
freerdp_build="$repo_dir/build/freerdp"
libei_build="$repo_dir/build/libei"
freerdp_install="$wine_prefix/drive_c/Program Files/FreeRDP"
libei_install="$wine_prefix/compat/libei"
uu_download_url=''
uu_installer_filename=''
uu_installer_sha256=''
healthd_sha256=''
terminal_proxy_install="$uu_bin/powershell.exe"
installed_terminal_proxy="$wine_prefix/compat/uu-terminal-proxy.exe"
saved_setting() {
    local name="$1"

    [[ -f "$environment_file" ]] || return 0
    /usr/bin/sed -n "s/^${name}=//p" "$environment_file" | \
        /usr/bin/tail -n 1
}
saved_rdp_port="$(saved_setting UURB_RDP_PORT)"
saved_resolution="$(saved_setting UURB_RESOLUTION)"
saved_follow_desktop_resolution="$(
    saved_setting UURB_FOLLOW_DESKTOP_RESOLUTION
)"
saved_display="$(saved_setting UURB_DISPLAY)"
saved_desktop_target="$(saved_setting UURB_DESKTOP_TARGET)"
saved_desktop_relay="$(saved_setting UURB_DESKTOP_RELAY)"
saved_vnc_grab_keyboard="$(saved_setting UURB_VNC_GRAB_KEYBOARD)"
saved_grd_fd_restart_threshold="$(
    saved_setting UURB_GRD_FD_RESTART_THRESHOLD
)"
saved_text_key_delay_ms="$(saved_setting UURB_TEXT_KEY_DELAY_MS)"
saved_physical_key_delay_ms="$(saved_setting UURB_PHYSICAL_KEY_DELAY_MS)"
saved_keyboard_route="$(saved_setting UURB_KEYBOARD_ROUTE)"
saved_phone_text_mode="$(saved_setting UURB_PHONE_TEXT_MODE)"
saved_network_interface="$(saved_setting UURB_NETWORK_INTERFACE)"
saved_cursor_guard="$(saved_setting UURB_CURSOR_GUARD)"
saved_cursor_size="$(saved_setting UURB_CURSOR_SIZE)"
saved_console_vnc_port="$(saved_setting UURB_CONSOLE_VNC_PORT)"
saved_console_web_port="$(saved_setting UURB_CONSOLE_WEB_PORT)"
rdp_port="${UURB_RDP_PORT:-${saved_rdp_port:-3390}}"
resolution="${UURB_RESOLUTION:-${saved_resolution:-1920x1080}}"
follow_desktop_resolution="${UURB_FOLLOW_DESKTOP_RESOLUTION:-${saved_follow_desktop_resolution:-off}}"
bridge_display="${UURB_DISPLAY:-${saved_display:-auto}}"
desktop_target="${UURB_DESKTOP_TARGET:-${saved_desktop_target:-auto}}"
desktop_relay="${UURB_DESKTOP_RELAY:-${saved_desktop_relay:-rdp}}"
vnc_grab_keyboard="${UURB_VNC_GRAB_KEYBOARD:-${saved_vnc_grab_keyboard:-on}}"
grd_fd_restart_threshold="${UURB_GRD_FD_RESTART_THRESHOLD:-${saved_grd_fd_restart_threshold:-4096}}"
text_key_delay_ms="$(resolve_text_key_delay \
    "$environment_file" "$saved_text_key_delay_ms")"
physical_key_delay_ms="${UURB_PHYSICAL_KEY_DELAY_MS:-${saved_physical_key_delay_ms:-0}}"
keyboard_route="${UURB_KEYBOARD_ROUTE:-${saved_keyboard_route:-rdp}}"
phone_text_mode="${UURB_PHONE_TEXT_MODE:-${saved_phone_text_mode:-auto}}"
network_interface="${UURB_NETWORK_INTERFACE:-${saved_network_interface:-all}}"
cursor_guard="${UURB_CURSOR_GUARD:-${saved_cursor_guard:-off}}"
cursor_size="${UURB_CURSOR_SIZE:-${saved_cursor_size:-auto}}"
console_vnc_port="${UURB_CONSOLE_VNC_PORT:-${saved_console_vnc_port:-5920}}"
console_web_port="${UURB_CONSOLE_WEB_PORT:-${saved_console_web_port:-6080}}"
uu_installer=''
skip_packages=false
skip_account_login=false
start_service=true
fresh_install=false
unattended=false
automatic_updates=false
upgrade_existing=false
prefix_only=false

usage() {
    cat <<'EOF'
usage: ./install.sh [options]

  --uu-installer PATH    use a previously downloaded audited installer
  --release-manifest PATH
                         use an approved release manifest
  --rdp-port PORT        local GNOME RDP relay port (default: 3390)
  --resolution WxH       relay resolution (default: 1920x1080)
  --follow-desktop-resolution off|on
                         after a stable X11 desktop resize, align and restart
                         only the UU bridge (default: off)
  --display auto|:N      private X display (default: first free from :20)
  --desktop-target TARGET
                         shared GNOME desktop: auto, xrdp, physical, or :N
                         (default: auto; explicit targets never fall back)
  --desktop-relay rdp|vnc
                         private-canvas relay; use vnc only for an X11/XRDP
                         desktop when nested GNOME RDP renders blank
  --vnc-grab-keyboard off|on
                         grab the dedicated private VNC relay keyboard so
                         Shift/Ctrl survive nested input (default: on)
  --grd-fd-restart-threshold N
                         restart before GNOME RDP exhausts descriptors
                         (default: 4096; 0 disables the guard)
  --text-key-delay-ms N  pace relayed phone text by 0-50 ms per character
                         (new install: 8; v0.1.0 upgrade: preserve 0)
  --physical-key-delay-ms N
                         pace physical key batches by 0-50 ms
                         (default: 0)
  --keyboard-route rdp|x11|auto
                         route physical keys through the compatible RDP path,
                         directly into an X11 desktop, or auto-detect X11
                         (default: rdp; x11 is opt-in)
  --phone-text-mode auto|keys|clipboard
                         keep representable phone text on fast key events and
                         paste newline/CJK as semantic clipboard text (auto),
                         or force one route (default: auto)
  --network-interface all|default|IFACE
                         use all adapters (the default), Ubuntu's preferred
                         route, or one named interface
  --cursor-guard off|on  opt into the process-local UU cursor workaround
                         (default: off)
  --cursor-size auto|N   with the cursor guard on, match the desktop cursor or
                         use a fixed size from 24 through 128 pixels
  --console-vnc-port N   localhost VNC sidecar port (default: 5920)
  --console-web-port N   localhost noVNC app port (default: 6080)
  --skip-packages        do not install Ubuntu/Wine package dependencies
  --skip-account-login   do not open UU for first-time account sign-in
  --unattended           enable TPM-backed startup after an automatic login
  --automatic-updates    enable daily checks and resumable Codex repair
  --upgrade-existing     run an audited installer over the existing UU prefix
                         before applying its approved release manifest
  --prefix-only          prepare only the selected Wine prefix; do not change
                         RDP, user services, launchers, or account login
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
        --rdp-port)
            rdp_port="${2:?--rdp-port requires a port}"
            shift 2
            ;;
        --resolution)
            resolution="${2:?--resolution requires WIDTHxHEIGHT}"
            shift 2
            ;;
        --follow-desktop-resolution)
            follow_desktop_resolution="${2:?--follow-desktop-resolution requires off or on}"
            shift 2
            ;;
        --display)
            bridge_display="${2:?--display requires auto or :N}"
            shift 2
            ;;
        --desktop-target)
            desktop_target="${2:?--desktop-target requires auto, xrdp, physical, or :N}"
            shift 2
            ;;
        --desktop-relay)
            desktop_relay="${2:?--desktop-relay requires rdp or vnc}"
            shift 2
            ;;
        --vnc-grab-keyboard)
            vnc_grab_keyboard="${2:?--vnc-grab-keyboard requires off or on}"
            shift 2
            ;;
        --grd-fd-restart-threshold)
            grd_fd_restart_threshold="${2:?--grd-fd-restart-threshold requires a number}"
            shift 2
            ;;
        --text-key-delay-ms)
            text_key_delay_ms="${2:?--text-key-delay-ms requires a number}"
            shift 2
            ;;
        --physical-key-delay-ms)
            physical_key_delay_ms="${2:?--physical-key-delay-ms requires a number}"
            shift 2
            ;;
        --keyboard-route)
            keyboard_route="${2:?--keyboard-route requires rdp, x11, or auto}"
            shift 2
            ;;
        --phone-text-mode)
            phone_text_mode="${2:?--phone-text-mode requires auto, keys, or clipboard}"
            shift 2
            ;;
        --network-interface)
            network_interface="${2:?--network-interface requires all, default, or an interface name}"
            shift 2
            ;;
        --cursor-guard)
            cursor_guard="${2:?--cursor-guard requires off or on}"
            shift 2
            ;;
        --cursor-size)
            cursor_size="${2:?--cursor-size requires auto or a pixel size}"
            shift 2
            ;;
        --console-vnc-port)
            console_vnc_port="${2:?--console-vnc-port requires a port}"
            shift 2
            ;;
        --console-web-port)
            console_web_port="${2:?--console-web-port requires a port}"
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
        --unattended)
            unattended=true
            shift
            ;;
        --automatic-updates)
            automatic_updates=true
            shift
            ;;
        --upgrade-existing)
            upgrade_existing=true
            shift
            ;;
        --prefix-only)
            prefix_only=true
            start_service=false
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
if [[ ! -r /etc/os-release ]]; then
    printf 'Cannot identify this operating system.\n' >&2
    exit 1
fi
# shellcheck source=/dev/null
source /etc/os-release
if [[ "${ID:-}" != ubuntu || "${VERSION_ID:-}" != 24.04 ]]; then
    printf 'Only Ubuntu 24.04 is currently supported; detected %s %s.\n' \
        "${ID:-unknown}" "${VERSION_ID:-unknown}" >&2
    exit 1
fi
if [[ ! "$rdp_port" =~ ^[1-9][0-9]{0,4}$ ]] ||
   ((rdp_port < 1024 || rdp_port > 65535)); then
    printf 'The RDP port must be an integer from 1024 through 65535.\n' >&2
    exit 2
fi
if [[ ! "$resolution" =~ ^[1-9][0-9]{2,4}x[1-9][0-9]{2,4}$ ]]; then
    printf 'The resolution must use WIDTHxHEIGHT, for example 1920x1080.\n' >&2
    exit 2
fi
resolution_width="${resolution%x*}"
resolution_height="${resolution#*x}"
if ((resolution_width < 640 || resolution_width > 16384 ||
     resolution_height < 480 || resolution_height > 16384)); then
    printf 'The resolution must be between 640x480 and 16384x16384.\n' >&2
    exit 2
fi
if [[ "$follow_desktop_resolution" != off &&
      "$follow_desktop_resolution" != on ]]; then
    printf 'Desktop-resolution following must be off or on.\n' >&2
    exit 2
fi
if [[ "$bridge_display" != auto &&
      ! "$bridge_display" =~ ^:(0|[1-9][0-9]{0,2})$ ]]; then
    printf 'The private display must be auto or an X display such as :20.\n' >&2
    exit 2
fi
if [[ "$desktop_target" != auto &&
      "$desktop_target" != xrdp &&
      "$desktop_target" != physical &&
      ! "$desktop_target" =~ ^:(0|[1-9][0-9]{0,2})(\.0)?$ ]]; then
    printf 'The desktop target must be auto, xrdp, physical, or an X display such as :11.\n' >&2
    exit 2
fi
if [[ "$desktop_relay" != rdp && "$desktop_relay" != vnc ]]; then
    printf 'The desktop relay must be rdp or vnc.\n' >&2
    exit 2
fi
if [[ "$vnc_grab_keyboard" != off && "$vnc_grab_keyboard" != on ]]; then
    printf 'VNC keyboard grabbing must be off or on.\n' >&2
    exit 2
fi
if [[ ! "$grd_fd_restart_threshold" =~ ^[0-9]+$ ]] ||
   ((grd_fd_restart_threshold != 0 &&
     (grd_fd_restart_threshold < 512 ||
      grd_fd_restart_threshold > 60000))); then
    printf 'The GNOME RDP descriptor threshold must be 0 or 512 through 60000.\n' >&2
    exit 2
fi
if [[ ! "$text_key_delay_ms" =~ ^[0-9]+$ ]] ||
   ((text_key_delay_ms > 50)); then
    printf 'The text-key delay must be an integer from 0 through 50 ms.\n' >&2
    exit 2
fi
if [[ ! "$physical_key_delay_ms" =~ ^[0-9]+$ ]] ||
   ((physical_key_delay_ms > 50)); then
    printf 'The physical-key delay must be an integer from 0 through 50 ms.\n' >&2
    exit 2
fi
if [[ "$keyboard_route" != rdp && "$keyboard_route" != x11 &&
      "$keyboard_route" != auto ]]; then
    printf 'The keyboard route must be rdp, x11, or auto.\n' >&2
    exit 2
fi
if [[ "$phone_text_mode" != auto && "$phone_text_mode" != keys &&
      "$phone_text_mode" != clipboard ]]; then
    printf 'The phone-text mode must be auto, keys, or clipboard.\n' >&2
    exit 2
fi
if [[ "$network_interface" != all &&
      "$network_interface" != default &&
      ! "$network_interface" =~ ^[a-zA-Z0-9_.:-]{1,15}$ ]]; then
    printf 'The UU network interface must be all, default, or a Linux interface name.\n' >&2
    exit 2
fi
if [[ "$network_interface" != all &&
      "$network_interface" != default &&
      ! -d "/sys/class/net/$network_interface" ]]; then
    printf 'The requested UU network interface does not exist: %s\n' \
        "$network_interface" >&2
    exit 2
fi
if [[ "$cursor_guard" != off && "$cursor_guard" != on ]]; then
    printf 'The cursor guard must be off or on.\n' >&2
    exit 2
fi
if [[ "$cursor_size" != auto ]]; then
    if [[ ! "$cursor_size" =~ ^[0-9]{1,3}$ ]]; then
        printf 'The cursor size must be auto or an integer from 24 through 128.\n' >&2
        exit 2
    fi
    cursor_size=$((10#$cursor_size))
    if ((cursor_size < 24 || cursor_size > 128)); then
        printf 'The cursor size must be auto or an integer from 24 through 128.\n' >&2
        exit 2
    fi
fi
if [[ ! "$console_vnc_port" =~ ^[1-9][0-9]{3,4}$ ||
      ! "$console_web_port" =~ ^[1-9][0-9]{3,4}$ ]]; then
    printf 'The UU console ports must be integers from 1024 through 65535.\n' >&2
    exit 2
fi
console_vnc_port=$((10#$console_vnc_port))
console_web_port=$((10#$console_web_port))
if ((console_vnc_port < 1024 || console_vnc_port > 65535 ||
     console_web_port < 1024 || console_web_port > 65535)) ||
   ((console_vnc_port == console_web_port)); then
    printf 'The UU console ports must be distinct values from 1024 through 65535.\n' \
        >&2
    exit 2
fi
if [[ "$upgrade_existing" == true && -z "$uu_installer" ]]; then
    printf -- '--upgrade-existing requires --uu-installer with an audited file.\n' >&2
    exit 2
fi
if [[ "$upgrade_existing" == true &&
      ! -f "$uu_dir/GameViewer.exe" ]]; then
    printf -- '--upgrade-existing requires an existing UU installation in %s.\n' \
        "$wine_prefix" >&2
    exit 2
fi
if [[ "$prefix_only" == true &&
      ("$unattended" == true || "$automatic_updates" == true) ]]; then
    printf -- '--prefix-only cannot configure unattended or automatic updates.\n' >&2
    exit 2
fi
if [[ "$prefix_only" == false ]]; then
    user_bus="${XDG_RUNTIME_DIR:-/run/user/$UID}/bus"
    if [[ ! -S "$user_bus" ]]; then
        printf 'The systemd user bus is unavailable at %s.\n' "$user_bus" >&2
        printf 'Log into the target GNOME desktop as this user, then rerun.\n' >&2
        exit 1
    fi
fi
if [[ "$unattended" == true && "$start_service" == false ]]; then
    printf -- '--unattended cannot be combined with --no-start.\n' >&2
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
        acl aria2 binutils ca-certificates cmake crudini curl freerdp3-x11 \
        gcc \
        gcc-mingw-w64-x86-64 \
        git gnome-remote-desktop iproute2 jq libsecret-tools libx11-6 \
        libxml2-utils libxtst6 meson novnc \
        ninja-build openbox openssl p7zip-full patch python3 python3-attr \
        python3-gi python3-jinja2 tar tigervnc-viewer websockify \
        x11-utils x11vnc xauth xclip \
        xdotool xvfb zstd
    install_winehq
}

stop_wine_prefix() {
    "$repo_dir/scripts/stop-wine-prefix" "$wine_prefix" "$wineserver_bin"
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

for command in curl meson ninja patch readelf sha256sum /usr/bin/systemctl \
    timeout \
    "$grdctl_bin" "$openssl_bin" "$python_bin" "$secret_tool_bin" \
    "$wine_bin" "$wineserver_bin" /usr/bin/Xvfb /usr/bin/gsettings \
    /usr/bin/awk /usr/bin/ip /usr/bin/mcookie /usr/bin/openbox \
    /usr/bin/script /usr/bin/sort /usr/bin/ss /usr/bin/xauth \
    /usr/bin/vncviewer /usr/bin/websockify /usr/bin/x11vnc /usr/bin/xclip \
    /usr/bin/xdotool \
    /usr/libexec/gnome-remote-desktop-daemon; do
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
release_version="$(manifest_field version)"
server_exe="$uu_bin/$(manifest_field server.filename)"
healthd_exe="$uu_bin/$(manifest_field health_monitor.filename)"
healthd_sha256="$(manifest_field health_monitor.original_sha256)"
devcon_exe="$uu_bin/drivers/devcon.exe"
devcon_backup="$devcon_exe.uu-original"
case "$release_version" in
    4.33.0.8907|4.34.0.8979)
        devcon_sha256='46731d6ea59dd9b63ad641c79646bb5ff64e1b877a1226536e3fe34d1ab4ee10'
        ;;
    *)
        printf 'No audited devcon.exe identity exists for UU %s.\n' \
            "$release_version" >&2
        exit 1
        ;;
esac

export WINEPREFIX="$wine_prefix"
export WINEDEBUG=-all
export WINEDLLOVERRIDES='winedbg.exe=d;mscoree,mshtml='

bridge_was_active=false
if [[ "$prefix_only" == false ]] &&
   "${systemctl_user[@]}" is-active --quiet uu-remote-bridge.service; then
    bridge_was_active=true
fi
restore_bridge_after_failure() {
    local status=$?

    if ((status != 0)) && [[ "$bridge_was_active" == true ]]; then
        "${systemctl_user[@]}" start uu-remote-bridge.service \
            >/dev/null 2>&1 || true
    fi
}
trap restore_bridge_after_failure EXIT

if [[ "$prefix_only" == false ]]; then
    port_listener="$(/usr/bin/ss -H -ltnp "sport = :$rdp_port" 2>/dev/null || true)"
    if [[ -n "$port_listener" ]] &&
       ! /usr/bin/grep -q 'gnome-remote-de' <<<"$port_listener"; then
        printf 'RDP port %s is already owned by another process:\n%s\n' \
            "$rdp_port" "$port_listener" >&2
        exit 1
    fi
    "${systemctl_user[@]}" stop uu-remote-bridge.service >/dev/null 2>&1 || true
fi
stop_wine_prefix

if [[ "$prefix_only" == false && "$bridge_display" != auto ]]; then
    display_number="${bridge_display#:}"
    if [[ -e "/tmp/.X11-unix/X$display_number" ||
          -e "/tmp/.X${display_number}-lock" ]]; then
        printf 'Private X display %s is already in use; use --display auto.\n' \
            "$bridge_display" >&2
        exit 1
    fi
fi

if [[ ! -f "$uu_dir/GameViewer.exe" || "$upgrade_existing" == true ]]; then
    if [[ ! -f "$uu_dir/GameViewer.exe" ]]; then
        fresh_install=true
    fi
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
    if [[ "$fresh_install" == true ]]; then
        "$wine_bin" wineboot -u
        "$wine_bin" winecfg -v win10
    else
        if [[ ! -f "$installed_manifest" ]]; then
            printf 'Cannot upgrade without the currently installed release manifest.\n' >&2
            exit 1
        fi
        previous_version="$(
            "$python_bin" "$repo_dir/scripts/patch-gameviewer.py" field version \
                --manifest "$installed_manifest"
        )"
        previous_server_filename="$(
            "$python_bin" "$repo_dir/scripts/patch-gameviewer.py" field \
                server.filename --manifest "$installed_manifest"
        )"
        previous_healthd_filename="$(
            "$python_bin" "$repo_dir/scripts/patch-gameviewer.py" field \
                health_monitor.filename --manifest "$installed_manifest"
        )"
        previous_backup_dir="$wine_prefix/compat/release-backups/$previous_version"
        mkdir -p "$previous_backup_dir"
        install -m 0600 "$installed_manifest" \
            "$previous_backup_dir/release-manifest.json"
        for previous_backup in \
            "$uu_bin/$previous_server_filename.uu-original" \
            "$uu_bin/$previous_healthd_filename.uu-original"; do
            if [[ -f "$previous_backup" ]]; then
                install -m 0600 "$previous_backup" \
                    "$previous_backup_dir/${previous_backup##*/}"
                rm -f "$previous_backup"
            fi
        done
    fi
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
"$repo_dir/scripts/build-libei.sh" "$libei_build"

mkdir -p "$wine_prefix/compat" "$freerdp_install" "$libei_install"
if [[ -e "$terminal_proxy_install" ]] &&
   { [[ ! -f "$installed_terminal_proxy" ]] ||
     ! /usr/bin/cmp -s "$terminal_proxy_install" \
        "$installed_terminal_proxy"; }; then
    printf 'Refusing to replace an unknown GameViewer bin/powershell.exe.\n' >&2
    exit 1
fi
install -m 0644 "$release_manifest" "$installed_manifest"
install -m 0755 \
    "$compat_build/uu-cursor-guard.dll" \
    "$compat_build/uu-input-bridge.dll" \
    "$compat_build/uu-input-broker.exe" \
    "$compat_build/uu-injector.exe" \
    "$compat_build/uu-service-control.exe" \
    "$compat_build/uu-terminal-proxy.exe" \
    "$wine_prefix/compat/"
install -m 0755 "$compat_build/uu-network-filter.so" \
    "$wine_prefix/compat/uu-network-filter.so"
install -m 0755 "$compat_build/uu-x11-input" \
    "$wine_prefix/compat/uu-x11-input"
install -m 0755 "$compat_build/uu-terminal-bridge" \
    "$wine_prefix/compat/uu-terminal-bridge"
install -m 0644 "$compat_build/uu-terminal.inputrc" \
    "$wine_prefix/compat/uu-terminal.inputrc"
install -m 0755 "$compat_build/uu-terminal-proxy.exe" \
    "$terminal_proxy_install"
install -m 0755 "$compat_build/winlogon.exe" \
    "$wine_prefix/compat/winlogon.exe"
install -m 0755 "$compat_build/winlogon.exe.so" \
    "$wine_prefix/compat/winlogon.exe.so"
install -m 0755 "$freerdp_build/"*.dll "$freerdp_build/sdl-freerdp.exe" \
    "$freerdp_install/"
install -m 0755 "$compat_build/winpr-sspi-shim.dll" \
    "$freerdp_install/winpr-sspi-shim.dll"
install -m 0755 "$libei_build/libei.so.1.2.1" \
    "$libei_install/libei.so.1.2.1"
ln -sfn libei.so.1.2.1 "$libei_install/libei.so.1"
mkdir -p "$freerdp_install/ossl-modules"
install -m 0755 "$freerdp_build/ossl-modules/legacy.dll" \
    "$freerdp_install/ossl-modules/legacy.dll"
runtime_digest_tmp="$(mktemp "$wine_prefix/compat/.runtime-source-sha256.XXXXXX")"
"$repo_dir/scripts/runtime-source-digest" >"$runtime_digest_tmp"
chmod 0644 "$runtime_digest_tmp"
mv "$runtime_digest_tmp" "$runtime_digest_file"

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

if [[ -f "$devcon_exe" ]]; then
    if [[ "$(sha256sum "$devcon_exe" | awk '{print $1}')" != \
          "$devcon_sha256" ]]; then
        printf 'Refusing to suppress an unknown devcon.exe build.\n' >&2
        exit 1
    fi
    if [[ -f "$devcon_backup" ]]; then
        if [[ "$(sha256sum "$devcon_backup" | awk '{print $1}')" != \
              "$devcon_sha256" ]]; then
            printf 'Refusing to use an unknown devcon.exe backup.\n' >&2
            exit 1
        fi
        rm -f "$devcon_exe"
    else
        mv "$devcon_exe" "$devcon_backup"
    fi
elif [[ ! -f "$devcon_backup" ]] || \
     [[ "$(sha256sum "$devcon_backup" | awk '{print $1}')" != \
        "$devcon_sha256" ]]; then
    printf 'The suppressed devcon.exe has no audited backup.\n' >&2
    exit 1
fi

"$python_bin" "$repo_dir/scripts/patch-gameviewer.py" patch "$server_exe" \
    --manifest "$installed_manifest"
"$repo_dir/scripts/clean-wine-device-registry" "$wine_prefix"

if [[ "$prefix_only" == true ]]; then
    printf '\nPrepared approved UU release in %s without changing RDP configuration or opening the login UI.\n' \
        "$wine_prefix"
    exit 0
fi

install -d -m 0755 \
    "$HOME/.local/bin" "$HOME/.local/libexec" \
    "$HOME/.config/systemd/user" "$HOME/.local/share/applications"
install -d -m 0700 "$config_dir"
environment_tmp="$(mktemp "$config_dir/.environment.XXXXXX")"
printf 'UURB_RDP_PORT=%s\n' "$rdp_port" >"$environment_tmp"
printf 'UURB_RESOLUTION=%s\n' "$resolution" >>"$environment_tmp"
printf 'UURB_FOLLOW_DESKTOP_RESOLUTION=%s\n' \
    "$follow_desktop_resolution" >>"$environment_tmp"
printf 'UURB_DISPLAY=%s\n' "$bridge_display" >>"$environment_tmp"
printf 'UURB_DESKTOP_TARGET=%s\n' "$desktop_target" >>"$environment_tmp"
printf 'UURB_DESKTOP_RELAY=%s\n' "$desktop_relay" >>"$environment_tmp"
printf 'UURB_VNC_GRAB_KEYBOARD=%s\n' \
    "$vnc_grab_keyboard" >>"$environment_tmp"
printf 'UURB_GRD_FD_RESTART_THRESHOLD=%s\n' \
    "$grd_fd_restart_threshold" >>"$environment_tmp"
printf 'UURB_TEXT_KEY_DELAY_MS=%s\n' \
    "$text_key_delay_ms" >>"$environment_tmp"
printf 'UURB_PHYSICAL_KEY_DELAY_MS=%s\n' \
    "$physical_key_delay_ms" >>"$environment_tmp"
printf 'UURB_KEYBOARD_ROUTE=%s\n' \
    "$keyboard_route" >>"$environment_tmp"
printf 'UURB_PHONE_TEXT_MODE=%s\n' \
    "$phone_text_mode" >>"$environment_tmp"
printf 'UURB_NETWORK_INTERFACE=%s\n' \
    "$network_interface" >>"$environment_tmp"
printf 'UURB_CURSOR_GUARD=%s\n' \
    "$cursor_guard" >>"$environment_tmp"
printf 'UURB_CURSOR_SIZE=%s\n' \
    "$cursor_size" >>"$environment_tmp"
printf 'UURB_CONSOLE_VNC_PORT=%s\n' \
    "$console_vnc_port" >>"$environment_tmp"
printf 'UURB_CONSOLE_WEB_PORT=%s\n' \
    "$console_web_port" >>"$environment_tmp"
chmod 0600 "$environment_tmp"
mv "$environment_tmp" "$environment_file"
install -m 0755 "$repo_dir/scripts/uu-remote-bridge" \
    "$HOME/.local/bin/uu-remote-bridge"
install -m 0755 "$repo_dir/scripts/uu-remote" "$HOME/.local/bin/uu-remote"
install -m 0755 "$repo_dir/scripts/uu-remote-console" \
    "$HOME/.local/bin/uu-remote-console"
install -m 0755 "$repo_dir/scripts/uu-agent" "$HOME/.local/bin/uu-agent"
install -m 0755 "$repo_dir/scripts/upgrade-uu-remote.sh" \
    "$HOME/.local/bin/uu-remote-upgrade"
install -m 0755 "$repo_dir/scripts/stop-wine-prefix" \
    "$HOME/.local/libexec/uu-remote-stop-wine-prefix"
install -m 0755 "$repo_dir/scripts/clean-wine-device-registry" \
    "$HOME/.local/libexec/uu-clean-wine-device-registry"
install -m 0755 "$repo_dir/scripts/inspect-wine-device-registry.py" \
    "$HOME/.local/libexec/uu-inspect-wine-device-registry.py"
install -m 0755 "$repo_dir/scripts/uu_connection_status.py" \
    "$HOME/.local/libexec/uu-connection-status"
install -m 0755 "$repo_dir/scripts/uu-keyring-unlock.py" \
    "$HOME/.local/bin/uu-keyring-unlock"
install -m 0644 "$repo_dir/systemd/uu-remote-bridge.service" \
    "$HOME/.config/systemd/user/uu-remote-bridge.service"
install -m 0644 "$repo_dir/systemd/uu-remote-console.service" \
    "$HOME/.config/systemd/user/uu-remote-console.service"
install -m 0644 "$repo_dir/systemd/uu-keyring-unlock.service" \
    "$HOME/.config/systemd/user/uu-keyring-unlock.service"

desktop_entry="$HOME/.local/share/applications/uu-remote.desktop"
"$python_bin" - "$repo_dir/desktop/uu-remote.desktop.in" \
    "$desktop_entry" "$HOME/.local/bin/uu-remote" <<'PY'
import sys
from pathlib import Path

template, destination, executable = map(Path, sys.argv[1:])
escaped = str(executable).replace("\\", "\\\\").replace(" ", "\\ ")
rendered = template.read_text(encoding="ascii").replace(
    "@EXEC@", f"{escaped} open"
)
destination.write_text(rendered, encoding="ascii")
PY
chmod 0644 "$desktop_entry"
if [[ -d "$HOME/Desktop" ]]; then
    desktop_shortcut="$HOME/Desktop/UU Remote.desktop"
    install -m 0755 "$desktop_entry" "$desktop_shortcut"
    if command -v gio >/dev/null 2>&1; then
        gio set "$desktop_shortcut" metadata::trusted true \
            >/dev/null 2>&1 || true
    fi
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$HOME/.local/share/applications" \
        >/dev/null 2>&1 || true
fi

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
relay_vnc_auth_file="$config_dir/relay-vnc.pass"
relay_vnc_auth_temporary="$(mktemp "$config_dir/relay-vnc.pass.XXXXXX")"
relay_vnc_password="$(LC_ALL=C printf '%.8s' "$rdp_password")"
printf -v relay_vnc_auth_quoted '%q' "$relay_vnc_auth_temporary"
if ! printf '%s\n%s\ny\n' "$relay_vnc_password" "$relay_vnc_password" |
    /usr/bin/script -qefc \
        "/usr/bin/x11vnc -storepasswd $relay_vnc_auth_quoted" /dev/null \
        >/dev/null 2>&1; then
    rm -f "$relay_vnc_auth_temporary"
    printf 'Could not create the loopback VNC credential.\n' >&2
    exit 1
fi
chmod 0600 "$relay_vnc_auth_temporary"
mv -f "$relay_vnc_auth_temporary" "$relay_vnc_auth_file"
unset relay_vnc_auth_quoted
unset relay_vnc_password
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

if [[ "$unattended" == true ]]; then
    "$repo_dir/scripts/configure-unattended.sh" enable
fi

if [[ "$automatic_updates" == true ]]; then
    "$repo_dir/scripts/configure-updater.sh" enable --repo "$repo_dir"
fi

printf '\nInstalled UU Remote Ubuntu bridge.\n'
printf 'Service: systemctl --user status uu-remote-bridge.service\n'
printf 'App:     open "UU Remote" or run uu-remote open\n'
printf 'Console: http://127.0.0.1:%s/vnc.html\n' "$console_web_port"
printf 'Logs:    uu-remote logs\n'
