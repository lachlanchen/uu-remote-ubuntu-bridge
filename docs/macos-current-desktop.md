# macOS current-desktop access

## Purpose

The UU bridge already uses GNOME Desktop Sharing internally:

```text
UU private X display -> SDL FreeRDP -> current GNOME desktop
```

GNOME does not let a second RDP client join that same desktop concurrently.
Its remote-login service is a different endpoint and creates a separate login
session. The Mac launcher therefore reuses the existing relay window instead
of opening another RDP connection.

## Data path

The default **Current Desktop** action in
`scripts/macos-connect-7090.applescript` creates this path:

```text
Screen Sharing on the Mac
  -> localhost:15922
  -> passwordless SSH alias glassagent-ubuntu
  -> Ubuntu 127.0.0.1:5922
  -> x11vnc for Ubuntu-Desktop-Relay only
  -> current physical GNOME desktop
```

Ubuntu's VNC listener is IPv4 loopback-only. The Mac SSH client creates both
IPv4 and IPv6 localhost listeners, which avoids Screen Sharing's IPv6-first
connection failure. `ExitOnForwardFailure`, an eight-second SSH timeout, and
three keepalive failures bound a dead connection.

## Install the Mac app

Copy the maintained source to the Mac and compile it:

```bash
scp scripts/macos-connect-7090.applescript \
  glassagent-mac:/tmp/macos-connect-7090.applescript
ssh glassagent-mac \
  'osacompile -o "$HOME/Desktop/Connect to 7090.app" \
  /tmp/macos-connect-7090.applescript'
```

The checked-in launcher is specific to the validated 7090 and its SSH alias.
Change the properties at the top before compiling for another host.

The launcher resolves `OptiPlex-7090.local` with mDNS instead of retaining a
DHCP address. Router or subnet changes therefore do not require editing the
app as long as both computers are on the same multicast-capable LAN. Keep the
SSH alias pinned with `HostKeyAlias`; a changing address must never weaken host
key verification.

For **Separate Login (RDP)**, the launcher uses Windows App or Microsoft Remote
Desktop when installed. On an older Mac with Royal TSX, it generates a small
temporary `.rdp` file containing the same mDNS hostname and opens it with Royal
TSX. No Windows App bookmark or stale numeric address is required.

The first **Current Desktop** connection asks for the same password configured
for the bridge. On the validated host it is stored by Screen Sharing in the
Mac login keychain for `localhost:15922`. Select **Remember password**; later
connections require no prompt while that keychain is unlocked.

## Lifecycle

`uu-remote-console relay`:

1. verifies the bridge and its private Xauthority;
2. identifies the visible `Ubuntu-Desktop-Relay` window;
3. creates a mode-0600 VNC authentication file from the existing bridge
   keyring credential when one does not exist;
4. starts x11vnc on `127.0.0.1:5922`;
5. ignores brief TCP readiness probes and waits for a sustained viewer;
6. keeps the relay focused while that viewer is connected;
7. exits five seconds after the last viewer disconnects.

The helper never opens a LAN listener. The VNC password file is only obscured,
not encrypted, so SSH remains the primary access boundary.

## Diagnose

From the Mac:

```bash
ssh -o BatchMode=yes glassagent-ubuntu \
  '~/.local/bin/uu-remote-console relay-port'
```

Expected output is `5922`. While connected:

```bash
lsof -nP -iTCP:15922 -sTCP:LISTEN
```

Both `[::1]:15922` and `127.0.0.1:15922` are expected. On Ubuntu:

```bash
ss -ltnp | grep '127.0.0.1:5922'
```

If the Mac receives a black view, inspect the shortcut source. A forward to
`[::1]:5900` is the obsolete path and may reach an unrelated Xvfb desktop.

If the display becomes recursively nested during testing, close any
Ubuntu-to-Mac Remmina window. The Mac is showing the current Ubuntu desktop,
and that desktop is otherwise showing the Mac; neither endpoint is blank.

Use **Separate Login (RDP)** only when a separate GNOME session is intended.
