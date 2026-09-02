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

## UU cursor is missing or too small

Keep the relay resolution and Wine DPI unchanged. The process-local cursor
guard is an opt-in compatibility extension, so hosts with a working cursor do
not load it. Enable it when the controller loses the cursor, renders it too
small, or the UU server records `ERROR_INVALID_CURSOR_HANDLE`:

```bash
./install.sh --skip-packages --skip-account-login \
  --cursor-guard on --cursor-size auto
```

`auto` reads the physical GNOME Xcursor size and creates the same-sized
fallback arrow for UU's independent cursor channel. For a controller that
still renders the cursor too small, use a fixed size:

```bash
./install.sh --skip-packages --skip-account-login \
  --cursor-guard on --cursor-size 64
```

Accepted values are `24` through `128`. Disable the extension with
`--cursor-guard off` when it is unnecessary. It does not change XRDP, VNC,
TeamViewer, the physical desktop resolution, or Wine's global DPI.

## Controller remains at “finding routes”

This message can be misleading: the controller may be waiting for the host to
finish local startup before any transport route can be selected. On the
affected workstation, `GameViewerServer.exe` used about two CPU cores and its
newest log stopped at:

```text
update_gvinput start
```

The dedicated Wine registry had accumulated 527 failed `gvinput` devices and
21,894 Bluetooth observations while Ubuntu's Bluetooth scanner was active.
UU enumerated those records synchronously before joining its signaling room.
This was not an Ethernet, DNS, firewall, XRDP, or controller-route failure.

Current installations make the audited `devcon.exe` unavailable while keeping
its exact vendor binary as `devcon.exe.uu-original`, disable Bluetooth only
inside UU's dedicated Wine prefix, and remove only recognized stale device
records. Existing installations can apply the same transactional repair:

```bash
uu-remote repair-registry
./scripts/verify.sh --quick
```

The command stops and restarts only `uu-remote-bridge.service`. It keeps a
mode-0600 `system.reg.before-device-hygiene-*` backup under
`$WINEPREFIX/compat/registry-backups`, refuses a root-device subtree containing
an unrelated device, and does not change Ubuntu Bluetooth or XRDP.

A healthy cold start records `update_gvinput end` within milliseconds and then
`room_state_changed: created`. Inspect without publishing account metadata:

```bash
server_logs="$HOME/.local/share/wineprefixes/uu-remote/drive_c/Program Files/Netease/GameViewer/log/server/log"
latest="$(find "$server_logs" -type f -name 'log_*.txt' -printf '%T@ %p\n' |
  sort -nr | head -n 1 | cut -d' ' -f2-)"
rg 'update_gvinput|input_device_count|room_state_changed: created' "$latest"
```

Do not copy this cleanup to a shared Wine prefix or delete arbitrary
`ROOT\HIDCLASS` entries. Its preflight assumptions are valid because this
project owns a dedicated UU-only prefix.

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

First inspect the broker metadata:

```bash
broker="$HOME/.local/share/wineprefixes/uu-remote/drive_c/users/$USER/Temp/uu-input-broker.log"
tail -80 "$broker"
```

Repeated `focus=timeout result=0 error=21` immediately after opening the local
UU app means one Wine prefix was split across two X displays. Wine's foreground
window state is shared across that prefix, so a physical-display
`GameViewer.exe` can prevent the private `Ubuntu-Desktop-Relay` from becoming
the Win32 foreground window even when X11 says it is active.

Update and reinstall this launcher, then restart the bridge once:

```bash
git pull --ff-only
./install.sh --skip-packages --skip-account-login
uu-remote restart
```

`uu-remote open` must present a `UU Remote - TigerVNC` window while
`GameViewer.exe`, `GameViewerServer.exe`, `uu-input-broker.exe`, and
`sdl-freerdp.exe` all retain the same private `DISPLAY`. Do not launch the
prefix's `GameViewer.exe` directly on `DISPLAY=:0`. A healthy fresh input call
reports `focus=ready`, a matching result count, and `error=0`.

Then check the compatibility hook log:

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

## Mac RDP is rejected or VNC is black

Do not connect a second RDP client to the bridge's desktop-sharing port. The
internal SDL FreeRDP process already owns that GNOME session. Port 3389 is
GNOME remote login and opens a separate desktop.

An SSH tunnel to `::1:5900` can also be wrong even though it connects. On the
validated host that socket belonged to x11vnc on an unrelated Xvfb display
`:42`, so the Mac received a black or stale desktop.

