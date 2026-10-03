# What works, what is conditional, and what remains unverified

Reviewed: **4 October 2026**. This is the Ubuntu bridge's feature status, not a
copy of the native Windows UU feature list. The operator reports ordinary
clipboard, dictation, multilingual input and mouse control working in daily use.
The release records below identify narrower, reproducible checks. A working
route or test fixture does not establish support for every controller or app.

## Feature status

| Feature | Status | Scope and evidence |
| --- | --- | --- |
| Existing Ubuntu desktop | Working on tested hosts | Physical GNOME desktop video, reconnect and retained applications passed the [4.42 RDP acceptance](releases/4.42.1.2835-acceptance.md) and [X11 workstation checks](releases/4.42-x11-workstation-20261001.md). Select the intended desktop explicitly when necessary. |
| Mouse | Working on tested routes | Movement, buttons, wheel, focus and clicks; geometry must match the selected desktop. |
| Physical keyboard and shortcuts | Working, controller-dependent | Letters, modifiers and punctuation have real-controller checks. [Adaptive relays](adaptive-keyboard-relays.md) preserve separate physical-key and semantic-text paths; this is not a universal US/JIS/Mac layout guarantee. |
| Phone keyboard / non-English Unicode | Working on tested paths | Chinese input was user-confirmed. Isolated semantic tests cover Chinese, punctuation, emoji and multiline text; an individual phone/IME still needs its own check. |
| Continuous dictation | Implemented and regression-tested; working in reported daily use | [Semantic text handling](semantic-text-and-clipboard.md) serializes commits and bounds composition edits so revisions cannot erase an earlier message. The 4.42 Mac controller run did not test real phone dictation. |
| Bidirectional text clipboard | Working, route-dependent | Exact multiline English/Chinese copy passed both directions on the RDP host. The X11/VNC return helper is opt-in and separately tested; see limits below. |
| Same desktop through UU, RDP and RealVNC | Optional, configured setup | The [shared physical X11 desktop](shared-physical-desktop.md) backend keeps existing windows. Independent default installations do not automatically share a desktop. |
| Resolution and canvas fitting | Configurable | Fixed size and optional stable X11/VNC size following are documented in the [README](../README.md#quick-start). This does not establish extra virtual-monitor support. |
| Reconnect, service recovery and boot startup | Implemented; prerequisites apply | Service restart and login retention passed. [Unattended startup](../README.md#unattended-reboot-startup) still needs a usable logged-in GNOME desktop/keyring. Neither 4.42 acceptance run rebooted the machine. |
| Native UU Terminal → Ubuntu shell | Adapter works; vendor channel conditional | The [native PTY bridge](native-ubuntu-terminal.md) supports UTF-8 and resize. Vendor controllers can reject startup because of version/transport incompatibility; an adapter test is not a vendor UI test. |
| `uu-shell` | Working with an enrolled SSH transport | The [fleet shell](fleet-shell.md) selects explicitly configured LazyTunnel SSH, port-mapped SSH or native UU Terminal. Live checks are recorded below; these transports are not interchangeable evidence. |
| UU port mapping / SSH / SCP | Conditional | [Two-way SSH and file transfers](ssh-and-port-mapping.md) have passed. Closing or taking over the mapping's carrier can disconnect it. It is not an always-on VPN or an automatic same-LAN connection. |
| Super Screen / extra virtual displays | Unverified | No accepted Ubuntu-bridge test establishes this vendor feature. Capturing or resizing one existing desktop does not prove a virtual display can be created or extended. |
| Anti-peep / privacy screen | Unverified | No validated Linux physical-screen blanking and local-input-lock backend was found in the bridge. Do not rely on the vendor button to protect a physical monitor; see below. |
| Remote audio / microphone | Limited; host-dependent | Some hosts deliberately use the [silent audio backend](troubleshooting.md#physical-speakers-pulse-or-the-uu-client-receives-unwanted-sound). Working video/control is not audio or microphone acceptance. |
| UU-native file transfer, image/file clipboard, drag-and-drop, other vendor extras | Unverified | Text clipboard acceptance does not cover these. SCP/SFTP over a verified SSH route is a separate file-transfer option. Features not listed as verified remain unverified. |

## Clipboard and input boundaries

- The [4.42 RDP production test](releases/4.42.1.2835-acceptance.md) verified
  controller-to-Ubuntu and Ubuntu-to-controller **text** copy with a native Mac
  controller. It did not verify image or file clipboard formats.
- On the X11/VNC track, `UURB_HOST_CLIPBOARD=on` enables the separate return
  helper. Its tested limit is 60 KiB of text. It filters bridge-owned dictation
  and inbound selections, does not replay startup content and never injects a
  paste. Do not enable raw reverse VNC clipboard synchronization to bypass it:
  that can reintroduce the old dictation/clipboard feedback problem.
- Phone dictation uses the semantic-text path, independently of an ordinary
  clipboard update. Chinese text, emoji, revisions, multiline content and
  2,000-record delivery have isolated regression evidence. Real controls and
  Chinese input were confirmed on the X11 workstation; that record explicitly
  leaves its full remote clipboard round trip to separate confirmation.
- Native RDP's optional shared-desktop clipboard is another channel. Its
  documented XRDP 0.9.24 test passed Chinese/Japanese/accented text but failed
  non-BMP emoji. Do not transfer a UU Unicode success claim to that channel.

## Super Screen and anti-peep are not accepted features

The repository has no accepted Super Screen test or dedicated Linux backend
for the vendor's privacy-screen controls. They must remain **unverified**, not
silently marked working because their buttons appear in the Windows client.
This review did not activate privacy mode or blank the working desktop.

UU captures a private relay canvas. Making that canvas black, hiding a viewer,
or reducing its resolution does not prove the physical monitor is hidden.
Turning off a physical monitor is a separate host operation; it may wake on
input, does not imply local keyboard/mouse locking, and must not be described
as a tested implementation of UU's anti-peep feature.

A future acceptance must independently observe the physical screen, preserve
remote control and open applications, verify restoration, and specify whether
local input is actually blocked. Super Screen likewise needs a real display
creation/extension test with correct geometry and input, not merely a resize.

## `uu-shell`: verified transport, explicit limitations

Use a peer already enrolled in your private configuration:

```bash
uu-shell --list
uu-shell lab
uu-shell --lazy lab hostname
uu-shell --native lab
```

Replace `lab` with your configured peer. `--lazy` requires existing LazyTunnel
enrollment; `--native` explicitly requests UU's own terminal channel. There is
no silent transport fallback, desktop takeover or reconnect loop.

The [3 October fleet checks](fleet-shell.md#native-uu-limits-observed-on-3-october-2026)
passed 64 directed hostname checks and SSH exit-status checks. Native UU tests
separately encountered `Client version too low`, `invalid open response` and
Streamer error 9012 on some peers. Both Ubuntu native adapters returned Chinese
text, but the proxy reported zero after `exit 7`; use SSH when command exit
status matters. The native Mac CLI can open its GUI picker instead of returning
an interactive shell in the calling terminal.

On 4 October, a fresh check invoked the installed `uu-shell` with its saved
transport for a self route and an Ubuntu peer. The command printed a Chinese
marker and intentionally exited with status 7. The results below describe SSH,
not native UU-channel tests. No remote desktop was
taken over and no mapping was opened or restarted.

| Tested route | Selected transport | Exact Chinese text | Exit status |
| --- | --- | --- | --- |
| Workstation → itself | Saved LazyTunnel SSH profile | Passed | 7, as requested |
| Workstation → Ubuntu peer | Saved LazyTunnel SSH profile | Passed | 7, as requested |

These were short, noninteractive checks of the installed helper, not a new
all-device availability sweep or an interactive native UU acceptance test.

## Installation scope and updates

The baseline is x86-64 Ubuntu 24.04, GNOME 46 and Wine 11. A fresh install remains
pinned to `4.33.0.8907`; `4.42.1.2835` has a separate exact-hash manifest and
two host-specific acceptance records. Unknown binaries are rejected. Read
[host compatibility](compatibility.md) and the release record for your route;
upgrading a README does not deploy a binary or change a running service.
