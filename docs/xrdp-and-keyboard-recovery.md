# XRDP Client Stall and UU Keyboard Recovery

This note records a validated recovery from two symptoms observed together:

- Windows App discovered the Ubuntu XRDP endpoint but remained on
  **Configuring** indefinitely.
- UU Remote video and pointer input worked, while fast physical-key input
  omitted keystrokes.

The procedure is intentionally narrow. It does not change NetworkManager,
routes, DNS, the firewall, the physical desktop, or system libraries.

## What the evidence showed

XRDP accepted the controller's TCP connection and completed TLS, but its log
stopped before capability exchange, authentication, or session selection.
Several connection-handler processes remained attached to established port
3389 sockets. An independent local FreeRDP authentication-only probe advanced
through capability negotiation immediately. The server and desktop were
therefore responsive; the remote Windows App process had retained stale RDP
state after running for several days.

VNC was not a port conflict. XRDP listened on TCP 3389, while the VNC mirror
used a separate localhost-only RFB port. A VNC process can still depend on the
same X display, however, so replacing an XRDP session can end that particular
VNC mirror even though the two network listeners do not conflict.

## Safest recovery order

Inspect the current attempt without changing the desktop:

```bash
ss -H -tnp 'sport = :3389'
journalctl -u xrdp.service -u xrdp-sesman.service \
  --since '-15 min' --no-pager
tail -n 80 /var/log/xrdp.log
```

If the newest attempt ends at `TLS connection established` and never reaches
`xrdp_caps_process_*`, reset the controller application first. On macOS:

```bash
osascript -e 'tell application "Windows App" to quit'
open -a "Windows App"
```

This is safer than restarting the Ubuntu service because it preserves the
server's in-memory XRDP session registry. Reopen one connection instead of
leaving several simultaneous attempts pending.

Only if the listener itself is unhealthy or stale handler processes remain
after the client has closed, restart XRDP:

```bash
sudo systemctl restart xrdp.service
systemctl is-active xrdp.service xrdp-sesman.service
ss -H -ltn 'sport = :3389'
```

On Ubuntu, restarting `xrdp.service` can also restart `xrdp-sesman.service`
through unit dependencies. Existing Xorg and GNOME processes may initially
survive, but the new session manager may no longer recognize that old session.
A subsequent login can create a new display and terminate the old one under a
single-session policy. Save GUI work and keep another access path before using
the server-side restart. Terminal multiplexers and files are unaffected.

The successful recovery advanced through these checkpoints:

```text
TLS connection established
xrdp_caps_process_codecs
sesman connect ok
login successful
connected ok
```

## Desktop uses only part of the UU canvas

Windows App can dynamically resize an XRDP desktop to its current window. If
the live desktop becomes smaller while UU retains its saved relay resolution,
UU shows the desktop at the left with an unused white region.

Compare the live XRDP display with the saved UU relay size:

```bash
DISPLAY=:11 XAUTHORITY="$HOME/.Xauthority" xdpyinfo | rg dimensions
sed -n 's/^UURB_RESOLUTION=//p' \
  "$HOME/.config/uu-remote-bridge/environment"
ps -eo pid,args | rg '[X]vfb :|[s]dl-freerdp.exe.*size:'
```

Replace `:11` with the active XRDP display. Do not immediately reduce UU to a
small dynamically selected window size: that removes the white region but
makes the remote desktop unnecessarily low resolution. Choose one useful
target for both layers. On the validated workstation, the existing helper
restores the XRDP desktop and localhost VNC mirror to `1620x1080`:

```bash
XRDP_VNC_GEOMETRY=1620x1080 \
  "$HOME/scripts/xrdp-vnc-bridge.sh" resize

./install.sh --skip-packages --skip-account-login \
  --resolution 1620x1080
```

The helper performs a short local FreeRDP reconnection to resize the existing
Xorg session in place; it may disconnect an attached viewer but does not log
out GNOME. The UU installer then restarts only the supervised bridge. Both
values remain persistent.

FreeRDP 3 rejects the older helper argument `subtype:0` by printing its usage
page without connecting. The current helper announces Japanese layout and
keyboard type but omits that explicit zero, retaining the same default while
allowing the resize. If Windows App later changes the session resolution
again, use a fixed/full-screen client size or repeat the two alignment steps.

## Physical-key pacing

The bridge now has a separate, optional delay for UU's physical-key path. Its
global default is zero, preserving the behavior of already-working hosts. On a
host where deliberate slow typing works but fast typing omits keys, install an
8 ms delay:

