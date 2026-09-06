# One physical desktop through RDP, RealVNC and UU Remote

This optional setup shares an existing **GDM X11** desktop. It does not
start another GNOME desktop, move application windows between X servers,
or log out an existing session. Other bridge installations keep their
current defaults unless they explicitly enable this setup.

## Why a new desktop appeared

XRDP's managed `Xorg`/`Xvnc` connections use `port=-1`, which asks sesman
to create or resume a separate session. Meanwhile RealVNC Service Mode
shows the console, and UU may select either desktop in `auto` mode.
An RDP login can also overwrite the systemd user manager's `DISPLAY`,
making that variable unsuitable as proof of which desktop is physical.

The bridge's explicit `physical` target now recognizes GDM's Xauthority
on the GNOME process, or a positively identified seat/GDM session. It no
longer treats the user manager's display alone as physical-session proof.
Explicit `:N`, `xrdp`, and `auto` modes remain available.

## Connection layout

```text
Physical GNOME X11 desktop
  ├─ RealVNC Service Mode → existing RealVNC console/cloud connection
  └─ independent loopback x11vnc service, 127.0.0.1:5922
       ├─ XRDP VNC proxy → RDP client, after Ubuntu PAM authentication
       └─ UU viewer + existing native input bridge → UU clients
```

The independent VNC service belongs to neither an RDP connection nor a UU
process tree. A UU restart cannot kill it. UU validates the configured
relay's owner, display, loopback listener and process before reusing it;
it does not silently fall back to a different port or desktop.

## Install the optional physical-desktop backend

Run as the desktop user from this repository:

```bash
install -m 0755 scripts/uu-shared-physical-vnc "$HOME/.local/bin/uu-shared-physical-vnc"
install -m 0644 systemd/uu-shared-physical-vnc.service "$HOME/.config/systemd/user/uu-shared-physical-vnc.service"
```

The normal installer also installs these files but does **not** enable the
optional service. In `~/.config/uu-remote-bridge/environment`, retain other
working settings and set each of these keys once:

```ini
UURB_DESKTOP_TARGET=physical
UURB_DESKTOP_RELAY=vnc
UURB_DESKTOP_VNC_PORT=5922
```

The installer preserves the shared-port setting during subsequent upgrades.
Clear/remove `UURB_DESKTOP_VNC_PORT` to return to UU-owned VNC startup.

If UU currently owns port 5922, briefly stop only its bridge, enable the
independent service, and restart UU:

```bash
systemctl --user stop uu-remote-bridge.service
systemctl --user daemon-reload
systemctl --user enable --now uu-shared-physical-vnc.service
systemctl --user start uu-remote-bridge.service
```

This reconnects UU without logging out GNOME. Preserve the Wine prefix,
account data and working keyboard, dictation and audio settings. The helper
discovers this user's physical GDM X11 session and uses its current display
and authority; it fails without creating a virtual desktop if none exists.
Existing unattended GDM login remains responsible for creating the physical
session after boot; this service does not enable autologin by itself.

## XRDP connection: authenticate before accessing the console

Back up `/etc/xrdp/xrdp.ini` and add a connection like the following. Replace
`YOUR_DESKTOP_USER` with the owner of the physical desktop. Verify the actual
sesman loopback address: the tested Ubuntu XRDP 0.9.24 instance listened on
`[::1]:3350`, despite a historical IPv4 address in sesman.ini.

```ini
[PhysicalDesktop]
name=Physical desktop (shared with RealVNC and UU)
lib=libvnc.so
username=YOUR_DESKTOP_USER
password=ask
ip=127.0.0.1
port=5922
pamusername=same
pampassword=same
pamsessionmng=::1
disabled_encodings_mask=1
```

In `[Globals]`, set `autorun=PhysicalDesktop`. Put the new connection before
the managed Xorg/Xvnc entries, retaining those as explicitly named separate
desktop alternatives if needed. A client supplying saved credentials can
connect directly; otherwise XRDP asks for the account password.

**The backend uses `-nopw` only on loopback. PAM authentication is required
on the network-facing RDP proxy.** Do not omit the PAM settings, use a build
that ignores them, or expose the backend to the LAN. Verify a deliberately
incorrect password is rejected **before** any VNC backend connection and a
correct password succeeds. `same` reuses the configured username/password
fields and does not require a second password prompt. No Ubuntu account
password needs to be stored in the connection file.

`disabled_encodings_mask=1` disables the ExtendedDesktopSize encoding for
this connection so an RDP client cannot resize the physical desktop. Use
client-side scaling to fit its window. A VNC proxy is not a managed XRDP
session: do not assume every chansrv feature (audio, drives and advanced
clipboard integration) is available without separate configuration.

On the tested XRDP build, new connections read the updated section without
restarting xrdp or sesman. The existing separately managed desktop remains
alive, with its windows preserved. Disconnect/reconnect the **client** to
use the new default; do not log out to switch.

## RealVNC and previous relay helpers

Keep RealVNC Service Mode on the physical console. If an older helper such
as `realvnc-current-xrdp-desktop.service` places a fullscreen viewer of XRDP
on the console, disable that helper after identifying its ownership. It is
the opposite of the desired direction here and can conflict on port 5922.
Do not disable the actual `vncserver-x11-serviced.service`.

The optional shared VNC service can also serve RDP without UU installed.
UU's uninstaller intentionally does not remove this independently managed
backend; reconfigure any RDP consumers before manually disabling/removing it.

## Validation on 2026-09-06

- Physical display `:0`, private UU canvas `:20`, preexisting XRDP `:10`.
- Wrong-password RDP test: PAM rejection, no backend desktop access.
- Correct-password RDP test: PAM success, `libvnc.so` connected to 5922,
  visible framebuffer showed the existing console and browser windows.
- The same physical window IDs remained present; no GNOME/Xorg process
  was terminated and no new GNOME session was created by the proxy test.
- UU selected `physical` / `:0`, reused the independent relay, retained
  direct X11 input and its authenticated native terminal helper.
- RealVNC Service Mode stayed running; the reverse-direction old relay was
  disabled. No RealVNC cloud credential or license setting was changed.
- The temporary test display and RDP test client were stopped afterward.
- Boot configuration was checked; a reboot was not performed. Client-side
  CJK dictation, phone typing and every RDP redirection feature were not
  exhaustively retested; their existing UU patch binaries were preserved.

References: [XRDP upstream configuration](https://github.com/neutrinolabs/xrdp/blob/v0.9.24/xrdp/xrdp.ini.in),
[XRDP connection/authentication code](https://github.com/neutrinolabs/xrdp/blob/v0.9.24/xrdp/xrdp_mm.c),
and the locally installed `xrdp.ini(5)` manual.
