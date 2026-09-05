#!/usr/bin/env bash

set -Eeuo pipefail
umask 077

original_arguments=("$@")
action="${1:-status}"
if (($#)); then
    shift
fi

pull_latest=true
promote_now=false
repo_override=''

usage() {
    cat <<'EOF'
usage: uu-remote-upgrade status [--repo PATH]
       uu-remote-upgrade check [--repo PATH] [--no-pull]
       uu-remote-upgrade apply [--repo PATH] [--no-pull] [--now]

Commands:
  status    show source, installed release, service, and updater state
  check     fast-forward a clean checkout, run tests, and check for an update
  apply     run the guarded product promotion, refresh the bridge runtime,
            preserve saved keyboard settings, and verify the result

Options:
  --repo PATH  use this repository checkout
  --no-pull    do not fetch or fast-forward the repository
  --now        explicitly bypass only the UU activity-idle delay; every hash,
               acceptance, login-preservation, snapshot, and rollback gate
               remains mandatory
EOF
}

while (($#)); do
    case "$1" in
        --repo)
            repo_override="${2:?--repo requires a path}"
            shift 2
            ;;
        --no-pull)
            pull_latest=false
            shift
            ;;
        --now)
            promote_now=true
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

case "$action" in
    status|check|apply)
        ;;
    -h|--help|help)
        usage
        exit 0
        ;;
    *)
        printf 'unknown command: %s\n' "$action" >&2
        usage >&2
        exit 2
        ;;
esac
if [[ "$action" != apply && "$promote_now" == true ]]; then
    printf -- '--now is valid only with apply.\n' >&2
    exit 2
fi
if [[ "$action" == status ]]; then
    pull_latest=false
fi

log() {
    printf '[uu-upgrade] %s\n' "$*"
}

fail() {
    printf '[uu-upgrade] ERROR: %s\n' "$*" >&2
    exit 1
}

config_file="$HOME/.config/uu-remote-bridge/updater.json"
discover_repository() {
    local candidate
    local script_root

    if [[ -n "$repo_override" ]]; then
        candidate="$repo_override"
    else
        script_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
        if [[ -d "$script_root/.git" ]]; then
            candidate="$script_root"
        elif [[ -f "$config_file" ]]; then
            candidate="$(
                /usr/bin/python3 - "$config_file" <<'PY'
import json
import sys
from pathlib import Path

value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(value.get("repository", ""))
PY
            )"
        else
            candidate="$HOME/ProjectsLFS/uu-remote-ubuntu-bridge"
        fi
    fi
    [[ -n "$candidate" ]] || fail 'could not discover the source repository'
    candidate="$(realpath "$candidate")"
    [[ -d "$candidate/.git" ]] || fail "not a Git checkout: $candidate"
    printf '%s\n' "$candidate"
}

repo_dir="$(discover_repository)"
manager="$repo_dir/scripts/uu_update_manager.py"
installer="$repo_dir/install.sh"
verifier="$repo_dir/scripts/verify.sh"
installed_manifest="$HOME/.local/share/wineprefixes/uu-remote/compat/release-manifest.json"
state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/uu-remote-upgrader"
wine_prefix="$HOME/.local/share/wineprefixes/uu-remote"
updater_state_dir="$HOME/.local/state/uu-remote-updater"
systemctl_user=(
    /usr/bin/env
    "DBUS_SESSION_BUS_ADDRESS=unix:path=${XDG_RUNTIME_DIR:-/run/user/$UID}/bus"
    /usr/bin/systemctl --user
)

for required in /usr/bin/flock /usr/bin/git /usr/bin/python3 \
    "$manager" "$installer" "$verifier"; do
    [[ -x "$required" ]] || fail "required executable is unavailable: $required"
done

git_clean() {
    [[ -z "$(/usr/bin/git -C "$repo_dir" status --porcelain)" ]]
}