Use the maintained launcher and its default **Current Desktop** action:

```bash
~/.local/bin/uu-remote-console relay-port
```

On the Mac, the launcher forwards local `localhost:15922` to that loopback
port over the `glassagent-ubuntu` SSH alias. The first connection asks for the
bridge password; select **Remember password**. A healthy connection leaves no
LAN VNC listener:

```bash
ss -ltnp | grep 5922
```

The Ubuntu address must be `127.0.0.1:5922`. The Mac may expose both
`127.0.0.1:15922` and `[::1]:15922`, but only while the SSH tunnel is active.
If Ubuntu is simultaneously viewing the Mac during a test, the two remote
windows form a recursive image. Close the Ubuntu-to-Mac viewer; this is not a
black-screen fault.

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

## Shift-number symbols look Japanese or American

The direct X11 path follows the target Ubuntu desktop's XKB layout; it does not
hardcode JIS inside the bridge. Check the selected desktop explicitly:

```bash
DISPLAY=:11 XAUTHORITY="$HOME/.Xauthority" setxkbmap -query
```

With `layout: jp`, `Shift+6` produces `&`, `Shift+7` produces `'`, and the
other symbol positions follow Japanese JIS. A US layout produces different
shift-number symbols. RealVNC can feel more controller-dependent because its
client protocol sends already interpreted key symbols, while UU's physical
path supplies Windows virtual keys/scancodes that the direct helper places on
the target XKB key positions.

UU does not expose a reliable controller-layout identity to this bridge.
Automatically guessing `jp` versus `us` from one symbol would make mixed Mac,
Windows, and phone controllers unstable. Keep the intended Ubuntu layout
explicit and change it only as an operator choice; resolution following never
changes keyboard settings.

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
depth. The launcher raises its own soft limit after any `runuser`/PAM boundary,
because that boundary can replace a system unit's 65536 limit with 1024. The
quick verifier also recognizes the supported application-profile service and
checks GNOME RDP's listener inside its network namespace. Rerun the installer
if the verifier still reports a 1024 limit, a missing backport, or
installed-source drift. The threshold is configurable with
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

If the transport and relay are responsive, deliberate slow typing works, and
fast physical-key input still omits events, test bounded physical-key pacing:

```bash
./install.sh --skip-packages --skip-account-login \
  --physical-key-delay-ms 8
./scripts/verify.sh --quick
```

The default is `0`. The broker waits only after an accepted physical-key
segment; it does not retry or synthesize a key. Confirm the accepted test with
privacy-safe metadata:

```bash
broker="$HOME/.local/share/wineprefixes/uu-remote/drive_c/users/$USER/Temp/uu-input-broker.log"
rg 'category=keyboard' "$broker" | tail -n 30
```

Look for `focus=ready`, `paced-physical=1`, the configured
`physical-delay-ms`, a matching result count, and `error=0`. Restore the
original behavior with `--physical-key-delay-ms 0`. After changing the value,
reconnect the UU controller and verify that fresh keyboard records appear after
the broker startup line for that value. A subjective test made through RDP or
an unreconnected UU client does not measure the new bridge process.

If 8-12 ms pacing improves but does not solve the symptom, and fresh broker
records still show matching counts with `error=0`, do not keep increasing the
delay. On a verified Xorg/XRDP target, select the native physical-key route:

```bash
./install.sh --skip-packages --skip-account-login \
  --keyboard-route x11 --physical-key-delay-ms 0
./scripts/verify.sh --quick
```

The verifier must report `direct X11 physical-key helper is active`. A fresh
UU computer-keyboard event must report `category=keyboard route=x11`, while a
representable normal-phone-keyboard commit reports
`category=text route=x11-text`; both require a matching result and `error=0`.
A fresh pointer or click event reports `category=mouse route=x11-mouse` with
the same success boundary. Video and clipboard remain on the selected local
relay. If explicit X11 preflight cannot verify the target display, the service
remains usable on RDP but verification fails so the fallback is not mistaken
for the requested test. Restore the baseline with:

```bash
./install.sh --skip-packages --skip-account-login \
  --keyboard-route rdp --physical-key-delay-ms 0
```

## Windows App remains on Configuring

First determine whether the newest XRDP attempt stops immediately after
`TLS connection established`:

```bash
ss -H -tnp 'sport = :3389'
journalctl -u xrdp.service -u xrdp-sesman.service \
  --since '-15 min' --no-pager
tail -n 80 /var/log/xrdp.log
```

