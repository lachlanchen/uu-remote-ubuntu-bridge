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
  --track track-rdp-broker-20260724 \
  --model codex-auto-review \
  --reasoning-effort medium \
  --auto-promote-accepted
```

Use `track-direct-x11-20260724` on a computer already validated with the direct X11
route. A fresh installation can opt in with `./install.sh
--automatic-updates`; the configurator derives the track from the saved
keyboard route.

`--auto-promote-accepted` does not let Codex deploy its own result. It only
permits a later exact-hash release whose committed manifest also contains the
complete maintainer acceptance record described below. Without that option,
even a fully accepted release is only reported as ready.

The installed Codex CLI names the requested configuration `codex-auto-review`
with `model_reasoning_effort="medium"`. Both values are explicit in
`~/.config/uu-remote-bridge/updater.json`, so a background service does not
silently inherit a later interactive default. Codex must already be logged in
for the same Unix user.

The configurator also records the absolute executable returned by
`command -v codex`. This matters when Codex was installed under NVM: the
systemd user manager intentionally has a smaller `PATH` than an interactive
shell. The updater invokes that stored executable for both rate-limit queries
and `codex exec`, instead of assuming the shell can discover it later. Use
`--codex /absolute/path/to/codex` when selecting a different installation.

The monitor queries Codex included-usage rate limits immediately before each
automatic repair attempt. It runs Codex only when every reported window is at
or below `codex_max_used_percent`, which defaults to 20. Purchased credits and
rate-limit reset credits are ignored and never consumed. If the local Codex
service cannot verify usage, the repair is deferred for at least one hour
without consuming an attempt.

## Services and reboot behavior

Two systemd user timers are enabled:

| Timer | Schedule | Work |
| --- | --- | --- |
| `uu-remote-update-check.timer` | Daily around 04:20 with a randomized delay; also 12 minutes after boot | Fetch metadata and inspect the official UU endpoint without restarting the relay |
| `uu-remote-repair-monitor.timer` | Seven minutes after boot and every 15 minutes after its previous run | Observe relay health, resume a pending Codex thread, or run an explicitly enabled fully accepted promotion transaction |

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
cached hash sidecar avoid repeating that download on later checks, even if the
official channel temporarily points backward and later returns to that build.

An endpoint that is equal to or older than the approved baseline is recorded
and ignored. This matters because a release channel can temporarily advertise
an older build. A different filename alone is not treated as an upgrade.

The default monitor never changes the live relay. If health is bad twice,
20 seconds apart, it records local evidence and queues analysis without
stopping or restarting RDP, Wine, or UU. An indeterminate user-manager query
is handled the same way.

`--auto-reinstall` is a separate, explicit opt-in to live recovery. Only with
that option may a confirmed failure permit one systemd restart followed by a
known-good reinstall if restart fails. The recovery path first clones the
selected immutable track, runs the repository tests, and prebuilds
compatibility artifacts while the already unhealthy relay remains untouched.
The default configuration used in this guide does not enable it.

Guarded release promotion is independent of health recovery. It cannot
restart XRDP and does not become eligible from a health failure.

## New upstream release workflow

When the official endpoint reports a numerically newer build:

1. Download into `~/.local/state/uu-remote-updater/downloads` with a 1 GiB
   ceiling and compute the complete SHA-256.
2. Recognize it only if that hash already belongs to an approved repository
   manifest. Binary approval alone still cannot transfer it.
3. For an unknown hash, attempt non-executing archive extraction with
   `stage-uu-release.sh`.
4. Create an isolated repair clone and a complete local context record under
   `~/.local/state/uu-remote-updater/tasks`.
5. Ask Codex to perform static comparison, candidate discovery, code changes,
   documentation, and proprietary-binary-free tests in that clone.

Every run receives a mode-0600 snapshot of
[Automated Repair Agent Handoff](automated-repair-agent-handoff.md). It
preserves the two validated host profiles, the separate phone/physical
keyboard paths, failed pacing and routing hypotheses, direct-X11 acceptance,
restart and descriptor lessons, action boundaries, and manual approval gates.
The generated task context requires that snapshot and the detailed project
notes to be read before editing.

An installer wrapper that cannot be extracted is not executed automatically.
The existing `--sandbox-install` path requires a deliberate operator action
because it creates a root-managed transient sandbox. The repair context records
that boundary instead of weakening it.

The 2026-07-24 observation of UU `4.34.0.8979` is the concrete fail-closed
example. Its official installer hash is
`237eb74939a62935ae3e2b1fd43c484d634ccd96fb1094ba764c8cb64065dc9a`.
Networkless staging succeeded, but static matching left two candidates for one
setting path and thousands for the runtime setter. A draft scanner that
ignored x86 instruction boundaries and relative operands was retained only as
private review evidence, not merged or approved. The task therefore remains
`ready-for-review`; it has no runnable manifest, no acceptance record, and no
route to the live prefix.

Codex may produce a draft manifest and a repair branch. It cannot label its own
binary interpretation `approved`, push, alter the live Wine prefix, use sudo,
or deploy an unknown binary. A maintainer still re-establishes instruction
semantics and performs the Windows and controller acceptance checks described
in [upstream maintenance](upstream-maintenance.md).

## Fully accepted, login-preserving promotion

A newer release can enter the live prefix only when all of these gates agree:

1. The official endpoint version and complete installer SHA-256 match one
   approved manifest in the fetched `origin/main` commit.
2. That same committed manifest carries a schema-1 `acceptance` object.
3. The acceptance is bound to both the installer SHA-256 and complete patched
   server SHA-256.
4. A maintainer recorded successful disposable-prefix, controller-input,
   disconnect/reconnect, service-restart, and login-preservation tests.
5. The evidence file exists in the same pinned commit.
6. Stability is between 270 and 1800 seconds.
7. `--auto-promote-accepted` is enabled.
8. UU's local logs have been quiet for the configured maintenance idle period,
   45 minutes by default.

The transaction then:

1. verifies the currently installed bridge and account-state markers;
2. records XRDP state without changing it;
3. stops only `uu-remote-bridge.service`;
4. makes a complete copy of the Wine prefix, with a further 1 GiB free-space
   safety margin;
5. runs the official accepted installer over that same prefix, as UU's normal
   in-place update would;
6. reapplies the exact accepted compatibility manifest;
7. compares the UU login registry section and both account-state trees
   byte-for-byte before opening UU;
8. starts UU and runs two runtime checks separated by the accepted stability
   interval; and
9. commits the result only if XRDP remains in its original active state.

Any exception, failed hash, missing login marker, account-state change,
runtime failure, interruption, or reboot restores the complete old prefix.
The failed task becomes `promotion-blocked` and never retries automatically.
A durable marker lets the next monitor invocation recover an interrupted
transaction. The snapshot and all account evidence remain local with user-only
permissions.

The updater state and Wine prefix must be on the same filesystem so rollback
can replace the prefix atomically. A successful task retains its rollback
snapshot for operator review; it is not silently purged by a timer.

The promotion helper contains no XRDP start, stop, restart, or reload action.
It may briefly disconnect UU when the final accepted update is applied; the
same account state is reused when UU returns, so no sign-in prompt should be
needed. Recent UU activity defers this interruption.

## Resuming Codex after interruption

Each task stores these fields atomically with mode `0600`:

- task kind, candidate identity, selected behavior track, and base commit
- sanitized release metadata and static staging result
- repair checkout and context paths
- an operational-handoff snapshot with the two-host troubleshooting history
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
| `promotion-waiting-idle` | A fully accepted update is ready, but recent UU activity prevents interruption |
| `promotion-running` | The complete-prefix transaction is in progress |
| `promoted` | Login state and runtime verification passed; the accepted release is live |
| `promotion-blocked` | Promotion failed closed and the old prefix was restored; no automatic retry |

If a service journal reports `failed to run command 'codex'`, rerun
`configure-updater.sh enable`. Current configurations persist the absolute
Codex executable, so NVM-only interactive `PATH` entries are not required by
the user service.

## State and privacy

Configuration contains no password or UU token. State directories are `0700`
and files are `0600`. Temporary CDN query keys are stripped. Proprietary
installers, extracted executables, Codex event logs, local journals, account
state, and host-specific evidence remain ignored and outside Git.

The Codex service uses `workspace-write`, `approval_policy="never"`,
`NoNewPrivileges=yes`, and a disabled Git push URL in the repair clone.
Network access remains available because Codex authentication requires it.
These controls reduce accidental reach; they are not a security boundary
equivalent to a separate VM.

The user service deliberately does not also request systemd mount-namespace
features such as `PrivateTmp=`, `ProtectSystem=`, `ProtectKernelTunables=`, or
`ProtectControlGroups=`. On Ubuntu 24.04 with restricted user namespaces,
those user-manager options first place the updater inside AppArmor's
`unprivileged_userns` profile. A nested Bubblewrap user namespace then fails,
so Codex cannot provide `workspace-write`. The updater keeps the compatible
service hardening and lets the Codex sandbox establish the filesystem
boundary itself.

On Ubuntu 24.04, `workspace-write` also needs Ubuntu's AppArmor profile for
Bubblewrap. If status reports `codex-sandbox-deferred`, install and enable only
the distro profile rather than disabling unprivileged-user-namespace
restrictions globally:

```bash
sudo apt install apparmor-profiles
sudo install -o root -g root -m 0644 \
  /usr/share/apparmor/extra-profiles/bwrap-userns-restrict \
  /etc/apparmor.d/bwrap-userns-restrict
