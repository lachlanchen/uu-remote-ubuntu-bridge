# UU Remote Ubuntu Bridge

An experimental compatibility bridge that lets the official Windows UU
Remote client display and control an existing GNOME desktop from Wine.

The working path is:

```text
UU controller
  -> GameViewerServer.exe in an isolated Wine prefix
  -> local SendInput broker
  -> Windows SDL FreeRDP in the same private X11 display
  -> GNOME Remote Desktop on localhost
  -> the logged-in Ubuntu Wayland desktop
```

This is not a native UU Linux port. It is a version-locked workaround tested
on Ubuntu 24.04.2, GNOME 46, Wine 11.0, and UU Remote 4.33.0.8907. The patcher
refuses any other UU executable.

## Current result

- Live GNOME desktop video at 1920x1080
- Mouse and keyboard control through UU
- Persistent account registration after service restart
- No four-minute Wine event-log crash
- Automatic re-injection if UU replaces its server process
- User-level systemd startup and restart handling

## Install

Run from a logged-in GNOME desktop session:

```bash
./install.sh
```

The installer uses `sudo` only for Ubuntu/Wine packages. It prompts for a
local GNOME RDP relay password and stores it in the user's login keyring. It
downloads the audited UU installer from NetEase's official release endpoint,
builds the compatibility code, installs a user service, and opens UU once if
an account sign-in is needed.

To reuse the already downloaded audited installer:

```bash
./install.sh --uu-installer ~/Downloads/UU-Remote/uuyc_4.33.0.exe
```

Useful commands:

```bash
uu-remote status
uu-remote restart
uu-remote logs
scripts/verify.sh --quick
scripts/verify.sh
```

The default verification waits 270 seconds to cross UU's former four-minute
failure interval. Use `--quick` for installation checks.

## Safety model

The bridge preserves UU and GNOME authentication. It does not edit account
databases, bypass login, install a kernel input driver, or expose a new remote
control protocol. The input pipe exists only inside the user-owned Wine
prefix; requests are bounded; logs contain event types and flags, never typed
characters. RDP credentials remain in the GNOME keyring and are not committed.

The installer verifies upstream hashes and exact machine-code signatures,
backs up both changed UU executables, and fails closed on unknown releases.
See [Security](docs/security.md) before deploying outside a trusted personal
machine.

## Repository contents

- `src/`: compatibility DLL, broker, injector, service helper, and SSPI shim
- `scripts/patch-gameviewer.py`: audited patch, verification, and restore
- `scripts/build-compat.sh`: builds all original compatibility code
- `scripts/build-winpr.sh`: builds WinPR and assembles the FreeRDP runtime
- `scripts/uu-remote-bridge`: supervised desktop relay
- `install.sh` and `uninstall.sh`: installation and reversible removal
- `docs/reverse-engineering.md`: exact `strings`, `xxd`, and `objdump` record

No proprietary UU binary or third-party compiled artifact is stored here.

## Documentation

- [Architecture](docs/architecture.md)
- [Reverse-engineering record](docs/reverse-engineering.md)
- [Windows reference comparison](docs/windows-reference.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Security](docs/security.md)

## Removal

Restore the original UU executables and remove only bridge files:

```bash
./uninstall.sh
```

`./uninstall.sh --purge` also deletes the dedicated Wine prefix, bridge
credential, and GNOME RDP enablement. That removes the UU account state in the
prefix.
