# Troubleshooting

## First checks

```bash
uu-remote status
scripts/verify.sh --quick
uu-remote logs
```

Runtime logs are under `~/.local/state/uu-remote-bridge`. UU's proprietary logs
remain inside its Wine prefix. Do not post either set without removing account
and device metadata.

Persistent runtime choices are in
`~/.config/uu-remote-bridge/environment`. Change them by rerunning the
installer, for example:

```bash
./install.sh --skip-packages --skip-account-login \
  --rdp-port 3391 --resolution 2560x1440 --display auto \
  --grd-fd-restart-threshold 4096
```

## UU is offline after reboot

Inspect the unattended boot chain without displaying either password:

```bash
./scripts/configure-unattended.sh status
journalctl --user -b \
  -u uu-keyring-unlock.service \
  -u gnome-remote-desktop.service \
  -u uu-remote-bridge.service
```

After the first configured reboot, both `Account in tss group` and
`tss active in this login` must be `yes`. A keyring unlock failure usually
means the GNOME keyring password changed. Replace the encrypted credential:

```bash
./scripts/configure-unattended.sh enable --replace-credential
sudo reboot
```

Do not place the password in the unit or command line. See
`unattended-startup.md` for the boot sequence, controlled verification, and
rollback.

## Device is online and video works, but control does not

Check the compatibility log:

```bash
log="$HOME/.local/share/wineprefixes/uu-remote/drive_c/users/$USER/AppData/Local/Temp/uu-input-bridge.log"
tail -80 "$log"
```

A working click contains:

```text
route=broker result=1 error=0
```

`result=0 error=5` without `route=broker` means the server was not injected.
Restart the service and inspect `input-injector.log`:

```bash
uu-remote restart
tail -80 ~/.local/state/uu-remote-bridge/input-injector.log
```

If UU was updated, run the patch verifier. Do not force a new version through
the patcher:

```bash
scripts/patch-gameviewer.py verify \
  "$HOME/.local/share/wineprefixes/uu-remote/drive_c/Program Files/Netease/GameViewer/bin/GameViewerServer.exe"
```

An `unsupported executable` result is intentional. Stage and audit the new
release with `scripts/stage-uu-release.sh` and
`scripts/audit-gameviewer.py`; follow `docs/upstream-maintenance.md`. Do not
add only the new hash to an old manifest.

## First click forces the UU session to exit

This was the original symptom of Wine rejecting `SendInput` from UU's service
token. Verify that both lines appear in the bridge log:

```text
UU SendInput bridge active
UU Wine event-log compatibility active
```

Then verify that `uu-input-broker.exe` is running. A service restart normally
restores both components.

## The phone keyboard does not type, but UU's computer keyboard does

These controls use different paths. The computer-keyboard panel sends physical
key events through `SendInput`; the phone's native IME sends batches marked
`KEYEVENTF_UNICODE`. SDL FreeRDP expects physical scancodes, so an old broker
can turn every letter into one repeated key and numbers into punctuation.
Confirm the broker log reports `text=normalized` for a phone text commit:

```bash
log="$HOME/.local/share/wineprefixes/uu-remote/drive_c/users/$USER/Temp/uu-input-broker.log"
tail -80 "$log"
```

If Unicode calls appear in `uu-input-bridge.log` with flag `0x00000004` but the
broker does not report normalization, reinstall or update the bridge and
restart the service. A Windows UU host followed by RDP appears to fix the issue
because native Windows converts the Unicode input before RDP handles it.

If the checkout contains the fix but the verifier says the installed runtime
differs, pulling was not followed by installation:

```bash
./install.sh --skip-packages --skip-account-login
```

Use the [mobile-keyboard parity handoff](mobile-keyboard-parity-handoff.md) when
this path works on one Ubuntu host but not another. It records the known-good
7090 baseline, phone/controller variables, exact acceptance matrix, and bounded
diagnostics without exposing typed content or UU identity data.

## Input degrades after a long relay session

Run the quick verifier and inspect only descriptor metadata:

```bash
scripts/verify.sh --quick
pid="$(pgrep -o -f 'gnome-remote-desktop-daemon --rdp-port')"
find "/proc/$pid/fd" -maxdepth 1 -type l | wc -l
sed -n '/Max open files/p' "/proc/$pid/limits"
```

Repeated `Failed to dup keymap fd: Too many open files` messages mean GNOME
RDP can no longer allocate the descriptor required by `libei` input. On the
validated Ubuntu 24.04 stack, libei 1.2.1 duplicated every received keymap FD
without closing the original. Current installations load a bridge-local
backport of upstream commit `ee27dd5c92e4e9496a36ca2d4112049fe02d2269` into
GNOME RDP only. `scripts/verify.sh` confirms the running process mapped that
library, and a timed verifier rejects renewed descriptor growth.

The 65536 soft limit and 4096-descriptor relay rebuild remain as defense in
depth. Rerun the installer if the verifier reports a 1024 limit, a missing
backport, or installed-source drift. The threshold is configurable with
`--grd-fd-restart-threshold`; `0` disables only the fallback guard, not the
backport.

## Individual keys lag or disappear, but direct RDP is normal

Run:

```bash
uu-remote network
```

The output includes the completed session time. A `stale` note means it is
historical evidence and does not describe the current idle or newly restarted
bridge. `controller/host relay geography: cross-region` means the controlling
device's VPN, proxy, or internet exit may have sent the two ends to distant
relay regions. The command reports only the match status, not either location.

This distinction matters. Direct RDP bypasses UU's controller-to-host network
path, while the UU route adds its own P2P or relay transport before the local
Wine-to-RDP bridge. If the report says `relay (forced by controller)` and its
delay approaches 300 ms, compare that with any `key watchdog` line. UU may
release a key after its own 300 ms safety interval before a delayed key-up
arrives.

