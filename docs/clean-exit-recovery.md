# Recover after a clean bridge exit

## Incident and evidence

On 2026-09-07 at 14:15:13 HKT the route supervisor detected a change from
Ethernet to Wi-Fi and returned to request a complete UU relay restart. The
parent logged that a critical child had exited. However, systemd recorded
`ExecMainStatus=0`, `Result=success`, and left the enabled service inactive.
`Restart=on-failure` did not apply, so UU remained unavailable until recovery.

The logs prove the network-change trigger and the restart-policy gap. They do
not prove why that particular launcher ultimately returned zero instead of its
expected one. The installed launcher had been edited after its process started;
its on-disk contents are not proof of the historical in-memory code. Do not
claim an OOM, a vendor crash, or lost login without separate evidence.

## Fix

- Use `Restart=always` with `RestartSec=30`: unexpected clean exits, signals,
  and failing exits all recover. Explicit `systemctl --user stop` still stops
  the service. No periodic agent or token-consuming repair process is needed.
- Use `StartLimitIntervalSec=0` so a prolonged network/login dependency failure
  does not exhaust five startup attempts and strand an unattended machine.
  The 30-second restart delay remains, as do existing memory, swap, task,
  cleanup-timeout and whole-service process containment limits.
- Record the exited critical child's PID and status using Bash `wait -n -p`.
  Both a clean critical-child exit and a failing exit request relay recovery.
- Keep the current account, Wine prefix, desktop selection, audio settings and
  independently owned VNC backend. Do not reinstall UU or reset login to fix a
  service that is simply inactive.
- The verifier recognizes the opt-in shared VNC service by its configured
  loopback listener, owning process and matching viewer port, including the
  VNC display-number notation. It no longer requires an unused FreeRDP binary
  for VNC mode. Missing or mismatched live transport still fails verification.

This closes the verified restart gap; it cannot guarantee connectivity during
power loss, provider outages, invalid credentials, or physical network failure.

## Brief route changes (October 2026)

A subsequent outage matched two NetworkManager default-route changes:
Ethernet to Wi-Fi, then back about two minutes later. The bridge's own logs
identified both restarts as route-change requests, and systemd recovered the
service normally. That evidence identifies the immediate interruption trigger;
it does not identify why the upstream route changed or establish a vendor crash.
Another observed transition lasted about one minute. NetworkManager reported
site/local connectivity followed by global connectivity, without a matching
kernel Ethernet link-down event. Do not infer a bad cable or disable network
connectivity checks from that evidence alone.

With `UURB_NETWORK_INTERFACE=default`, the existing supervisor now requires the
same replacement interface for **three consecutive route checks** before
restarting. Checks retain their existing cadence (40 supervisor iterations,
nominally about ten seconds). An absent route, failed route probe, return to
the original interface, or a different candidate resets the pending decision.
This suppresses short flaps but adds roughly two check intervals before a
genuine switch. A sustained outage or the two-minute incident can still require
a reconnect. Explicit adapter selection and `all` mode are unchanged.

No extra watcher, connectivity probe, routing rule, account change or desktop
restart is required by this guard. Tests run the actual Bash decision function
against synthetic route sequences. They do not interrupt production networking.
If the launcher is atomically staged while UU is connected, the running Bash
supervisor keeps its old function until the next normal bridge start. Record
that deferred activation; do not rewrite the full runtime digest or describe
the staged fix as already live.

## Maintenance checks for a shared VNC desktop

The updater's health check must follow `UURB_DESKTOP_RELAY`, just as the runtime
verifier does. Previously it always required FreeRDP and GNOME RDP processes,
which could classify a working VNC relay as unhealthy. VNC mode now checks the
configured x11vnc process, its owned loopback listener, and a viewer connected
to that port. For a bridge-managed VNC server it reads the last reported port
from the bounded tail of the relay log. Missing processes, wrong listener
ownership, non-loopback binding, or unresolved ports remain failures.

This changes diagnostics only. It does not switch relay modes, alter the
default no-restart maintenance policy, or prove client keyboard/clipboard
acceptance without a real client test. The RDP checks remain in use for RDP
mode. Updating the standalone maintenance helper takes effect on its next
invocation and does not require restarting the working UU desktop.

## Recovery and checks

### Already recovered: avoid repairing a healthy desktop

On 2026-10-10 an operator reported UU unavailable, then reported it back before
any service change. The same bridge PID had remained active since the previous
day. Live IPC, exact patched-binary checks, account device listing, the shared
desktop relay and input/clipboard helpers passed. There was no matching bridge
restart, kernel OOM or logged default-interface change in the inspected window.
The daily installer download had timed out separately. These observations do
**not** establish a cause for the brief remote connection failure, or prove
that an updater timeout took the desktop offline. Do not restart the working
desktop or claim a network/hardware diagnosis from them.