If no capability, authentication, or session-selection line follows, reset
Windows App on the controlling Mac before touching Ubuntu:

```bash
osascript -e 'tell application "Windows App" to quit'
open -a "Windows App"
```

A localhost VNC mirror on a different RFB port does not conflict with XRDP's
TCP 3389 listener. Restart `xrdp.service` only if the listener remains unhealthy
after the client closes. Ubuntu's unit dependencies can restart
`xrdp-sesman.service` too; the replacement manager may create a new display and
end the prior XRDP/VNC desktop. The complete evidence and safest ordering are
in [XRDP Client Stall and UU Keyboard Recovery](xrdp-and-keyboard-recovery.md).

## UU has white space or clips the right side of the desktop

Compare the active XRDP display with the UU relay setting:

```bash
DISPLAY=:11 XAUTHORITY="$HOME/.Xauthority" xdotool getdisplaygeometry
sed -n 's/^UURB_RESOLUTION=//p' \
  ~/.config/uu-remote-bridge/environment
```

Windows App can dynamically resize the XRDP desktop when its window changes.
When XRDP is smaller than UU's private relay, the unused region appears as
white space. When XRDP is larger, FreeRDP can clip the right or bottom edge
instead of scaling it. The GNOME top bar may still look plausible, so inspect
the dimensions rather than judging only from the header.

On an active direct-X11 bridge, the quick verifier performs this comparison
too and fails with both dimensions when they differ:

```bash
./scripts/verify.sh --quick
```

Do not shrink UU to a very small window-derived size unless that low resolution
is intentional. Restore a useful XRDP size first, then match UU. For example,
if both should be `1920x1080`:

```bash
./install.sh --skip-packages --skip-account-login \
  --resolution 1920x1080
```