pull_repository() {
    local branch
    local before
    local remote_ref

    [[ "$pull_latest" == true ]] || return 0
    git_clean || fail 'repository has local changes; commit or preserve them before upgrading'
    branch="$(/usr/bin/git -C "$repo_dir" symbolic-ref --quiet --short HEAD || true)"
    [[ -n "$branch" ]] || fail 'repository is detached; switch to its maintained branch first'
    remote_ref="origin/$branch"
    before="$(/usr/bin/git -C "$repo_dir" rev-parse HEAD)"
    log "fetching origin/$branch"
    /usr/bin/git -C "$repo_dir" fetch --prune --tags origin "$branch"
    /usr/bin/git -C "$repo_dir" merge-base --is-ancestor HEAD "$remote_ref" \
        || fail "local $branch and $remote_ref diverged; refusing an automatic merge"
    /usr/bin/git -C "$repo_dir" merge --ff-only "$remote_ref"
    if [[ "$before" != "$(/usr/bin/git -C "$repo_dir" rev-parse HEAD)" &&
          "${UURB_UPGRADE_REEXEC:-0}" != 1 ]]; then
        log 'source changed; restarting from the newly pulled script'
        exec /usr/bin/env UURB_UPGRADE_REEXEC=1 \
            "$repo_dir/scripts/upgrade-uu-remote.sh" \
            "${original_arguments[@]}"
    fi
}

manifest_field() {
    /usr/bin/python3 "$repo_dir/scripts/patch-gameviewer.py" field "$1" \
        --manifest "$installed_manifest"
}

updater_command() {
    [[ -f "$config_file" ]] || fail 'automatic update configuration is not enabled'
    /usr/bin/python3 "$manager" --config "$config_file" "$@"
}

read_updater_state_dir() {
    /usr/bin/python3 - "$config_file" "$updater_state_dir" <<'PY'
import json
import sys
from pathlib import Path

config, fallback = sys.argv[1:]
value = json.loads(Path(config).read_text(encoding="utf-8"))
print(value.get("state_dir", fallback))
PY
}

run_source_checks() {
    log 'running proprietary-binary-free repository tests'
    /usr/bin/python3 -m unittest discover -s "$repo_dir/tests" -v
    /usr/bin/bash -n "$repo_dir/scripts/upgrade-uu-remote.sh"
}

run_live_check() {
    local verifier_options=("$@")

    log 'verifying the live relay, keyboard route, and approved binary'
    /usr/bin/env \
        "DBUS_SESSION_BUS_ADDRESS=unix:path=${XDG_RUNTIME_DIR:-/run/user/$UID}/bus" \
        "$verifier" --quick "${verifier_options[@]}"
}

print_status() {
    local installed='unavailable'
    local service_state='unknown'

    if [[ -f "$installed_manifest" ]]; then
        installed="$(manifest_field version)"
    fi
    service_state="$("${systemctl_user[@]}" is-active uu-remote-bridge.service 2>/dev/null || true)"
    printf 'UU Remote upgrade status\n'
    printf '  repository: %s\n' "$repo_dir"
    printf '  source: %s\n' "$(/usr/bin/git -C "$repo_dir" describe --always --dirty)"
    printf '  installed UU: %s\n' "$installed"
    printf '  bridge: %s\n' "${service_state:-unknown}"
    if [[ -f "$config_file" ]]; then
        updater_command status
    else
        printf '  maintenance: not configured\n'
    fi
}

refresh_updater_runtime() {
    local updater_libexec="$HOME/.local/libexec/uu-remote-updater"
    local unit_dir="$HOME/.config/systemd/user"

    [[ -f "$config_file" ]] || return 0
    /usr/bin/install -d -m 0755 \
        "$HOME/.local/bin" "$updater_libexec/scripts" "$unit_dir"
    /usr/bin/install -m 0755 "$manager" \
        "$HOME/.local/bin/uu-remote-update"
    /usr/bin/install -m 0755 \
        "$repo_dir/scripts/promote-approved-release.py" \
        "$repo_dir/scripts/stop-wine-prefix" \
        "$updater_libexec/scripts/"
    /usr/bin/install -m 0644 "$repo_dir/scripts/gameviewer_patchlib.py" \
        "$updater_libexec/scripts/gameviewer_patchlib.py"
    /usr/bin/install -m 0644 \
        "$repo_dir/systemd/uu-remote-update-check.service" \
        "$repo_dir/systemd/uu-remote-update-check.timer" \
        "$repo_dir/systemd/uu-remote-repair-monitor.service" \
        "$repo_dir/systemd/uu-remote-repair-monitor.timer" \
        "$unit_dir/"
    "${systemctl_user[@]}" daemon-reload
    "${systemctl_user[@]}" enable --now \
        uu-remote-update-check.timer uu-remote-repair-monitor.timer \
        >/dev/null
}

