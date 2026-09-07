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

## Recovery and checks

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
