# Architecture

## Goal

UU Remote's Windows host can capture a Wine desktop, but its Windows kernel
input and display drivers cannot operate a native Ubuntu GNOME session. The
bridge therefore gives UU one ordinary Windows window to capture and
translates UU's user-mode input into that same window.

## Data path

```text
Mobile, Windows, or macOS UU controller
                 |
                 | UU signaling and media
                 v
GameViewerServer.exe (Wine, DISPLAY=:20)
        |                         |
        | captures pixels         | SendInput IAT hook
        v                         v
Ubuntu-Desktop-Relay       uu-input-bridge.dll
(sdl-freerdp.exe)                  |
        |                          | bounded INPUT records
        | RDP on 127.0.0.1         v
        |                    \\.\pipe\uurb-input-v1
        |                          |
        |                          v
        |                    uu-input-broker.exe
        |                          |
        +--------------------------+
                 Wine/X11 input
                         |
                         v
GNOME Remote Desktop, TCP 3390
                         |
                         v
Logged-in GNOME desktop (Wayland or Xorg/XRDP)
```

UU's separate terminal channel follows a smaller path:

```text
UU Terminal -> Wine ConPTY helper -> uu-terminal-proxy.exe
            -> authenticated 127.0.0.1 socket -> native forkpty login shell
```

## Components

### Private X11 display

`Xvfb` supplies a 1920x1080 display by default, and Openbox supplies basic
window management. In automatic mode the launcher chooses the first unused X
display from `:20` through `:99`; a validated fixed display and resolution can
also be persisted by the installer. Both UU and the Windows SDL FreeRDP client
use this display. UU therefore captures the FreeRDP window as if it were a
normal Windows desktop application.

After a forced Xvfb exit, cleanup removes a stale socket/lock only when the
lock still names the exact Xvfb PID started by this bridge and that PID no
longer exists. It never deletes an unowned display lock.

The X server uses an `Xauthority` cookie and `-nolisten tcp`; it is not exposed
as a network service.

### Local management window

`uu-remote open` keeps every process in the dedicated Wine prefix on the
private X display. It maps the existing `GameViewer.exe` management window,
binds `x11vnc` to that one X window and IPv4 loopback, and opens the result in
TigerVNC on the logged-in GNOME desktop. The sidecar never exports the private
root window, so the physical desktop cannot recurse through its own relay.

The launcher holds a per-user lock to prevent duplicate viewers. While it is
open, a runtime marker permits the management window to be raised; the input
broker can still focus the relay before each controller input. Closing or
terminating the viewer stops the sidecar, minimizes the management window,
removes the marker, and raises `Ubuntu-Desktop-Relay`. This design avoids
Wine's process-global foreground state spanning two unrelated X displays,
which otherwise makes `SetForegroundWindow` fail even when X11 reports the
relay as active.

The full private-display noVNC console remains an explicit diagnostic command,
`uu-remote console`; it is not the desktop-launcher path.

### External current-desktop view

GNOME's desktop-sharing RDP endpoint is already occupied by the internal
`Ubuntu-Desktop-Relay` client. A second RDP client cannot join that same
desktop concurrently; GNOME's remote-login endpoint creates a separate login
session instead.

`uu-remote-console relay` provides a bounded path for an authorized Mac:

```text
macOS Screen Sharing
        |
        | localhost:15922
        v
passwordless SSH tunnel
        |
        | Ubuntu 127.0.0.1:5922
        v
x11vnc, one Ubuntu-Desktop-Relay window
        |
        v
existing SDL FreeRDP client -> current GNOME desktop
```

The helper retrieves the existing bridge credential once, explicitly limits
it to classic VNC's eight-byte password width, stores x11vnc's obscured form in
a mode-0600 file, and requires VNC authentication in addition to SSH. It
tolerates short readiness probes, waits for a real viewer, keeps the relay
focused while connected, and exits after the viewer has been absent for five
seconds. The listener remains IPv4 loopback-only on Ubuntu; SSH provides the
Mac-side IPv4 and IPv6 localhost sockets.

### GNOME RDP relay

GNOME Remote Desktop mirrors the existing GNOME session on port 3390. The
Windows FreeRDP build connects to `127.0.0.1`, so this second hop stays on the
host. GNOME performs the final desktop capture and input integration.

XRDP commonly starts GNOME on a private D-Bus instead of the persistent
systemd user bus. The launcher discovers the D-Bus, display, and session type
from the live user-owned `gnome-shell` process and starts GNOME Remote Desktop
on that exact bus. This also works for a normal Wayland login and prevents an
idle daemon on the wrong bus from being mistaken for a working relay.

The native GNOME daemon receives Linux's OpenSSL configuration and a provider
directory discovered from the host `openssl` executable; the Windows FreeRDP
client receives its separate Wine path. Keeping those environments separate
is required for NTLM/NLA authentication and avoids architecture-specific host
paths.

The relay uses NetEase-independent GNOME credentials kept in the login
keyring. FreeRDP reads the password from standard input, not its command line,
and pins the SHA-256 fingerprint of GNOME's configured TLS certificate.

### FreeRDP SSPI compatibility

The Jenkins Windows SDL client uses WinPR's SSPI ABI. Wine's native SSPI and
WinPR disagree about the private handle-name representation during NLA. The
small `winpr-sspi-shim.dll` forwards to `InitSecurityInterfaceExA/W` from
`libwinpr3.dll` and normalizes those handles before and after credential and
context operations.

### UU direct-input patch

Windows UU normally prefers its signed `gvinput.sys` HID driver. That driver
cannot load under Wine. Four validated instruction edits force UU's existing
user-mode `SendInput` path instead. The patch is limited to 4.33.0.8907 and is
described in `reverse-engineering.md`.

### Input broker

The UU service creates GameViewerServer with a token for which Wine rejects
`SendInput` with error 5. `uu-input-bridge.dll` first calls the original API;
only when that call fails does it forward the exact bounded `INPUT` array to a
normal user Wine process over a local named pipe. That fallback is intentional:
the service process cannot reliably use relay-window visibility to choose the
route across Wine's desktop boundary. The broker requests focus for the relay
window and confirms it became the foreground window within a bounded 300 ms
before calling `SendInput`. It returns the real count and error code to UU only
after that boundary succeeds.

On an X11 target with `UURB_KEYBOARD_ROUTE=x11`, the broker sends bounded
keyboard, mouse, or mixed arrays to `uu-x11-input` over a token-authenticated
loopback socket. Physical keys are mapped directly. Unicode phone-text arrays
that are representable by the active layout are normalized into ordinary
virtual-key chords. In the default adaptive mode, newline, tab, CJK, emoji,
and other non-representable text instead cross the same authenticated helper
as a bounded semantic-text request. The helper validates and converts that
request to UTF-8, owns the target `CLIPBOARD` and `PRIMARY` selections through
`xclip`, and emits one paste chord only after `XGetSelectionOwner` confirms
both new owners.
An ownership timeout fails closed instead of pasting stale user data. The
native helper otherwise preflights the complete translated
array, maps the established XFree86 scan-code set to X11 keycodes, and maps
Windows relative/normalized motion, buttons, vertical and horizontal wheel
events to XTEST on the discovered live desktop. A helper that
is absent, unreachable before injection, or presented with an unsupported
event safely falls back to the selected desktop relay. A communication failure
after injection begins returns an error without replay, preventing duplicate
input. Held keys and buttons are released when the broker disconnects, and
helper exit restarts the supervised bridge.

The direct route removes the nested Wine/desktop-relay conversions for the
input categories that failed on the affected XRDP workstation. It is not
enabled globally because the original RDP route is known-good on other hosts
and is still required for Wayland targets.

No key code, Unicode character, clipboard payload, or text is written to the
diagnostic logs. Semantic text exists only in process memory and the user's
target clipboard.

### Native terminal bridge

Wine's compatibility `powershell.exe` exits successfully without providing a
shell, which made a valid UU terminal request immediately display exit code
0. The installed `GameViewer/bin/powershell.exe` is therefore a small Windows
stdio proxy. It retains UU's authenticated terminal and ConPTY transport while
forwarding bytes and resize events to `uu-terminal-bridge` on IPv4 loopback.

The native helper authenticates a fresh 256-bit token inherited from the
supervised launcher, limits concurrency to four sessions, and uses `forkpty`
to start the current Ubuntu user's interactive login shell in the user's home.
Neither helper logs terminal payloads. The token is absent from command lines
and ready files. This design avoids an SSH listener, SSH key, stored password,
or extra account boundary. See
[Native Ubuntu terminal through UU Remote](native-ubuntu-terminal.md).

### Phone text input

UU exposes two mobile keyboard paths. Its computer-keyboard panel emits normal
Windows key events and reaches the input broker unchanged. The phone's native
IME instead submits batches marked `KEYEVENTF_UNICODE`. SDL FreeRDP consumes
physical scancodes and misreads Wine's synthetic Unicode events, typically as
one repeated letter or punctuation key. The bridge routes Unicode batches
directly to the broker, where each representable character is converted with
`VkKeyScanW` into an ordinary virtual-key chord. On `rdp`, character chords are
submitted separately with a persistent, configurable 8 ms delay so the
SDL/RDP event loop can consume each chord before UU sends the next one. On
`x11`, representable text is preflighted and injected through the authenticated
XTEST helper, bypassing both nested RDP keyboard conversions. Adaptive text
that has no safe key chord—or that contains a line break—is placed on the
target clipboard and pasted, preserving its Unicode and multiline semantics.
The original request count is returned to UU only after the selected boundary
accepts the complete request.

Physical-key segments are unchanged by default. On the RDP route, an optional
0-50 ms delay can add back-pressure after each accepted segment. On the direct
X11 route, that value is only a minimum down-to-up hold time. Neither route
retries or synthesizes input.

Diagnostics use separate bounded quotas for phone text, physical keyboard,
mouse, and other calls, and successful events are not synchronously forced to
disk. This keeps early mouse traffic from both adding input latency and hiding
later keyboard telemetry. Failures are still flushed immediately. Logs contain
only category, counts, route, focus state, pacing and boundary timing metadata,
and result codes; they never contain the key or character value.

The separate RDP `cliprdr` channel remains enabled for normal copy and paste;
it is not the transport used by UU's native phone keyboard in 4.33.0.8907.

### Wine event-log compatibility

UU periodically calls `EvtOpenPublisherMetadata`. Wine 11 marks that function
unimplemented and aborts the caller. The injected DLL replaces only that IAT
entry and returns `ERROR_EVT_PUBLISHER_METADATA_NOT_FOUND`, which is the normal
Windows API failure shape. UU handles it and continues running.

### Process supervision

The launcher waits on all critical bridge processes. A complete relay restart
is requested if GNOME Remote Desktop, Xvfb, Openbox, FreeRDP, the input broker,
or fake Winlogon process exits. A lightweight inner supervisor watches
GameViewerServer's Linux PID, re-injects the compatibility DLL after a UU
restart, and sends the account bootstrap IPC again. If the server remains
absent for ten seconds or re-injection fails, the inner supervisor exits so
systemd rebuilds the complete relay instead of leaving a false-active service.
The same existing supervisor samples GNOME Remote Desktop's descriptor count
once every ten seconds. The user unit raises its descriptor limit to 65536,
and the launcher repeats that soft-limit raise after entering the user
context. This second step matters when an optional system application-profile
wrapper crosses `runuser`/PAM, which may otherwise reset the soft limit to
1024. Failure to raise the limit is logged but never prevents the bridge from
starting. The relay is rebuilt at a persistent default threshold of 4096
before `libei` can lose keyboard injection to `EMFILE`.

The primary repair is an isolated backport of upstream libei commit
`ee27dd5c92e4e9496a36ca2d4112049fe02d2269`. Ubuntu 24.04's libei 1.2.1
duplicated each keymap descriptor but did not close the descriptor received
from the protocol demarshaller. The installer builds 1.2.1 from a pinned,
hash-verified archive with that one-line close and places it inside the bridge
prefix. Only the supervised GNOME RDP process receives its directory through
`LD_LIBRARY_PATH`; Ubuntu's system library is not replaced. The limit and
restart threshold remain independent containment if another descriptor leak
appears.

Verification accepts either the ordinary systemd user unit or the known
system application-profile unit. A profile may place the relay in a private
network namespace, so the checker reads the matching GNOME RDP process's
`/proc/PID/net/tcp*` tables and requires a listening socket on the configured
port. It does not require that private listener to appear in the host
namespace.
Shutdown first stops the supervised producers, then asks Wine's own server to
exit and applies a bounded fallback only to Wine executables owned by the
current user whose environment names the dedicated UU prefix. Other Wine
prefixes are deliberately excluded.

The user unit is enabled under `default.target`. It can therefore survive the
different target wiring used by physical GNOME, XRDP, and persistent user
managers. If no user GNOME Shell exists yet, it waits quietly and attaches when
the desktop becomes available.

Desktop identity is independent of the private UU canvas display. By default,
the launcher follows the graphical environment imported into the persistent
user manager and retains its historical newest-session fallback. A persistent
`UURB_DESKTOP_TARGET=xrdp` instead matches the live GNOME Shell's logind
session service (`xrdp-sesman`); `physical` matches a seat-attached/GDM
session, and `:N` matches an exact X display. Explicit targets fail closed by
waiting: they never substitute another logged-in desktop. This lets Windows
RDP and direct UU control the same long-lived XRDP session without restarting
XRDP, GNOME Shell, or any application window.

If the normal `gnome-remote-desktop.service` was active before the bridge, the
launcher records that state, temporarily replaces it with the session-aware
relay, and restores it during cleanup. Stopping UU therefore does not silently
leave an existing native desktop-sharing service disabled.

The fake `winlogon.exe` exists because GameViewerService expects an active
Windows session token source. It only sleeps; it does not authenticate or
grant additional Unix privileges.

The replacement GameViewerHealthd also only sleeps. The upstream monitor
mistook Wine's health reporting for a hung main loop and terminated a healthy
server. Systemd and the inner PID supervisor provide the lifecycle monitoring
instead.

### Optional unattended boot

The bridge user unit starts under `default.target` and waits for a real GNOME
Shell. In unattended mode, GDM creates that desktop through automatic login.
A separate oneshot unit asks systemd to decrypt a TPM2-bound credential and
unlocks the existing GNOME login keyring over the Secret Service D-Bus
interface.

The bridge has a hard startup dependency on that unit. It runs after
`gnome-keyring-daemon.service` and before both the packaged GNOME Remote
Desktop service and the bridge's session-aware relay. The relay can therefore
read its ordinary credential before it connects. The complete sequence and
rollback are documented in `unattended-startup.md`.