This restarts only the supervised UU bridge; it does not restart or reconfigure
XRDP. If XRDP itself must be resized, do that as a separate operator-controlled
step because changing the XRDP geometry may disconnect its attached viewer.
See the
[recovery note](xrdp-and-keyboard-recovery.md#desktop-uses-only-part-of-the-uu-canvas)
for the FreeRDP 3 compatibility correction and persistence behavior.

If Windows RDP and UU regularly take turns on the same X11/XRDP desktop, the
VNC relay can follow a stable source size automatically:

```bash
./install.sh --skip-packages --skip-account-login \
  --follow-desktop-resolution on
```

The bridge aligns immediately at startup. While running, it ignores the first
minute, rejects sizes below `1024x720`, and requires three matching five-second
checks before atomically saving the new size and restarting only UU. This
debounce prevents a dragged or minimized RDP window from causing a restart
loop. It never resizes or restarts XRDP, GNOME, or the shared applications.

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

## UU opens a clean desktop instead of the existing XRDP desktop

Two GNOME sessions are alive and automatic discovery selected the physical/GDM
session (commonly `:0`) while the useful windows remain in an XRDP session
(commonly `:10` or `:11`). Confirm their identities without restarting either
desktop:

```bash
loginctl list-sessions
pgrep -a gnome-shell
journalctl --user -u uu-remote-bridge.service -n 30 --no-pager
```

Pin the session by type rather than by its temporary display number:

```bash
./install.sh --skip-packages --skip-account-login \
  --desktop-target xrdp
```

The journal must identify `xrdp-sesman` and the current XRDP display. When no
XRDP desktop exists, the bridge waits; it does not fall back to the physical
desktop. This operation restarts only the UU bridge. It must not restart
`xrdp`, `xrdp-sesman`, GDM, GNOME Shell, or the applications being shared.
Restore historical automatic selection with `--desktop-target auto`, or
select the physical seat with `--desktop-target physical`.

## Physical speakers pulse or the UU client receives unwanted sound

Do not assume that every sound heard during a UU session belongs to UU. The
bridge's internal SDL FreeRDP command includes `/audio-mode:2`, so the nested
desktop relay does not intentionally play the shared desktop back into the
host speakers. Identify the live PipeWire stream first:

```bash
wpctl status
wpctl inspect STREAM_OR_CLIENT_ID
pgrep -a -u "$UID" -f 'sdl-freerdp|GameViewer|SHI'
```

During the first 2026-08-09 inspection, UU and FreeRDP owned no playback
stream. The only continuous output was an Unreal packaged build:

```text
application.name = SDL Application
application.process.binary = SHI
media.class = Stream/Output/Audio
target.object = ...USB_Audio_2...sink
```

Its own log confirmed that SDL3 opened the physical USB S/PDIF output with a
six-channel 48 kHz stream. Mute only the identified node while preserving the
game and desktop:

```bash
wpctl set-mute STREAM_NODE_ID 1
wpctl get-volume STREAM_NODE_ID
```

If the hardware still remains active, disconnect that application's two
links from the physical sink and connect them to the existing XRDP virtual
sink with `pw-link`. Use the exact names from `pw-link -l`; never change the
system default sink merely to repair one application. On the affected host,
this changed the physical S/PDIF node from running to idle while SHI, UU,
XRDP, GNOME Shell, and every window remained running.

The durable Unreal-side fix is to launch remote previews with its supported
`-nosound` option. Keep `-enablesound` as an explicit listening override. A
single launcher edit is not sufficient when a build pipeline regenerates new
review directories: identify every live `SHI` stream, and make the generated
launch command carry `-NoSound`. Do not add a polling daemon or a global
WirePlumber mute rule for this symptom.

That first diagnosis was valid for that stream graph, but it was not the whole
incident. After the UU bridge restarted at 22:58, `wpctl status` showed two
new streams owned by `GameViewerServer.exe` through Wine:

```text
Output/Audio  网易UU远程服务 -> physical USB S/PDIF
Input/Audio   网易UU远程服务 <- C922 webcam microphone
```

The capture stream was active and `pipewire-pulse` repeatedly logged
`[网易UU远程服务] overrun recover`. This was the remaining sound path. Mute
both dynamically discovered UU stream nodes, then move only their exact links
from physical devices to the existing XRDP virtual endpoints:

```bash
wpctl set-mute UU_OUTPUT_NODE 1
wpctl set-mute UU_INPUT_NODE 1

# Use IDs from `pw-link -I -l`; they are examples, not stable identifiers.
pw-link -d UU_OUTPUT_FL PHYSICAL_PLAYBACK_FL
pw-link -d UU_OUTPUT_FR PHYSICAL_PLAYBACK_FR
pw-link -d PHYSICAL_CAPTURE_FL UU_INPUT_FL
pw-link -d PHYSICAL_CAPTURE_FR UU_INPUT_FR

pw-link UU_OUTPUT_FL XRDP_SINK_FL
pw-link UU_OUTPUT_FR XRDP_SINK_FR
pw-link XRDP_SOURCE_FL UU_INPUT_FL
pw-link XRDP_SOURCE_FR UU_INPUT_FR
```

`wpctl set-mute` records the per-application input and output mute through
WirePlumber's normal stream-restore mechanism. Do not edit WirePlumber's state
file directly. A live link reroute can be useful for diagnosis, but do not make
`PULSE_SINK=xrdp-sink` or `PULSE_SOURCE=xrdp-source` a service environment
override. On the validated multi-session host, many stale XRDP modules exported
the same node names. Wine connected to PipeWire but then hung forever while
enumerating Windows Core Audio. The HTTP room request still returned success,
which made the service look healthy, but signaling never started and
`LACHLANSERVER` disappeared from every other UU client.

Digital mute is not the same as closing the device. Two subsequently generated
SHI review builds remained linked to the S/PDIF endpoint while their restored
stream mute was on, leaving ALSA `pcm2p` in `RUNNING`. Route those exact
streams away from the physical sink. On hardware that keeps an idle USB S/PDIF
clock active, an exact-device WirePlumber rule may set `node.pause-on-idle` to
`true` and a short `session.suspend-timeout-seconds`; do not apply that rule to
all sound devices. The acceptance check is:

```bash
cat /proc/asound/card*/pcm*p/sub*/status
fuser -v /dev/snd/*
```

The affected playback PCM must say `closed`, not merely `SUSPENDED`, muted, or
idle in a desktop mixer.

Finally, UU's own log showed that every controller connection still invoked
`startAudioCapture`, even after its stream was muted and the physical PCM was
closed. Disabling Wine PulseAudio only in this dedicated prefix prevents UU
from opening PipeWire or a physical ALSA device:

```ini
# ~/.config/systemd/user/uu-remote-bridge.service.d/20-audio-isolation.conf
[Service]
Environment="UURB_UU_AUDIO=off"
```

The bridge maps `off` to `winepulse.drv=d` in its own Wine process. It does not
disable normal Ubuntu, browser, XRDP, or other Wine-prefix audio.

Do not stop at device visibility. In the 2026-08-10 incident, `off` alone let
the host advertise itself and accept a controller participant, but the
controller waited forever. The streamer stopped at
`AudioDeviceModuleImpl::InitPlayout`; ICE and video capture never started. UU
therefore requires a usable audio abstraction even when the operator wants no
sound.

Give only this Wine prefix a silent ALSA namespace. The repository includes a
reviewed template:

```bash
install -d -m 0700 ~/.config/uu-remote-bridge
install -m 0600 config/alsa-null.conf \
  ~/.config/uu-remote-bridge/alsa-null.conf

WINEPREFIX="$HOME/.local/share/wineprefixes/uu-remote" \
  /opt/wine-stable/bin/wine reg add \
  'HKCU\Software\Wine\Drivers' /v Audio /t REG_SZ /d alsa /f
```

Extend the same service drop-in without adding global ALSA or PipeWire state:

```ini
[Service]
Environment="UURB_UU_AUDIO=off"
Environment="ALSA_CONFIG_PATH=/home/USER/.config/uu-remote-bridge/alsa-null.conf"
```

Run `systemctl --user daemon-reload`, then restart only
`uu-remote-bridge.service` during a disconnected UU window. The validated cold
start completed both peer-connection factories in milliseconds, connected
signaling, reached `room_state_changed: created`, advertised the device as
`CONNECTED`, and left no GameViewer stream in `wpctl status` or physical PCM
in `/proc/asound`. The exact acceptance sequence for a new controller includes
peer states 1 through 3, successful media initialization, and video capture;
room creation alone is not sufficient.

`UURB_UU_AUDIO=system` is the compatibility default. To undo the silent
fallback, remove the drop-in and delete only this prefix's explicit audio
driver value, then restart only the bridge:

```bash
WINEPREFIX="$HOME/.local/share/wineprefixes/uu-remote" \
  /opt/wine-stable/bin/wine reg delete \
  'HKCU\Software\Wine\Drivers' /v Audio /f
```

Do not restart PipeWire, WirePlumber, XRDP, GDM, or GNOME for this repair.

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

## Device is online but the shared desktop is black or white

First distinguish signaling from capture. A successful account login, room
creation, and controller join prove only that the device is visible to UU.
Inspect the private canvas separately:

```bash
uu-agent status
uu-agent snapshot ~/.local/state/uu-remote-bridge/private-canvas.png
```

If the real target display has content but the private screenshot is uniformly
black or white, test the source through a localhost-only VNC mirror. On the
validated dual-NVIDIA/XRDP host, GNOME Remote Desktop 46.3 accepted the local
FreeRDP client but delivered a blank nested surface; disabling CUDA merely
changed black to white. The same X11 desktop rendered immediately through
`x11vnc`, and pointer motion crossed the viewer back to the original display.

Enable the scoped fallback without changing XRDP or logging out:

```bash
./install.sh --skip-packages --skip-account-login \
  --desktop-target xrdp --desktop-relay vnc
```

The fallback owns a dynamically selected loopback port, disables IPv6 and the
VNC bell, keeps the native viewer full-screen on UU's private display, and is
supervised in the same service cgroup. It does not reuse or restart the user's
normal VNC viewer. `rdp` remains the default for other hosts. Switch back with
`--desktop-relay rdp`.

For UU media compatibility, keep `UURB_UU_AUDIO=system` only if completely
disabling Wine PulseAudio makes a particular controller disconnect. Do not
force XRDP sink/source names through the service environment. Disable the VNC
bell independently; it does not participate in UU's WebRTC negotiation.

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

## UU Terminal immediately says exit code 0

On an unpatched Wine host, UU successfully opens its terminal channel and then
launches Wine's placeholder `powershell.exe`. That executable returns success
without creating an interactive shell, so exit code 0 is the symptom—not a UU
account or network failure.

Install the current bridge and verify the native broker:

```bash
./install.sh --skip-packages --skip-account-login
./scripts/verify.sh --quick
./scripts/test-terminal-bridge.sh
```

In UU, choose the `PowerShell` shell even though the resulting PTY is the
native Ubuntu login shell. If verification reports a missing or stale terminal
bridge, do not copy an arbitrary executable over
`GameViewer/bin/powershell.exe`; rerun the installer so its byte-identity guard
can repair a known installation or refuse unknown vendor drift.

Inspect only metadata when diagnosing:

```bash
tail -n 30 ~/.local/state/uu-remote-bridge/terminal-bridge.log
```

Do not add an SSH password or expose another listening port as a workaround.
The intended listener is ephemeral, token-authenticated, and localhost-only.

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