The investigation did establish a maintenance false positive: systemd's
`NRestarts` had reached 12 over time, and a single restart the day before was
classified as a storm simply because the service was young again. The resulting
unstarted repair remained queued after the runtime recovered.

- Keep `restart_count` as lifetime diagnostic information. Detect a storm only
  from at least three scheduled-restart journal events in the last 15 minutes.
  Match systemd's structured message ID, the exact user unit and current boot;
  validate monotonic timestamps and read at most three records. The returned
  `recent_restart_count` saturates at three. An unavailable journal is `null`,
  never proof of a storm. Rotated or unavailable logs can miss a real storm;
  service/process/listener failures are still checked independently.
- Before resuming a queued `runtime-health` repair with zero attempts and no
  agent thread, require two healthy probes 20 seconds apart with available
  restart evidence. Mark it `recovered-before-repair`, retain its private
  `tasks/<id>/task.json`, context and checkout, and remove only its pending queue
  marker. Release tasks, promotions and already-started repair work remain.
- Use the existing maintenance timer. This adds no background process and
  does not restart UU, RDP, VNC, GNOME or the current desktop.

The maintenance helper can be atomically updated while UU is connected; the
next invocation uses the fix. Back up the helper and private state first. A
successful local health probe is not a substitute for real-client mouse,
Chinese dictation and clipboard acceptance, and cannot guarantee vendor or
Internet availability.

For this incident, the complete local suite passed (212 tests, two opt-in
tests skipped). The deployed maintenance helper reported zero recent restarts
and healthy relay components while the lifetime count remained 12. A manual
retry of the daily update check succeeded and verified the already-installed
release's installer hash. No UU upgrade or runtime restart was needed.

### Commands

```bash
systemctl --user show uu-remote-bridge.service \
  -p ActiveState -p SubState -p Result -p ExecMainStatus -p NRestarts -p Restart
journalctl --user -u uu-remote-bridge.service -n 60 --no-pager
systemctl --user start uu-remote-bridge.service
uu-agent list
uu-agent snapshot
```

An `active` unit alone is insufficient. Check that the background server is
running, the saved account can list devices, and the private relay screenshot
shows the selected live desktop. `uu-remote network` may describe an old
completed connection, not the new one. Do not mistake it for a current remote
client acceptance test. Keep device IDs, screenshots, logs and backups private.

If verification reports a missing health-stub comparison artifact in a fresh
checkout, run `scripts/build-compat.sh` to build the local reference files.
This is a build, not an installation: it does not replace the running helpers.
Do not suppress binary-integrity failures merely to get a green health report.

Use the [runtime-only refresh](runtime-only-refresh.md) for normal deployment.
For a narrow emergency hotfix, back up the installed unit and launcher, patch
only the verified affected settings, and retain unrelated local customizations.
Never overwrite an executing Bash file in place: prepare and syntax-check a
replacement, atomically rename it onto the installed path, and restart only UU
at a controlled point. Reload systemd after unit edits. Do not restart SSH,
GNOME, another Wine prefix, the shared VNC service, or chat applications.

## Regression tests

```bash
python3 -m unittest discover -s tests -v
UURB_TEST_SYSTEMD=1 python3 -m unittest discover \
  -s tests -p test_service_recovery.py -v
```

The normal suite runs the actual final launcher supervision block against
harmless child processes with exit codes zero and seven. The opt-in test uses
a uniquely named transient user unit, not the production relay: it proves more
than five clean exits recover and that a deliberate stop remains stopped. Its
100ms delay is test-only; production retains 30 seconds. The test always cleans
up its unit. A live production fault test, if required, needs an independent
SSH/terminal management path and a brief UU reconnect window.

## Verified recovery on 2026-09-07

- The enabled bridge was restarted at 17:10 HKT using the existing account.
- Account device listing succeeded, the selected desktop was visible through
  the relay, and the quick live verifier passed after the checks above were
  corrected. Runtime drift was explicitly allowed to preserve previously
  installed workstation-specific input helpers; no full runtime upgrade was
  performed.
- The suite ran 145 tests with only the opt-in systemd test skipped. That
  isolated live systemd test was then run explicitly and passed.
- No reboot or new external remote-control session was used as an acceptance
  test. No WeChat, WeCom, phone mirror, SSH or shared-VNC process was restarted.
