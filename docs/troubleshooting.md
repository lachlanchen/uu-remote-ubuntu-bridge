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
ss -ltnp | rg ':3390\b'
tail -80 ~/.local/state/uu-remote-bridge/gnome-remote-desktop.log
tail -80 ~/.local/state/uu-remote-bridge/freerdp.log
tail -80 ~/.local/state/uu-remote-bridge/openbox.log
```

GNOME RDP must mirror the primary desktop, allow input, and own the configured
port. The daemon is a child of `uu-remote-bridge.service`; an idle
`gnome-remote-desktop.service` on a different D-Bus is not sufficient. The
relay window must be named `Ubuntu-Desktop-Relay`:

```bash
DISPLAY=:20 xdotool search --name Ubuntu-Desktop-Relay getwindowname
```

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
