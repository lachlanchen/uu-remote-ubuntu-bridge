# Automatic Checks and Resumable Repair

The maintenance subsystem detects upstream changes without replacing a smooth
live relay. It separates zero-downtime observation from recovery actions and
keeps unknown proprietary binaries behind the same semantic review gate as the
manual workflow.

## Enable it

For an existing installation, select its validated input behavior track:

```bash
cd ~/Projects/uu-remote-ubuntu-bridge
git fetch --tags origin
./scripts/configure-updater.sh enable \
  --track track-rdp-broker-v1 \
  --model gpt-5.6-sol \
  --reasoning-effort xhigh
```

Use `track-direct-x11-v1` on a computer already validated with the direct X11
route. A fresh installation can opt in with `./install.sh
--automatic-updates`; the configurator derives the track from the saved
keyboard route.

The installed Codex CLI names the requested configuration `gpt-5.6-sol` with
`model_reasoning_effort="xhigh"`. Both values are explicit in
`~/.config/uu-remote-bridge/updater.json`, so a background service does not
silently inherit a later interactive default. Codex must already be logged in
for the same Unix user.

## Services and reboot behavior

Two systemd user timers are enabled:

| Timer | Schedule | Work |
| --- | --- | --- |
| `uu-remote-update-check.timer` | Daily around 04:20 with a randomized delay; also 12 minutes after boot | Fetch metadata and inspect the official UU endpoint without restarting the relay |
| `uu-remote-repair-monitor.timer` | Seven minutes after boot and every 15 minutes after its previous run | Check relay health, resume a pending Codex thread, or perform bounded recovery when the relay is already unhealthy |

The daily timer uses `Persistent=true`, so a powered-off machine performs one
missed check after its next boot. The repair timer does not need a logged-in
terminal. It runs from the user manager used by the existing unattended bridge.

Inspect it with:

```bash
uu-remote update
systemctl --user list-timers --all \
  uu-remote-update-check.timer uu-remote-repair-monitor.timer
journalctl --user -u uu-remote-update-check.service -n 100 --no-pager
journalctl --user -u uu-remote-repair-monitor.service -n 100 --no-pager
```

## Low-disruption rules

Normal checks never run the UU installer, stop Wine, restart GNOME RDP, or
replace compatibility files. They follow the official redirect with a HEAD
request, remove expiring query keys before writing state, parse the full build
identifier, and compare it with every approved manifest. A same-version release
is downloaded once to establish its complete SHA-256; unchanged ETag, size, and
cached hash avoid repeating that download on later checks.

An endpoint that is equal to or older than the approved baseline is recorded
and ignored. This matters because a release channel can temporarily advertise
an older build. A different filename alone is not treated as an upgrade.

The monitor changes the live relay only after health is bad twice, 20 seconds
apart. It then performs one systemd restart. If that fails and known-good
reinstallation is enabled, it first clones the selected immutable track, runs
the repository tests, and prebuilds compatibility artifacts while the already
unhealthy relay remains untouched. Only the final reinstall reaches the live
prefix. A healthy bridge is never periodically restarted for maintenance.

## New upstream release workflow

When the official endpoint reports a numerically newer build:

1. Download into `~/.local/state/uu-remote-updater/downloads` with a 1 GiB
   ceiling and compute the complete SHA-256.
2. Accept it immediately only if that hash already belongs to an approved
   repository manifest. Even then, live deployment remains maintenance-gated.
3. For an unknown hash, attempt non-executing archive extraction with
   `stage-uu-release.sh`.
4. Create an isolated repair clone and a complete local context record under
   `~/.local/state/uu-remote-updater/tasks`.
5. Ask Codex to perform static comparison, candidate discovery, code changes,
   documentation, and proprietary-binary-free tests in that clone.

An installer wrapper that cannot be extracted is not executed automatically.
The existing `--sandbox-install` path requires a deliberate operator action
because it creates a root-managed transient sandbox. The repair context records
that boundary instead of weakening it.

Codex may produce a draft manifest and a repair branch. It cannot label its own
binary interpretation `approved`, push, alter the live Wine prefix, use sudo,
or deploy an unknown binary. A maintainer still re-establishes instruction
semantics and performs the Windows and controller acceptance checks described
in [upstream maintenance](upstream-maintenance.md).

## Resuming Codex after interruption

Each task stores these fields atomically with mode `0600`:

- task kind, candidate identity, selected behavior track, and base commit
- sanitized release metadata and static staging result
- repair checkout and context paths
- Codex thread UUID, attempt count, last event time, and phase
- JSONL events, final structured result, and test output

The thread UUID is saved as soon as Codex emits `thread.started`. If the
computer reboots, the network drops, the service times out, or Codex exits
early, the next monitor run calls `codex exec resume` with that same UUID and
points it back to the persisted context. If interruption happened before a
thread UUID existed, it starts a new thread from the same context. Retry delay
grows from 15 minutes to a maximum of 24 hours, avoiding a tight paid-token
loop while retaining the task indefinitely.

Codex output must match `scripts/codex-repair-result.schema.json`. The monitor
then independently runs the full unit suite. Its terminal states are:

| State | Meaning |
| --- | --- |
| `ready-for-review` | Source changed and tests pass; semantic review and live acceptance remain |
| `no-change` | Codex found no safe source change |
| `blocked` | Evidence, staging, tests, or human approval is still required |

## State and privacy

Configuration contains no password or UU token. State directories are `0700`
and files are `0600`. Temporary CDN query keys are stripped. Proprietary
installers, extracted executables, Codex event logs, local journals, account
state, and host-specific evidence remain ignored and outside Git.

The Codex service uses `workspace-write`, `approval_policy="never"`,
`NoNewPrivileges=yes`, private temporary files, a read-only system view, and a
disabled Git push URL in the repair clone. Network access remains available
because Codex authentication requires it. These controls reduce accidental
reach; they are not a security boundary equivalent to a separate VM.

## Another-computer handoff

Send the operator this sequence after choosing the track from
[Input Behavior Tracks](release-tracks.md):

```bash
cd ~/Projects/uu-remote-ubuntu-bridge
git status --short
git pull --ff-only origin main
git fetch --tags origin
./scripts/configure-updater.sh enable --track TRACK_NAME \
  --model gpt-5.6-sol --reasoning-effort xhigh
./scripts/configure-updater.sh status
```

Stop if the worktree is dirty. Confirm `codex login status` for that Unix user
and verify both timers after reboot. Do not copy this machine's updater state,
Codex sessions, Wine prefix, keyring credential, or UU logs to the other host.

## Disable or reset

Disable timers while retaining local repair evidence:

```bash
./scripts/configure-updater.sh disable
```

Delete configuration and all local maintenance state as well:

```bash
./scripts/configure-updater.sh disable --purge-state
```