```bash
./install.sh --skip-packages --skip-account-login \
  --physical-key-delay-ms 8
./scripts/verify.sh --quick
```

The delay is applied only after the broker accepts a physical-key segment. It
adds back-pressure at the Wine-to-FreeRDP boundary; it does not retry, invent,
or replay a key. Replaying would be unsafe because a late original could
produce a duplicate. Roll back the experiment without removing account state:

```bash
./install.sh --skip-packages --skip-account-login \
  --physical-key-delay-ms 0
```

Keyboard, mouse, text, and other calls have independent bounded telemetry
quotas so early mouse motion cannot consume all diagnostic capacity. Inspect
only content-free metadata:

```bash
broker="$HOME/.local/share/wineprefixes/uu-remote/drive_c/users/$USER/Temp/uu-input-broker.log"
rg 'category=keyboard' "$broker" | tail -n 30
```

A paced successful call reports `category=keyboard`, `focus=ready`,
`paced-physical=1`, the configured `physical-delay-ms`, a matching result
count, and `error=0`. The logs never record a key code, character, clipboard
payload, address, account identifier, or typed text.

## Direct X11 physical-key route

Pacing improved this workstation but did not remove every omission. A later
12 ms capture recorded 219 physical-key broker calls; every recorded call
returned the requested count with `error=0`, while the operator still observed
missing fast letters, Enter presses, and Ctrl chords. This ruled out broker
API failure as the explanation for those recorded calls. It did not prove that
the controller emitted every intended event, because privacy-safe logs cannot
reconstruct typed content, but it made adding more delay a poor next step.

The affected desktop is XRDP Xorg. Its XTEST extension is available and its
standard scan-code-to-X-keycode map was verified directly. The bridge can
therefore bypass the lossy nested keyboard conversion while preserving all
other working channels:

```text
UU physical key -> Wine hook -> user-token broker -> X11 helper -> Xorg

UU video/mouse/text -> existing SDL FreeRDP -> GNOME RDP -> desktop
```

Enable this route only on a verified Xorg/XRDP target:

```bash
./install.sh --skip-packages --skip-account-login \
  --keyboard-route x11 --physical-key-delay-ms 0
./scripts/verify.sh --quick
```

The native helper uses XTEST on the discovered desktop, accepts only physical
keyboard arrays over an authenticated loopback socket, and is supervised by
the existing service. It preflights each complete array. Unavailable or
unsupported input falls back before injection; a failure after possible
injection is returned without replay, avoiding duplicate keys. Disconnect
releases tracked held keys. With the direct route, the physical delay is a
minimum key-hold interval rather than a delay after every down and up event;
zero keeps the path non-blocking.

Restore the universally compatible path without deleting UU state:

```bash
./install.sh --skip-packages --skip-account-login \
  --keyboard-route rdp --physical-key-delay-ms 0
```

The repository default remains `rdp`, so the known-good Wayland host and all
existing installations retain their old route. `auto` chooses direct input
only when the discovered target is X11. The verifier fails if an explicitly
requested X11 route could not become active.

Before live deployment, an isolated Xvfb test sent the full alphabet together
with Ctrl+A and Enter as one fast stream. XTEST observed all 58 transitions in
order: 29 key presses and 29 key releases, including both Ctrl and Enter
transitions.

The subsequent real UU controller test reached the newly restarted broker, not
an older RDP process: all 256 sampled physical-key records reported
`route=x11`, a matching one-event result, and `error=0`. The operator described
typing as very smooth and said almost all earlier loss was fixed. Because the
diagnostic quota intentionally stops after a bounded sample and does not record
typed content, this is documented as a strong practical improvement rather
than a universal zero-loss guarantee.

## What is proven, and what is not

In the observed run, Windows App was restarted, XRDP created a fresh desktop,
the supervised UU bridge automatically restarted against that desktop, and
the 8 ms physical-key setting was active. The operator reported a drastic
improvement, but occasional omissions remained at the fastest typing speed.
Content-free broker metadata independently confirmed that every physical-key
call which reached the hook was focused, paced, and accepted without an error.

This proves the combined state improved the symptom; it does not prove a full
fix or isolate either the fresh XRDP desktop or pacing as sufficient by itself.
A controlled 12 ms trial was the final pacing experiment. It retained
occasional omissions despite successful broker results, so further delay was
rejected in favor of the direct X11 route above. Reconnect UU after any route
change and require fresh `category=keyboard route=x11 result=1 error=0`
records before attributing a manual test to that route.