backup_paths=(
    "$HOME/.config/uu-remote-bridge/environment"
    "$HOME/.config/uu-remote-bridge/alsa-null.conf"
    "$HOME/.config/systemd/user/uu-remote-bridge.service"
    "$HOME/.config/systemd/user/uu-remote-bridge.service.d"
    "$HOME/.config/systemd/user/uu-remote-console.service"
    "$HOME/.config/systemd/user/uu-keyring-unlock.service"
    "$HOME/.local/bin/uu-agent"
    "$HOME/.local/bin/uu-ssh"
    "$HOME/.local/bin/uu-shell"
    "$HOME/.local/bin/uu-link"
    "$HOME/.local/bin/uu-keyring-unlock"
    "$HOME/.local/bin/uu-remote"
    "$HOME/.local/bin/uu-remote-bridge"
    "$HOME/.local/bin/uu-remote-console"
    "$HOME/.local/bin/uu-remote-upgrade"
    "$HOME/.local/share/applications/uu-remote.desktop"
    "$HOME/Desktop/UU Remote.desktop"
    "$HOME/.local/libexec/uu-connection-status"
    "$HOME/.local/libexec/uu-remote-stop-wine-prefix"
    "$wine_prefix/compat"
    "$wine_prefix/drive_c/Program Files/FreeRDP"
    "$wine_prefix/drive_c/Program Files/Netease/GameViewer/bin"
)
backup_dir=''
runtime_refresh_started=false

capture_runtime_backup() {
    local item
    local relative
    local target
    local timestamp

    timestamp="$(/usr/bin/date +%Y%m%dT%H%M%S)"
    backup_dir="$state_dir/transactions/$timestamp"
    /usr/bin/install -d -m 0700 "$backup_dir/tree"
    for item in "${backup_paths[@]}"; do
        [[ -e "$item" || -L "$item" ]] || continue
        relative="${item#/}"
        target="$backup_dir/tree/$relative"
        /usr/bin/install -d -m 0700 "$(/usr/bin/dirname "$target")"
        /bin/cp -a --reflink=auto "$item" "$target"
    done
    /usr/bin/python3 - "$backup_dir/record.json" "$repo_dir" \
        "$(manifest_field version)" <<'PY'
import json
import os
import subprocess
import sys
import time
from pathlib import Path

destination, repository, installed_version = sys.argv[1:]
record = {
    "schema_version": 1,
    "created_at": int(time.time()),
    "repository": str(Path(repository).resolve()),
    "source_commit": subprocess.check_output(
        ["git", "-C", repository, "rev-parse", "HEAD"], text=True
    ).strip(),
    "installed_version": installed_version,
}
path = Path(destination)
path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
os.chmod(path, 0o600)
PY
    /usr/bin/ln -sfn "$backup_dir" "$state_dir/latest"
    log "local runtime rollback copy: $backup_dir"
}

restore_runtime_backup() {
    local backup
    local failed
    local item
    local relative

    [[ -n "$backup_dir" && -d "$backup_dir/tree" ]] || return 1
    log 'runtime refresh failed; restoring the post-promotion runtime copy'
    "${systemctl_user[@]}" stop uu-remote-bridge.service >/dev/null 2>&1 || true
    "$repo_dir/scripts/stop-wine-prefix" \
        "$wine_prefix" /opt/wine-stable/bin/wineserver >/dev/null 2>&1 || true
    for item in "${backup_paths[@]}"; do
        relative="${item#/}"
        backup="$backup_dir/tree/$relative"
        [[ -e "$backup" || -L "$backup" ]] || continue
        failed="$backup_dir/failed/$relative"
        /usr/bin/install -d -m 0700 "$(/usr/bin/dirname "$failed")"
        if [[ -e "$item" || -L "$item" ]]; then
            /bin/mv "$item" "$failed"
        fi
        /usr/bin/install -d -m 0700 "$(/usr/bin/dirname "$item")"
        /bin/cp -a "$backup" "$item"
    done
    "${systemctl_user[@]}" daemon-reload
    "${systemctl_user[@]}" start uu-remote-bridge.service
}