sudo apparmor_parser -r /etc/apparmor.d/bwrap-userns-restrict
uu-remote update retry
```

Confirm both layers before retrying:

```bash
systemd-run --user --wait --pipe --collect \
  --property=NoNewPrivileges=yes \
  /usr/bin/bwrap --die-with-parent --unshare-user --uid 0 --gid 0 \
  --ro-bind / / /bin/true
systemctl --user cat uu-remote-repair-monitor.service
```

The probe must exit successfully, and the service must not contain one of the
systemd mount-namespace options listed above. Do not disable Ubuntu's global
unprivileged-user-namespace restriction.

`retry` keeps the private evidence and repair checkout, clears the unusable
Codex thread, and starts a new thread on the next monitor run. It refuses
non-retryable phases. If an operator has completed the documented networkless
fallback in the task's `stage-sandbox` directory, retry imports it only after
the installer, server, and health-monitor hashes match the sandbox record.

There is deliberately no transfer from `ready-for-review` into the live Wine
prefix. The task record always marks automated output as ineligible. A
maintainer must independently establish semantics, approve the manifest,
complete the full controller/login acceptance matrix, commit its evidence, and
bind that acceptance to both binary hashes. Only this later repository state
can make an exact official installer eligible for the guarded transaction.

## Another-computer handoff

Send the operator this sequence after choosing the track from
[Input Behavior Tracks](release-tracks.md):

```bash
cd ~/Projects/uu-remote-ubuntu-bridge
git status --short
git pull --ff-only origin main
git fetch --tags origin
./scripts/configure-updater.sh enable --track TRACK_NAME \
  --model codex-auto-review --reasoning-effort medium \
  --auto-promote-accepted
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
