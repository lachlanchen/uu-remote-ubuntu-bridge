#!/usr/bin/env bash

set -Eeuo pipefail
umask 077

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
config_dir="$HOME/.config/uu-remote-bridge"
config_file="$config_dir/updater.json"
state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/uu-remote-updater"
unit_dir="$HOME/.config/systemd/user"
updater_libexec="$HOME/.local/libexec/uu-remote-updater"
model='codex-auto-review'
reasoning_effort='medium'
codex_executable=''
track=''
branch='main'
idle_minutes=45
auto_reinstall=false
auto_promote=false
command="${1:-status}"
[[ $# -eq 0 ]] || shift

usage() {
    cat <<'EOF'
usage: scripts/configure-updater.sh enable [options]
       scripts/configure-updater.sh disable [--purge-state]
       scripts/configure-updater.sh status

Enable options:
  --repo PATH            source repository used for audits and recovery
  --track TAG            known-good behavior track to reinstall on failure
  --branch NAME          repair base branch (default: main)
  --model MODEL          Codex model (default: codex-auto-review)
  --reasoning-effort EFFORT
                         Codex reasoning effort (default: medium)
  --codex PATH           absolute Codex executable (default: current command)
  --idle-minutes N       documented maintenance idle window (default: 45)
  --auto-reinstall       opt in to live recovery: restart the bridge after two
                         confirmed failures, then reinstall the known-good
                         track if restart fails (default: disabled)
  --no-auto-reinstall    retain the safe default; accepted for compatibility
  --auto-promote-accepted
                         promote only a newer exact-hash release carrying a
                         complete maintainer acceptance record; snapshot and
                         roll back the Wine prefix on any failure
  --no-auto-promote      retain the safe promotion default (disabled)
EOF
}

purge_state=false
while (($#)); do
    case "$1" in
        --repo)
            repo_dir="$(realpath "${2:?--repo requires a path}")"
            shift 2
            ;;
        --track)
            track="${2:?--track requires a tag}"
            shift 2
            ;;
        --branch)
            branch="${2:?--branch requires a name}"
            shift 2
            ;;
        --model)
            model="${2:?--model requires a model identifier}"
            shift 2
            ;;
        --reasoning-effort)
            reasoning_effort="${2:?--reasoning-effort requires a value}"
            shift 2
            ;;
        --codex)
            codex_executable="${2:?--codex requires a path}"
            shift 2
            ;;
        --idle-minutes)
            idle_minutes="${2:?--idle-minutes requires a number}"
            shift 2
            ;;
        --no-auto-reinstall)
            auto_reinstall=false
            shift
            ;;
        --auto-reinstall)
            auto_reinstall=true
            shift
            ;;
        --no-auto-promote)
            auto_promote=false
            shift
            ;;
        --auto-promote-accepted)
            auto_promote=true
            shift
            ;;
        --purge-state)
            purge_state=true
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

systemctl_user=(
    /usr/bin/env
    "DBUS_SESSION_BUS_ADDRESS=unix:path=${XDG_RUNTIME_DIR:-/run/user/$UID}/bus"
    /usr/bin/systemctl --user
)

detect_track() {
    local route='rdp'
    local environment_file="$config_dir/environment"

    if [[ -f "$environment_file" ]]; then
        route="$(sed -n 's/^UURB_KEYBOARD_ROUTE=//p' "$environment_file" | tail -n 1)"
        route="${route:-rdp}"
    fi
    if [[ "$route" == x11 ]]; then
        printf 'track-direct-x11-20260724\n'
    else
        printf 'track-rdp-broker-20260724\n'
    fi
}

