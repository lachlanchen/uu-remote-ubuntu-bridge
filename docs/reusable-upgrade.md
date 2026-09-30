# Reusable, Login-Preserving Upgrade

`uu-remote-upgrade` combines the repository update, accepted UU product
promotion, bridge refresh, and post-update verification into one repeatable
operation. It is intended for an already working bridge whose account login,
keyboard behavior, and XRDP access must survive the update.

If UU's own updater has already changed the binary behind the saved manifest,
the normal upgrade preflight must fail. Use the
[audited drift-repair procedure](releases/4.40.1.2090-repair.md), not a forced
promotion or a manually falsified version. A product release and a bridge
runtime refresh are separate acceptance decisions.

## Commands

After one current-source installation, use either spelling:

```bash
uu-remote-upgrade status
uu-remote upgrade status
```

Audit without changing the installed UU product:

```bash
uu-remote upgrade check
```

Apply an accepted update after UU has been idle for the configured maintenance
window:

```bash
uu-remote upgrade apply
```

When the operator has deliberately chosen a short UU interruption, bypass only
the activity delay:

```bash
uu-remote upgrade apply --now
```

`--now` is not a force-install switch. The exact installer hash, approved
manifest, hash-bound acceptance record, complete Wine-prefix snapshot,
byte-for-byte account-state comparison, two runtime checks, and automatic
rollback remain mandatory.

The source-tree form works before the command has been installed:

```bash
cd ~/ProjectsLFS/uu-remote-ubuntu-bridge
./scripts/upgrade-uu-remote.sh apply --now
```

## Current production gate

As of 2026-07-27, the production prefix is back on the approved
`4.33.0.8907` client. The guarded `4.34.0.8979` promotion completed its warm
transaction and preserved login, XRDP, and the input profile, but a later
stopped-prefix cold start exposed an accumulated Wine device-registry stall.
The complete 4.33 prefix snapshot was restored, and the same stall then
reproduced on 4.33.

The 4.34 patch remains statically approved, but its promotion acceptance is
withdrawn. Its manifest deliberately has no `acceptance` object, so
`upgrade apply` cannot promote that release. Re-acceptance requires a clean
stopped-prefix cold start, fresh signaling, real controller input, login
preservation, and the normal stability interval. See
[the withdrawn acceptance record](releases/4.34.0.8979-acceptance.md).

## Transaction order

The script:

1. refuses a dirty or detached checkout;
2. fetches and fast-forwards the current branch without merging divergent
   history;
3. restarts itself from the newly pulled source when that source changed;
4. runs the complete proprietary-binary-free unit suite and shell parser;
5. verifies the currently running approved binary, relay, direct-X11 or RDP
   keyboard route, saved timing, network filter, account marker, and historical
   controller path;
6. checks the official endpoint and permits only a fully accepted exact-hash
   release;
7. lets the existing promotion transaction snapshot the complete Wine prefix,
   update it in place, compare account state, verify twice, and roll back on
   any failure;
8. selects the repository manifest matching the now-installed UU version;
9. records a second local runtime copy, then installs the current bridge
   helpers and service while preserving
   `~/.config/uu-remote-bridge/environment`;
10. refreshes the already configured maintenance binaries and timers without
    changing their selected behavior track or Codex settings;
11. verifies `uu-agent`, the bridge, and XRDP's active state.

XRDP is queried but never started, stopped, restarted, or reconfigured by the
UU promotion. The source refresh also operates only on the UU bridge user
service. A changed XRDP PID is reported, while a changed active state fails the
operation.

## Keyboard and control preservation

The installer reads the existing environment before writing it back. On the
validated direct-X11 workstation this preserves:

```text
UURB_TEXT_KEY_DELAY_MS=8
UURB_PHYSICAL_KEY_DELAY_MS=0
UURB_KEYBOARD_ROUTE=x11
UURB_NETWORK_INTERFACE=default
```

Do not copy those values blindly to another host. The other validated profile
uses the RDP broker route. The selected immutable maintenance track remains the
authority for that computer.

The quick verifier does not synthesize private user input. It proves that the
broker, focused relay, selected keyboard helper, patched server, and historical
controller path are available. After a product update, perform one visible
phone and physical-key acceptance:

```text
phone keyboard: abcXYZ123,.!?
computer keyboard: rapid alphabet, Enter, Ctrl+A
mouse: move, click, drag, and wheel
```

## Rollback records

Product promotion keeps its complete prefix snapshot under:

```text
~/.local/state/uu-remote-updater/tasks/*/promotion/snapshot-prefix
```

If promotion fails or is interrupted, the promotion helper restores that
snapshot and marks the task `promotion-blocked`; it does not retry
automatically.

`apply --now` also checks the persisted terminal phase, not merely whether the
pending file disappeared. A failed-closed transaction can therefore never be
reported as a completed upgrade. An explicit later `apply --now` may re-queue
that exact accepted release only when the fetched promotion tooling has a
different source commit. The failed task is moved intact below
`tasks/retired/`; unchanged code is refused so the same failure cannot loop.

After a successful product promotion, the wrapper records the bridge runtime
immediately before refreshing current source:

```text
~/.local/state/uu-remote-upgrader/transactions/TIMESTAMP/
~/.local/state/uu-remote-upgrader/latest
```

If the source refresh fails, the wrapper stops only the UU bridge, restores
that post-promotion runtime copy, and starts the bridge again. Failed files are
retained below the same transaction directory for diagnosis. These private
records can include proprietary binaries and local configuration and must
never be committed.

Snapshots are intentionally not deleted by a timer. Review disk space and
remove an obsolete transaction only after the updated bridge has passed live
controller testing.

## Why the persistent user bus is explicit

XRDP, VNC, and nested desktop terminals can export a private
`DBUS_SESSION_BUS_ADDRESS`. A plain `systemctl --user` can therefore query the
wrong bus even though the persistent user manager and UU service are healthy.
The upgrader and `uu-agent` explicitly use:

```text
unix:path=/run/user/UID/bus
```

This is session-independent and makes the same commands work from a physical
desktop, XRDP, VNC, SSH, or an unattended user manager.

## 2026-07-27 fail-closed lesson

The first production run found a tooling preflight defect before the official
4.34 installer ran. The pinned promotion checkout had no generated
`build/compat/uu-healthd-stub.exe`, so its complete verifier could not compare
the installed health-monitor stub. The transaction entered
`promotion-blocked`, left 4.33 installed, and kept the account and XRDP
unchanged.

Building the missing verifier then exposed a second, deeper issue: GNU's PE
linker inserted the build time and recalculated the PE checksum. Two builds
from identical source therefore had different whole-file hashes even though
all executable content was identical.

The permanent correction fixes `SOURCE_DATE_EPOCH`, requests no linker
timestamp insertion for new builds, and compares legacy health stubs after
zeroing only the documented COFF `TimeDateStamp` and optional-header
`CheckSum` fields. Any code, data, import, header, or other-byte difference
still fails. The promotion builds this verifier inside the pinned checkout
before checking the live runtime.

The pre-promotion check may tolerate only the expected source-digest
difference between pulled tooling and the still-running bridge. It still
requires the approved product binary, audited health-monitor backup, input
hooks, keyboard route, relay listener, account marker, and controller history.
The post-install checks require an exact runtime digest.

The first live 4.34 retry exposed a separate service-readiness race. A
`Type=simple` user service becomes `active` as soon as its launcher starts,
before the private GNOME RDP relay has necessarily opened port 3390. Stale
Wine process names from the preceding stop could satisfy the old readiness
loop, so the verifier ran during that sub-second gap and the transaction
correctly rolled back even though the relay opened one second later.

The verifier now waits for the real GNOME daemon to own the configured relay
listener and, when `UURB_KEYBOARD_ROUTE=x11`, for the native X11 helper and its
ready record. It still validates every condition independently after the wait.
This is a readiness correction, not a bypass: an absent relay or input helper
still fails closed after the bounded 45-second window.

With that correction committed as `eb5382e`, the same accepted
`4.34.0.8979` installer completed the full transaction on the production
workstation. Both runtime checks passed, account state remained byte-for-byte
usable, XRDP retained its active state and process, and the wrapper refreshed
the bridge from the same pinned source. The saved input profile remained
8 ms text pacing, 0 ms physical-key pacing, and direct X11 routing.

That result is retained as historical evidence for the transaction machinery,
not as current release acceptance. A later production cold start remained in
`update_gvinput` before creating a signaling room. Prefix-local inspection
found 527 failed virtual-input roots and 21,894 retained Wine Bluetooth device
observations. Restoring 4.33 reproduced the scan; bounded registry cleanup
reduced it to milliseconds and restored fresh signaling. Commit `1dd8ee2`
made that cleanup idempotent and part of the cold-start boundary, while the
4.34 acceptance record was withdrawn pending a complete retest.

Installed commands live in `~/.local/bin`. Ensure that directory is in
`PATH`; Ubuntu normally adds it from `~/.profile`. The source-tree command
shown above remains available if a custom shell profile omits it.

## Reusing it on another computer

Keep that computer's Wine prefix, updater state, keyring credential, and input
profile local. Pull only the source:

```bash
cd ~/ProjectsLFS/uu-remote-ubuntu-bridge
git status --short
git pull --ff-only origin main
./install.sh --skip-packages --skip-account-login
./scripts/configure-updater.sh enable --track TRACK_NAME \
  --model codex-auto-review --reasoning-effort medium \
  --auto-promote-accepted
./scripts/upgrade-uu-remote.sh check
```

Choose `track-rdp-broker-20260724` for the already smooth broker host or
`track-direct-x11-20260724` for a host that has separately passed direct-X11
acceptance. Never copy this workstation's private updater state or prefix to
the other machine.