on_error() {
    local status=$?

    trap - ERR
    if [[ "$runtime_refresh_started" == true ]]; then
        restore_runtime_backup || true
    fi
    exit "$status"
}
trap on_error ERR

pull_repository

if [[ "$action" == status ]]; then
    print_status
    exit 0
fi

git_clean || fail 'repository changed during preparation'
run_source_checks
run_live_check --allow-runtime-drift

if [[ "$action" == check ]]; then
    log 'checking the official endpoint without changing the live relay'
    updater_command check
    updater_command status
    exit 0
fi

/usr/bin/install -d -m 0700 "$state_dir"
exec 9>"$state_dir/upgrade.lock"
/usr/bin/flock -n 9 || fail 'another full UU upgrade is already running'

xrdp_before="$(
    /usr/bin/systemctl show xrdp.service \
        --property=ActiveState --property=MainPID
)"

log 'checking for an exact-hash accepted UU release'
updater_command check
updater_state_dir="$(read_updater_state_dir)"
pending_kind="$(
    /usr/bin/python3 - "$updater_state_dir/pending.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.is_file():
    print("")
else:
    print(json.loads(path.read_text(encoding="utf-8")).get("kind", ""))
PY
)"
updater_phase="$(
    /usr/bin/python3 - "$updater_state_dir/status.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
print(json.loads(path.read_text(encoding="utf-8")).get("phase", ""))
PY
)"
if [[ -n "$pending_kind" && "$pending_kind" != approved-promotion ]]; then
    fail "pending maintenance task is $pending_kind; an unaccepted binary cannot be deployed"
fi
if [[ "$pending_kind" == approved-promotion ||
      "$updater_phase" == promotion-blocked ]]; then
    if [[ "$promote_now" == true ]]; then
        log 'operator requested immediate guarded promotion'
        updater_command promote-now
    else
        log 'waiting for the configured UU idle window before promotion'
        updater_command monitor
    fi
    if [[ -f "$updater_state_dir/pending.json" ]]; then
        updater_command status
        fail 'accepted release remains deferred; rerun apply when idle or explicitly add --now'
    fi
    updater_phase="$(
        /usr/bin/python3 - "$updater_state_dir/status.json" <<'PY'
import json
import sys
from pathlib import Path

print(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")).get("phase", ""))
PY
    )"
    [[ "$updater_phase" == promoted || "$updater_phase" == current ]] \
        || fail "accepted product promotion ended in phase: $updater_phase"
fi

[[ -f "$installed_manifest" ]] || fail 'installed release manifest disappeared'
installed_version="$(manifest_field version)"
source_manifest="$repo_dir/patches/uu-remote-$installed_version.json"
[[ -f "$source_manifest" ]] \
    || fail "source has no manifest for installed UU $installed_version"
[[ "$(
    /usr/bin/python3 "$repo_dir/scripts/patch-gameviewer.py" field review_status \
        --manifest "$source_manifest"
)" == approved ]] || fail "UU $installed_version is not an approved source manifest"

capture_runtime_backup
runtime_refresh_started=true
log "refreshing bridge runtime for approved UU $installed_version"
"$installer" \
    --skip-packages \
    --skip-account-login \
    --release-manifest "$source_manifest"
run_live_check
runtime_refresh_started=false

refresh_updater_runtime
"$HOME/.local/bin/uu-agent" runtime >/dev/null
"$HOME/.local/bin/uu-agent" version >/dev/null

xrdp_after="$(
    /usr/bin/systemctl show xrdp.service \
        --property=ActiveState --property=MainPID
)"
if [[ "$(sed -n 's/^ActiveState=//p' <<<"$xrdp_after")" != \
      "$(sed -n 's/^ActiveState=//p' <<<"$xrdp_before")" ]]; then
    fail 'XRDP active state changed during the UU-only upgrade'
fi
if [[ "$(sed -n 's/^MainPID=//p' <<<"$xrdp_after")" != \
      "$(sed -n 's/^MainPID=//p' <<<"$xrdp_before")" ]]; then
    log 'XRDP remained active but its PID changed independently during the upgrade'
fi

log "upgrade complete: UU $installed_version, source $(/usr/bin/git -C "$repo_dir" rev-parse --short HEAD)"
print_status
