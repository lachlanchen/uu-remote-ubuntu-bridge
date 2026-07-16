# Architecture

## Goal

UU Remote's Windows host can capture a Wine desktop, but its Windows kernel
input and display drivers cannot operate an Ubuntu Wayland session. The bridge
therefore gives UU one ordinary Windows window to capture and translates UU's
user-mode input into that same window.

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
Logged-in GNOME Wayland desktop
```

## Components

### Private X11 display

`Xvfb` supplies a 1920x1080 display on `:20`, and Openbox supplies basic
window management. Both UU and the Windows SDL FreeRDP client use this display.
UU therefore captures the FreeRDP window as if it were a normal Windows
desktop application.

The X server uses an `Xauthority` cookie and `-nolisten tcp`; it is not exposed
as a network service.

### GNOME RDP relay

GNOME Remote Desktop mirrors the existing Wayland session on port 3390. The
Windows FreeRDP build connects to `127.0.0.1`, so this second hop stays on the
host. GNOME performs the final desktop capture and input integration.

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

### Wine event-log compatibility

UU periodically calls `EvtOpenPublisherMetadata`. Wine 11 marks that function
unimplemented and aborts the caller. The injected DLL replaces only that IAT
entry and returns `ERROR_EVT_PUBLISHER_METADATA_NOT_FOUND`, which is the normal
Windows API failure shape. UU handles it and continues running.

### Process supervision

The launcher waits on all critical bridge processes. A complete relay restart
is requested if Xvfb, Openbox, FreeRDP, the input broker, or fake Winlogon
process exits. A lightweight inner supervisor watches GameViewerServer's Linux
PID, re-injects the compatibility DLL after a UU restart, and sends the account
bootstrap IPC again.

The fake `winlogon.exe` exists because GameViewerService expects an active
Windows session token source. It only sleeps; it does not authenticate or
grant additional Unix privileges.

The replacement GameViewerHealthd also only sleeps. The upstream monitor
mistook Wine's health reporting for a hung main loop and terminated a healthy
server. Systemd and the inner PID supervisor provide the lifecycle monitoring
instead.
