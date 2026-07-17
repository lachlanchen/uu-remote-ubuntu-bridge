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
normal user Wine process over a local named pipe. The broker focuses the relay
window and calls `SendInput`, returning the real count and error code to UU.

No key code, Unicode character, clipboard payload, or text is written to the
diagnostic logs.

### Phone text input

UU exposes two mobile keyboard paths. Its computer-keyboard panel emits normal
Windows key events and reaches the input broker unchanged. The phone's native
IME instead submits batches marked `KEYEVENTF_UNICODE`. SDL FreeRDP consumes
physical scancodes and misreads Wine's synthetic Unicode events, typically as
one repeated letter or punctuation key. The bridge routes Unicode batches
directly to the broker, where each representable character is converted with
`VkKeyScanW` into an ordinary virtual-key chord before it reaches SDL FreeRDP.
The original request count is returned to UU only after every translated event
is accepted. Unsupported characters fail explicitly rather than being emitted
as an unrelated key.

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
Shutdown first stops the supervised producers, then asks Wine's own server to
exit and applies a bounded fallback only to Wine executables owned by the
current user whose environment names the dedicated UU prefix. Other Wine
prefixes are deliberately excluded.

The user unit is enabled under `default.target`. It can therefore survive the
different target wiring used by physical GNOME, XRDP, and persistent user
managers. If no user GNOME Shell exists yet, it waits quietly and attaches when
the desktop becomes available.

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
