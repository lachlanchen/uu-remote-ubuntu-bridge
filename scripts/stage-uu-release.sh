#!/usr/bin/env bash

set -Eeuo pipefail
umask 077

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
installer=''
output=''
sandbox_install=false
keep_workdir=false
staging_method='archive-extraction'

usage() {
    cat <<'EOF'
usage: scripts/stage-uu-release.sh --installer PATH [options]

Extract a UU installer without executing it and stage the server binaries for
scripts/audit-gameviewer.py. Output defaults to build/upstream/SHA256_PREFIX.

  --output DIR          select the private staging directory
  --sandbox-install     if archive extraction fails, execute the installer in
                        a root-managed, networkless systemd/Wine sandbox
  --keep-workdir        retain extracted files and the disposable Wine prefix
EOF
}

while (($#)); do
    case "$1" in
        --installer)
            installer="${2:?--installer requires a path}"
            shift 2
            ;;
        --output)
            output="${2:?--output requires a path}"
            shift 2
            ;;
        --sandbox-install)
            sandbox_install=true
            shift
            ;;
        --keep-workdir)
            keep_workdir=true
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

if [[ -z "$installer" ]]; then
    usage >&2
    exit 2
fi
for command in 7z find sha256sum; do
    if ! command -v "$command" >/dev/null 2>&1; then
        printf 'missing required command: %s\n' "$command" >&2
        exit 1
    fi
done

installer="$(realpath "$installer")"
installer_sha256="$(sha256sum "$installer" | awk '{print $1}')"
if [[ -z "$output" ]]; then
    output="$repo_dir/build/upstream/${installer_sha256:0:12}"
else
    output="$(realpath -m "$output")"
fi
if [[ -e "$output" && ! -d "$output" ]]; then
    printf 'output path is not a directory: %s\n' "$output" >&2
    exit 1
fi
if [[ -d "$output" ]] && [[ -n "$(find "$output" -mindepth 1 -print -quit)" ]]; then
    printf 'output directory is not empty: %s\n' "$output" >&2
    exit 1
fi

extract_dir="$output/extracted"
mkdir -p "$extract_dir"
chmod 0700 "$output" "$extract_dir"
if ! 7z x -y "-o$extract_dir" "$installer" >"$output/7z.log"; then
    printf 'Archive extraction failed; checking the explicit sandbox policy.\n' >&2
fi