case "$command" in
    enable)
        if [[ ! -d "$repo_dir/.git" ]]; then
            printf 'UU updater repository is unavailable: %s\n' "$repo_dir" >&2
            exit 1
        fi
        for required in git python3 systemctl; do
            if ! command -v "$required" >/dev/null 2>&1; then
                printf 'missing updater dependency: %s\n' "$required" >&2
                exit 1
            fi
        done
        codex_executable="${codex_executable:-$(command -v codex || true)}"
        if [[ -z "$codex_executable" || "$codex_executable" != /* ||
              ! -x "$codex_executable" ]]; then
            printf 'missing executable Codex path; use --codex /absolute/path/to/codex\n' >&2
            exit 1
        fi
        if ! [[ "$idle_minutes" =~ ^[0-9]+$ ]] || ((idle_minutes < 5)); then
            printf -- '--idle-minutes must be at least 5.\n' >&2
            exit 2
        fi
        track="${track:-$(detect_track)}"
        git -C "$repo_dir" fetch --quiet --tags origin >/dev/null 2>&1 || true
        if ! git -C "$repo_dir" rev-parse --verify --quiet \
            "refs/tags/$track^{commit}" >/dev/null; then
            printf 'known-good track tag is unavailable: %s\n' "$track" >&2
            exit 1
        fi
        if ! "$codex_executable" login status 2>&1 | grep -q '^Logged in'; then
            printf 'Codex is not logged in for this user. Run codex login first.\n' >&2
            exit 1
        fi

        install -d -m 0700 "$config_dir" "$state_dir"
        install -d -m 0755 \
            "$HOME/.local/bin" "$unit_dir" "$updater_libexec/scripts"
        python3 - "$config_file" "$repo_dir" "$state_dir" "$branch" \
            "$track" "$model" "$reasoning_effort" "$idle_minutes" \
            "$auto_reinstall" "$auto_promote" "$codex_executable" <<'PY'
import json
import os
import sys
from pathlib import Path

(
    destination,
    repository,
    state_dir,
    branch,
    track,
    model,
    effort,
    idle_minutes,
    auto_reinstall,
    auto_promote,
    codex_executable,
) = sys.argv[1:]
value = {
    "schema_version": 1,
    "repository": str(Path(repository).resolve()),
    "state_dir": str(Path(state_dir).resolve()),
    "remote": "origin",
    "branch": branch,
    "track": track,
    "endpoint": "https://api.nrd.nie.163.com/api/v1/release/dl/1?channel=gwqd",
    "codex_model": model,
    "codex_reasoning_effort": effort,
    "codex_executable": codex_executable,
    "codex_timeout_seconds": 5400,
    "codex_max_used_percent": 20,
    "idle_minutes": int(idle_minutes),
    "auto_reinstall_known_good": auto_reinstall == "true",
    "auto_promote_accepted_release": auto_promote == "true",
    "max_download_bytes": 1073741824,
}
path = Path(destination)
temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
temporary.chmod(0o600)
temporary.replace(path)
PY
        install -m 0755 "$repo_dir/scripts/uu_update_manager.py" \
            "$HOME/.local/bin/uu-remote-update"
        install -m 0755 "$repo_dir/scripts/uu-remote" \
            "$HOME/.local/bin/uu-remote"
        install -m 0755 \
            "$repo_dir/scripts/promote-approved-release.py" \
            "$repo_dir/scripts/stop-wine-prefix" \
            "$updater_libexec/scripts/"
        install -m 0644 "$repo_dir/scripts/gameviewer_patchlib.py" \
            "$updater_libexec/scripts/gameviewer_patchlib.py"
        install -m 0644 "$repo_dir/systemd/uu-remote-update-check.service" \
            "$unit_dir/uu-remote-update-check.service"
        install -m 0644 "$repo_dir/systemd/uu-remote-update-check.timer" \
            "$unit_dir/uu-remote-update-check.timer"
        install -m 0644 "$repo_dir/systemd/uu-remote-repair-monitor.service" \
            "$unit_dir/uu-remote-repair-monitor.service"
        install -m 0644 "$repo_dir/systemd/uu-remote-repair-monitor.timer" \
            "$unit_dir/uu-remote-repair-monitor.timer"
        "${systemctl_user[@]}" daemon-reload
        "${systemctl_user[@]}" enable --now \
            uu-remote-update-check.timer \
            uu-remote-repair-monitor.timer
        "${systemctl_user[@]}" start --no-block uu-remote-update-check.service
        printf 'Enabled UU maintenance timers on track %s.\n' "$track"
        printf 'Status: uu-remote-update status\n'
        ;;
    disable)
        if [[ -f "$state_dir/promotion-in-progress.json" ]]; then
            printf 'Refusing to disable maintenance during a recoverable UU promotion.\n' >&2
            printf 'Run uu-remote update and wait for promotion recovery first.\n' >&2
            exit 1
        fi
        "${systemctl_user[@]}" disable --now \
            uu-remote-update-check.timer \
            uu-remote-repair-monitor.timer \
            uu-remote-update-check.service \
            uu-remote-repair-monitor.service >/dev/null 2>&1 || true
        rm -f \
            "$unit_dir/uu-remote-update-check.service" \
            "$unit_dir/uu-remote-update-check.timer" \
            "$unit_dir/uu-remote-repair-monitor.service" \
            "$unit_dir/uu-remote-repair-monitor.timer" \
            "$HOME/.local/bin/uu-remote-update"
        "${systemctl_user[@]}" daemon-reload
        if [[ "$purge_state" == true ]]; then
            rm -rf "$state_dir"
            rm -f "$config_file"
        fi
        printf 'Disabled UU maintenance timers.\n'
        ;;
    status)
        if [[ -x "$HOME/.local/bin/uu-remote-update" && -f "$config_file" ]]; then
            "$HOME/.local/bin/uu-remote-update" status
            printf '\nTimers:\n'
            "${systemctl_user[@]}" list-timers --all --no-pager \
                uu-remote-update-check.timer uu-remote-repair-monitor.timer
        else
            printf 'UU automatic maintenance is not enabled.\n'
        fi
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac
