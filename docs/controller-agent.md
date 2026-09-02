# UU Controller CLI and Remote Agent

## Scope

UU Remote 4.34.0.8979 includes `uuyc-cli.exe` beside the official controller.
It talks to the already authenticated UU GUI/server through local IPC. The
bridge installs `uu-agent`, a small launcher that discovers the live private
X display, Xauthority file, Wine prefix, and controller executable from the
systemd service. It does not implement or emulate UU's network protocol.

The observed command surface is:

```text
version
user info|wallet
device list|connect|disconnect|status
cloudpc list|launch|shutdown|connect|disconnect
echo
term
```

This is an observed vendor interface, not a stability promise. Run
`uu-agent cli --help` after every upstream UU update and keep automation
bounded to the commands that the installed version reports.

## Local Wrapper

```bash
uu-agent version
uu-agent list
uu-agent status
uu-agent runtime
```

`runtime` prints paths and a display number, but no account or device
identifier. `list` can print private device names and IDs; do not paste it
into issues, CI logs, or a public repository.

The wrapper also provides private-display diagnostics:

```bash
uu-agent windows
uu-agent focus '网易UU远程'
capture="$(uu-agent snapshot)"
printf '%s\n' "$capture"
```

Captures default to `~/.local/state/uu-remote-agent/captures`, use mode `0600`,
and must stay outside Git.

## Mac Terminal Agent

Prefer the terminal agent for deterministic Mac inspection and builds:

```bash
uu-agent term 'Mac device name' --shell zsh --new-session
```

Non-interactive input is supported by the tested CLI:

```bash
printf '%s\n' \
  'sw_vers' \
  'xcodebuild -version' \
  'xcrun simctl list devices available' \
  'exit' |
  uu-agent term 'Mac device name' --shell zsh --new-session
```

Select an exact device name from the live list. Never hard-code a controller
device ID in a script or document. A terminal session has the authority of the
logged-in remote user; do not send passwords, signing secrets, recovery keys,
or destructive disk commands through reusable scripts.

The current CLI advertises `powershell`, `cmd`, `zsh`, and `bash`. Actual
support depends on the controlled platform and UU host version. In particular,
the tested Windows 7 host reports that its terminal agent is unsupported.

## Terminal into this Ubuntu bridge host

The same UU terminal panel can now control the Ubuntu machine that hosts this
Wine bridge. Select `PowerShell`: the name is the vendor compatibility entry
point, but the installed proxy opens the Ubuntu user's native interactive
shell. It does not run Wine PowerShell and does not use SSH.

The old immediate `exit 0` was caused by Wine's placeholder
`powershell.exe`, not by UU networking. Installation, security boundaries,
tests, and rollback are documented in
[Native Ubuntu terminal through UU Remote](native-ubuntu-terminal.md).

## GUI Fallback

Use GUI control only when the task inherently needs Xcode, Simulator, System
Settings, keychain approval, or another visual surface:

```bash
uu-agent connect 'Mac device name'
uu-agent windows
uu-agent snapshot
```

Controller success means only that a request reached the local UU process.
Confirm that a remote window appeared before sending input. Coordinates are
resolution- and version-dependent, so scripts must rediscover the current
window and inspect a fresh private screenshot. Never automate account
publication, a purchase, firmware flashing, credential entry, or a destructive
confirmation dialog.

## Headless Mac: Current Failure Evidence

The operator clarified that several monitor-free connections to the 7050 iMac
were attempts, not successful sessions. Each remained at route optimization.
Fresh controller evidence on 2026-07-27 showed:

- UU signaling and a TURN relay completed;
- the Mac reported one screen but zero physical and zero virtual screens;
- every negotiated video stream remained at `0x0`, `0 bps`, and zero decoded
  frames until the controller ended the session;
- a separate UU `term` attempt timed out waiting for the remote open response;
- LAN SSH and macOS Screen Sharing refused connections.

The connection therefore reaches the Mac, but there is currently no usable
framebuffer or independent command path. This supersedes the earlier statement
that headless GUI access was verified on this host.

Temporarily attach a monitor or display-emulator plug. Once UU renders again:

1. Enable Remote Login and install a dedicated SSH public key.
2. Install and start a persistent virtual screen.
3. Reboot once, disconnect the monitor, and verify video, input, terminal, and
   SSH independently.

BetterDisplay supports virtual screens for headless remote access. On macOS
13.2 or later, install it from its official Homebrew cask:

```bash
brew install --cask betterdisplay
open -a BetterDisplay
```

This repository includes a guarded Mac-side bootstrap. It is read-only unless
`--execute` is supplied:

```bash
./scripts/bootstrap-headless-macos.sh
./scripts/bootstrap-headless-macos.sh --execute
```

Run it only after a temporary monitor or display-emulator plug restores one
working GUI session. The script can also enable Remote Login and install one
public key, but those options are explicit and never accept or store a
password:

```bash
./scripts/bootstrap-headless-macos.sh --execute \
  --enable-remote-login \
  --public-key-file /path/to/dedicated-key.pub
```

Create one named `1920x1080` virtual screen, configure BetterDisplay to start
at login, and verify that macOS and UU both capture it before removing the
temporary display. BetterDisplay's current CLI supports
`create -type=VirtualScreen`, `virtualScreenName`, `useResolutionList`,
`resolutionList`, and `virtualScreenHiDPI`. Query the installed version's help
before scripting those parameters.

## Failure Interpretation

| Observation | Meaning | Next action |
| --- | --- | --- |
| `device list` says offline | UU host heartbeat is absent | Check power, network, login, and host service |
| Online, terminal open timeout | Host service is reachable but the terminal-agent session did not open | Test GUI separately; use independent SSH if already enabled |
| GUI remains optimizing; video stays `0x0` | Signaling works but no framebuffer arrives | Temporarily attach a display, then configure a persistent virtual screen |
| Terminal works, GUI stalls | Agent is healthy; capture/display path is not | Inspect permissions and display state for the reproduced GUI failure |
| GUI works, terminal unsupported | Platform/version lacks the terminal agent | Use GUI once to install SSH |
| CLI exits `2` | Local controller IPC is unavailable | Verify `uu-remote-bridge.service` and UU server |
| CLI exits `5` | Vendor operation timed out | Do not retry destructive actions blindly |

## Security Boundary

`uu-agent` neither stores verification codes nor bypasses controlled-host
authentication. UU account state remains in the dedicated Wine prefix. Device
IDs, screenshots, terminal transcripts, and account output are operator data
and must stay out of source control.