mapfile -d '' server_candidates < <(
    find "$extract_dir" -type f -iname 'GameViewerServer.exe' -print0
)
mapfile -d '' healthd_candidates < <(
    find "$extract_dir" -type f -iname 'GameViewerHealthd.exe' -print0
)
if ((${#server_candidates[@]} != 1 || ${#healthd_candidates[@]} != 1)) && \
   [[ "$sandbox_install" == false ]]; then
    printf 'Expected one server and one health monitor; found %s and %s.\n' \
        "${#server_candidates[@]}" "${#healthd_candidates[@]}" >&2
    if [[ "$keep_workdir" == true ]]; then
        printf 'The installer was not executed. Inspect %s or use a new output directory with --sandbox-install.\n' \
            "$extract_dir" >&2
    else
        rm -rf "$output"
        printf 'The failed extraction was removed. Rerun with --sandbox-install or stage in an isolated VM.\n' >&2
    fi
    exit 1
fi

if ((${#server_candidates[@]} != 1 || ${#healthd_candidates[@]} != 1)); then
    for command in sudo systemd-run timeout /opt/wine-stable/bin/wine \
        /opt/wine-stable/bin/wineserver; do
        if ! command -v "$command" >/dev/null 2>&1; then
            printf 'missing sandbox command: %s\n' "$command" >&2
            exit 1
        fi
    done

    sandbox_home="$output/sandbox-home"
    sandbox_prefix="$output/wine-prefix"
    sandbox_runtime="$output/sandbox-runtime"
    mkdir -p "$sandbox_home" "$sandbox_prefix" "$sandbox_runtime"
    chmod 0700 "$sandbox_home" "$sandbox_prefix" "$sandbox_runtime"

    printf 'Archive extraction had no payload. Sudo is needed for a locked-down transient sandbox.\n'
    sudo -v
    sudo systemd-run --wait --pipe --collect --quiet \
        --uid="$UID" \
        --gid="$(id -g)" \
        --working-directory=/work \
        --property=ProtectSystem=strict \
        --property=ProtectHome=tmpfs \
        --property=PrivateTmp=yes \
        --property=PrivateDevices=yes \
        --property=PrivateNetwork=yes \
        --property=IPAddressDeny=any \
        --property='RestrictAddressFamilies=AF_UNIX AF_NETLINK' \
        --property=NoNewPrivileges=yes \
        --property=ProtectKernelTunables=yes \
        --property=ProtectKernelModules=yes \
        --property=ProtectKernelLogs=yes \
        --property=ProtectControlGroups=yes \
        --property=ProtectClock=yes \
        --property=ProtectHostname=yes \
        --property=LockPersonality=yes \
        --property=RemoveIPC=yes \
        --property=UMask=0077 \
        --property="BindPaths=$output:/work" \
        --property="BindReadOnlyPaths=$installer:/input/uu-installer.exe" \
        --setenv=HOME=/work/sandbox-home \
        --setenv=WINEPREFIX=/work/wine-prefix \
        --setenv=WINEDEBUG=-all \
        --setenv=WINEDLLOVERRIDES='winedbg.exe=d' \
        --setenv=XDG_RUNTIME_DIR=/work/sandbox-runtime \
        --setenv=DISPLAY= \
        /bin/bash -c '
            set -Eeuo pipefail
            cleanup() {
                /opt/wine-stable/bin/wineserver -k || true
                /opt/wine-stable/bin/wineserver -w || true
            }
            trap cleanup EXIT
            /opt/wine-stable/bin/wine wineboot -u
            /usr/bin/timeout --kill-after=10s 180s \
                /opt/wine-stable/bin/wine /input/uu-installer.exe /S
            sleep 2
        ' >"$output/sandbox-install.log" 2>&1
    staging_method='systemd-sandbox'

    mapfile -d '' server_candidates < <(
        find "$sandbox_prefix" -type f -iname 'GameViewerServer.exe' -print0
    )
    mapfile -d '' healthd_candidates < <(
        find "$sandbox_prefix" -type f -iname 'GameViewerHealthd.exe' -print0
    )
    if ((${#server_candidates[@]} != 1 || ${#healthd_candidates[@]} != 1)); then
        printf 'Sandbox install produced %s server and %s health-monitor candidates.\n' \
            "${#server_candidates[@]}" "${#healthd_candidates[@]}" >&2
        printf 'Inspect %s without using it as an approved release.\n' "$output" >&2
        exit 1
    fi
fi

install -m 0600 "${server_candidates[0]}" "$output/GameViewerServer.exe"
install -m 0600 "${healthd_candidates[0]}" "$output/GameViewerHealthd.exe"
server_sha256="$(sha256sum "$output/GameViewerServer.exe" | awk '{print $1}')"
healthd_sha256="$(sha256sum "$output/GameViewerHealthd.exe" | awk '{print $1}')"

printf '%s\n' \
    "installer=$installer" \
    "installer_sha256=$installer_sha256" \
    "server_sha256=$server_sha256" \
    "healthd_sha256=$healthd_sha256" \
    "staging_method=$staging_method" \
    >"$output/SHA256"
chmod 0600 "$output/SHA256" "$output/7z.log"

if [[ "$keep_workdir" == false ]]; then
    rm -rf "$extract_dir" \
        "$output/sandbox-home" \
        "$output/sandbox-runtime" \
        "$output/wine-prefix"
fi

printf 'staged server: %s\n' "$output/GameViewerServer.exe"
printf 'staged health monitor: %s\n' "$output/GameViewerHealthd.exe"
printf 'hash record: %s\n' "$output/SHA256"
if [[ "$staging_method" == systemd-sandbox ]]; then
    printf 'The installer executed only inside the locked-down transient sandbox.\n'
else
    printf 'The installer was extracted but never executed.\n'
fi