Do not compensate by replaying keys in the host bridge. A late original event
would then create duplicate text. Prefer Automatic/P2P in the controlling UU
client when it is available, but compare the measured result: NAT or firewall
rules can block P2P and make automatic relay fallback slower. The host bridge
must retain its proven original-call-then-broker fallback for ordinary input.
Do not select that route from service-side relay-window visibility: Wine may
hide the window from that token even while the relay is healthy.

On a multi-homed host, also compare Ubuntu's defaults with the address UU chose:

```bash
ip -4 route show default
./scripts/verify.sh --quick
```

UU under Wine can bind the first enumerated adapter rather than the interface
on Ubuntu's lowest-metric default route. If logs and a controlled comparison
confirm that mismatch, enable the opt-in process-local filter:

```bash
./install.sh --skip-packages --skip-account-login \
  --network-interface default
```

The verifier must report `default -> INTERFACE`. The setting is resolved at
service start and the existing supervisor compares it with Ubuntu's preferred
interface every ten seconds. A genuine change causes one complete relay
restart on the new route; no second loop or service is added. It is fail-open
if no usable default exists, and it does not modify host routes or other
applications. To restore UU's original all-adapter view:

```bash
./install.sh --skip-packages --skip-account-login \
  --network-interface all
```

## Server restarts every four minutes

Check for Wine's unimplemented event-log abort:

```bash
rg 'EvtOpenPublisherMetadata, aborting' \
  ~/.local/state/uu-remote-bridge/winlogon.log
```

Old occurrences can remain because logs append. Record the server PID, wait
270 seconds, and compare it, or run:

```bash
scripts/verify.sh
```

If the PID still changes, confirm the event-log compatibility hook initialized
for the current PID. The launcher re-injects automatically after a UU restart.

## Video is black

Check each hop:

```bash
systemctl --user status uu-remote-bridge.service
/usr/bin/grdctl status
rdp_port="$(sed -n 's/^UURB_RDP_PORT=//p' \
  ~/.config/uu-remote-bridge/environment)"
ss -ltnp | rg ":${rdp_port:-3390}\\b"
tail -80 ~/.local/state/uu-remote-bridge/gnome-remote-desktop.log
tail -80 ~/.local/state/uu-remote-bridge/freerdp.log
tail -80 ~/.local/state/uu-remote-bridge/openbox.log
```

GNOME RDP must mirror the primary desktop, allow input, and own the configured
port. The daemon is a child of `uu-remote-bridge.service`; an idle
`gnome-remote-desktop.service` on a different D-Bus is not sufficient. The
relay window must be named `Ubuntu-Desktop-Relay`:

```bash
pgrep -af '/usr/bin/Xvfb :[0-9]+'
```

Automatic display selection starts at `:20` and skips occupied X sockets and
lock files. If a fixed display is configured and occupied, the service fails
clearly instead of attaching to or disrupting that display.

The Windows FreeRDP client requires `SDL_RENDER_DRIVER=software` under Xvfb.
`OPENSSL_MODULES` points to the copied provider directory, while the pinned
WinPR build uses internal MD4/MD5/RC4 for NTLM if Wine cannot load the legacy
provider.

On XRDP, confirm the journal says which private desktop was selected:

```text
GNOME Desktop Sharing is relaying x11 :10.0.
```

The launcher reads this from the live `gnome-shell` process. Do not hard-code
an old `/tmp/dbus-*` address; it changes after logout or reboot.

## Service is active but UU stays offline after its server exits

Current versions treat a missing `GameViewerServer.exe` lasting ten seconds,
or a failed DLL re-injection after a server PID change, as a bridge failure.
Systemd then restarts the complete relay. Confirm the journal contains the
recovery reason rather than an indefinitely idle service:

```bash
uu-remote logs
```

If shutdown previously waited for `winedevice.exe`, rerun the current
installer. It installs a bounded prefix-scoped cleanup helper. The helper
matches both the current UID and exact UU `WINEPREFIX`; it does not terminate
Wine programs from other prefixes.

## Device appears offline

The UU GUI sends the account login IPC message after the service starts. The
launcher performs this automatically and again after a server PID change.
Confirm the account has been authenticated once:

```bash
uu-remote login
```

This temporarily stops the hidden relay, opens the official UU client on the
current visible desktop, and restores the bridge when the client closes.
Complete sign-in, then close the GUI normally. Forcibly terminating it during
its bootstrap handshake can ask the background server to exit; the supervisor
will recover, but the device can be briefly offline.

## GNOME RDP authentication fails

The UU bridge uses a separate local RDP credential from the login keyring:

```bash
/usr/bin/secret-tool lookup service uu-desktop-bridge username "$USER" >/dev/null
/usr/bin/grdctl status
```

Clear only the bridge's keyring item, then rerun the installer to prompt for
and store a replacement credential:

```bash
secret-tool clear service uu-desktop-bridge username "$USER"
./install.sh --skip-packages --skip-account-login
```

Do not place the credential in the systemd unit or launcher.

## FreeRDP reports NLA or SSPI errors

Confirm these files exist together:

```text
libwinpr3.dll
libcrypto-3-x64.dll
libssl-3-x64.dll
libcjson-1.dll
liburiparser-1.dll
winpr-sspi-shim.dll
ossl-modules/legacy.dll
sdl-freerdp.exe
```

Rebuild them with `scripts/build-winpr.sh` and `scripts/build-compat.sh`; do
not mix a different major WinPR DLL into the runtime directory.

## Restore upstream UU files

```bash
./uninstall.sh
```

This restores the audited backups and removes the bridge while preserving the
dedicated UU Wine prefix. `--purge` removes the prefix and its account state.
