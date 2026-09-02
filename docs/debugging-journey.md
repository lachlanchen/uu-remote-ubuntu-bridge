# Debugging Journey

This is the evidence trail behind the bridge, including hypotheses that were
useful but incomplete. It is intentionally free of account tokens, clipboard
contents, typed characters from private sessions, and proprietary binaries.

## 1. Split the relay into observable hops

The first useful model was not “UU on Linux.” It was a chain of independently
testable boundaries:

```text
phone controller
  -> UU GameViewerServer under Wine
  -> a capturable Windows relay window
  -> SDL FreeRDP on private Xvfb
  -> local GNOME RDP
  -> the logged-in Ubuntu desktop
```

Video, pointer motion, button input, physical keyboard input, phone text,
account presence, and long-running process survival were tested separately.
This prevented one successful hop from being mistaken for a working system.

## 2. Replace the unavailable kernel-input path

Windows UU preferred its signed `gvinput.sys` virtual HID driver. Wine could
not load that driver, although the official client still contained a
user-mode `SendInput` path. Four version-locked executable edits selected that
existing path. The patcher validates the complete upstream hash, exact
instruction signatures, and complete patched hash before changing anything.

That made the first input request visible, but the first click still ended the
remote session. A minimal Windows probe and the bridge diagnostic showed:

```text
SendInput -> result=0 error=5
```

The UU service token was unsuitable for Wine input injection. A bounded named
pipe now carries the original `INPUT` records to a normal user-token broker.
The broker focuses only the relay window, calls `SendInput`, and returns the
real count and Windows error. No key code, character, coordinate, or clipboard
payload is logged.

## 3. Prove stability by elapsed time

An early bridge looked correct but the server disappeared at roughly four
minutes. Replacing UU's health monitor helped one failure mode without fixing
the second. Wine's event-log stub aborted the server when UU called
`EvtOpenPublisherMetadata`.

The injected bridge now returns the ordinary Windows error
`ERROR_EVT_PUBLISHER_METADATA_NOT_FOUND` at that API boundary. UU handles the
error and continues. The full verifier checks one server PID for 270 seconds;
a startup-only check would not have found this fault.

## 4. Distinguish two phone keyboard surfaces

UU's computer-keyboard panel sends physical keyboard events. The phone's
normal keyboard uses UU's text-input operation. The failure signature was
specific: ordinary keys worked, while phone text became one repeated letter
or punctuation.

### The first incomplete hypothesis

The first phone-text patch enabled FreeRDP's `cliprdr` channel. Clipboard
sharing is useful for copy and paste, and a Windows host followed by RDP can
make phone text appear related to clipboard transport. However, a test that
only asserted `+clipboard` on the command line did not test phone input.

UU's own bounded logs provided the decisive evidence:

```text
KeyboardMouseRunner::execTextInput
wetpe_ime not install use SendInput
```

The text operation submitted paired `INPUT_KEYBOARD` records marked
`KEYEVENTF_UNICODE`. Wine accepted the call, so the old “broker only after
failure” rule did not run. SDL FreeRDP then interpreted unsuitable synthetic
Unicode events as physical input.

One diagnostic trap mattered: bridge and broker logs intentionally stop
recording routine successful calls after a bounded count. An unchanged file
timestamp after that limit does not prove an API was never called.

### The working correction

The IAT hook detects any Unicode keyboard record and routes that complete batch
to the broker for normalization. In the live relay, ordinary events now also
use the broker as their primary path instead of first repeating the known-
denied service-token call. The broker:

1. drops the matching synthetic Unicode key-up record
2. maps each representable character with `VkKeyScanW`
3. emits explicit modifier, virtual-key down/up, and modifier-release events
4. reports UU's original request count only after the whole translated batch
   succeeds
5. returns `ERROR_NO_UNICODE_TRANSLATION` instead of emitting a wrong key when
   a character cannot be represented

The acceptance string `abcXYZ123,.!?` exercises case, shift state, digits, and
punctuation through the phone's normal keyboard. The current implementation is
not a general Unicode text engine: CJK characters, emoji, and characters
outside the active Wine keyboard layout can still fail explicitly.

## 5. Separate source updates from installed runtime

During diagnosis, Git contained the corrected launcher while
`~/.local/bin/uu-remote-bridge` and the compatibility binaries were still from
an older installation. The running process therefore retained its old command
line even though the checkout looked fixed.

The installer now records a deterministic digest of all runtime-affecting
source, build, manifest, unit, and launcher files. `verify.sh` compares that
digest with the active installation. A pull without reinstalling is reported
as runtime drift instead of being mistaken for a deployed fix.

## 6. Find and repair long-running GNOME RDP descriptor growth

After an eight-hour relay session, the GNOME Remote Desktop child showed:

```text
open descriptors: 1023
soft limit:        1024
mutter-shared:     888
```

Its log repeatedly reported:

```text
libei bug: Failed to dup keymap fd: Too many open files
```

This explains input degradation in that live session. The exact upstream
cause was initially unproven, so the first safe response was containment. A
fresh relay then made the leak measurable: `mutter-shared` grew from 893 to
998 over 30 seconds, about 3.5 descriptors per second.

The installed package was `libei1 1.2.1-1`. Upstream commit
`ee27dd5c92e4e9496a36ca2d4112049fe02d2269` later described the exact defect:
the received keymap descriptor was duplicated into an `ei_keymap`, but the
descriptor from the protocol demarshaller was never closed. The upstream fix
adds that missing close. This matches all local evidence: Mutter creates the
files as `mutter-shared`, libei receives them, and failure occurs when libei
can no longer duplicate another keymap FD.

Replacing a desktop-wide system library would have enlarged the risk. The
bridge instead builds libei 1.2.1 from a hash-verified upstream archive,
applies that published one-line backport, and installs it inside the dedicated
bridge prefix. `LD_LIBRARY_PATH` is set only for the supervised GNOME RDP
child. The system package remains untouched.

Two operational protections remain as defense in depth:

- `LimitNOFILE=65536` gives the supervised GNOME RDP child practical headroom.
- The existing quarter-second UU supervisor counts GNOME RDP descriptors only
  once every ten seconds. At the default threshold of 4096 it exits, allowing
  systemd to rebuild the complete local relay before injection fails.

This adds no second monitoring loop. The threshold is persistent and
controllable:

```bash
./install.sh --skip-packages --skip-account-login \
  --grd-fd-restart-threshold 4096
```

Use `0` only to disable the guard deliberately.

## 7. Reconstruct what an interactive login supplied

Starting a user service at boot was not enough. UU needs a real GNOME session,
and GNOME RDP needs its credential from the login keyring. GDM automatic login
creates the desktop but does not give PAM a password with which to unlock that
keyring.

The unattended path therefore:

1. preserves the previous GDM values in root-only rollback state
2. enables automatic login for the selected desktop user
3. seals the existing keyring password to the local TPM with
   `systemd-creds`
4. decrypts it only into systemd's protected runtime credential directory
5. unlocks the existing login collection over session D-Bus
6. starts GNOME RDP and the bridge only after that oneshot succeeds

GDM can start the user manager slightly before GNOME Keyring owns the Secret
Service name. The unlock helper now tolerates that specific race for up to 120
seconds, and the oneshot remains visibly active after success. A wrong
credential still fails closed.

The configurator and installed unlock helper use Ubuntu's
`/usr/bin/python3` explicitly. This prevents an activated Conda environment
from hiding the system `python3-gi` package and turning an idempotent status or
enable operation into an unnecessary package-install attempt.

## 8. Treat teardown as a production path

One controlled descriptor-guard restart exposed a harmless but noisy cleanup
race: Xvfb removed `/tmp/.X20-lock` between process termination and the
launcher's attempt to read its owner. Because shell redirections happen before
the command runs, the missing-file message escaped the command's original
error suppression. Cleanup now checks readability and redirects standard
error before opening the lock file. It removes a stale lock only when the
recorded owner is exactly the supervised Xvfb PID.

## 9. Validation matrix

| Boundary | Evidence |
| --- | --- |
| Approved UU binary | Full hash and exact patch signatures |
| Input hook | Initialization record without key content |
| Normal-token broker | Original count and `error=0` |
| Phone text | `text=normalized`, plus exact visible acceptance string |
| Local RDP | Configured port owned by GNOME RDP |
| Runtime deployment | Installed source digest matches checkout |
| Descriptor health | Limit and current count below restart threshold |
| Former timed exit | Same UU server PID after 270 seconds |
| Unattended boot | Current-boot unit order and successful keyring oneshot |

The broad lesson is to test the complete behavior, not the presence of a flag,
process, or file. Every useful discovery was converted into either a
fail-closed check, bounded recovery behavior, a regression test, or an
explicitly documented limitation.

## 10. Do not equate `SendInput` acceptance with delivered text

A later controller test exposed a subtler failure: typing worked, but fast
phone input needed repeated taps and omitted characters. The current broker
generation recorded 54 normalized Unicode requests and 446 routine requests;
all returned their exact source count with `error=0`. Most text requests were
the expected two-record Unicode down/up pair. There was no current descriptor
exhaustion and no pipe failure.

That evidence moved the fault boundary downstream of the API return. The
broker was asking Wine to enqueue whole translated bursts immediately after an
unchecked `SetForegroundWindow`, then reporting success. It also synchronously
flushed early routine diagnostics, mostly mouse motion, on the serial input
path. Neither behavior proves that SDL FreeRDP has focused and consumed a key.

The correction has three parts:

1. confirm that `Ubuntu-Desktop-Relay` is the foreground window, retrying for
   at most 300 ms and failing explicitly if focus cannot be acquired
2. preserve request ordering but submit translated text as individual
   character chords, waiting 8 ms per character by default before acknowledging
   the source request
3. use separate bounded text, keyboard, mouse, and other telemetry quotas,
   buffer successful logs, and flush failures immediately

The delay is persisted as `UURB_TEXT_KEY_DELAY_MS` and can be changed safely:

```bash
./install.sh --skip-packages --skip-account-login --text-key-delay-ms 8
```

The diagnostic line records only category, `focus`, `focus-wait-ms`, pacing,
boundary timing, counts, and result codes. It does not record what was typed.

## 11. Separate upstream transport loss from local input injection

A direct-RDP comparison later stayed responsive while individual keys sent by
UU lagged or disappeared. The local broker showed successful calls with
`focus-wait-ms=0`, and the relevant processes were neither CPU- nor
memory-bound. UU's own aggregate logs instead showed forced relay sessions
with roughly 289-346 ms average delay, peaks near 533 ms, and explicit key
watchdog releases at a 300 ms threshold.

That evidence places the loss before the local bridge. Retrying or synthesizing
keys on Ubuntu would be unsafe because delayed originals could still arrive.
It also did not justify changing the proven ordinary-input routing. A later
attempt to choose the broker from `FindWindowW` visibility caused a complete
mouse and keyboard regression: the service-side process could not reliably see
the relay window, so it selected the denied original path without reaching the
fallback. Broker startup lines appeared, but no new calls reached it.

The exact proven behavior was restored: ordinary input tries the original API
and falls back to the broker on failure; Unicode phone text still routes to the
broker directly for normalization. A source-level regression test now guards
that fallback. The lesson is to optimize only after measuring the boundary in
the same Wine token and window station that executes it.

`uu-remote network` summarizes the latest completed transport report without
printing IP addresses, client IDs, account data, or typed content. Reports are
ordered by their embedded completion timestamp rather than filename, and a
report older than five minutes is explicitly marked stale. It also retains the
important counterexample: earlier automatic sessions may show P2P punching
blocked by NAT/firewall and an even slower relay fallback. Connection mode
should be selected from measured delay, not from the word “P2P” alone.

## 12. Check which adapter UU actually binds

A second Ubuntu host remained smooth on the supported `v0.1.0` runtime, while
this workstation lost fast physical-key events. Reinstalling that exact runtime
did not change the symptom. Timing instrumentation then put a strict boundary
around the local path: bridge and broker calls normally completed in 0-4 ms,
the observed maximum was 17 ms, every observed call returned its requested
count with `error=0`, and some missing key-downs never reached the hook at all.

That ruled out broker pacing, GNOME RDP, CPU load, and local pipe latency as the
cause of those missing events. UU's 300 ms key watchdog was also not the source
of the key-down loss: disassembly and live logs showed that it repairs stale
pressed-key state after transport loss. Lowering its registry interval would
make held keys and modifiers less reliable, so the temporary override was
removed.

The machine-specific difference was its adapter topology. Ubuntu had two
active default routes and correctly preferred the lower-metric route. Wine's
adapter list put the other interface first, and UU selected that first entry
instead of Ubuntu's route. UU therefore bound a slower path whose source address
could be routed asymmetrically through the preferred interface.

A controlled process-local A/B test changed only UU's visible adapter list. It
made UU bind the preferred interface, reduced room-login time from about 577 ms
to 315-384 ms, and improved the UDP probe from 1,135 of 1,140 replies to
1,138-1,140. In the best filtered run all replies arrived before the timeout.
No route, firewall, NetworkManager, Docker, desktop, or input code changed.

The permanent filter wraps `getifaddrs()` and `if_nameindex()` only inside UU's
Wine service tree. It exposes the selected interface plus loopback and keeps a
copied view so the original libc allocations remain intact. It is deliberately
fail-open: an absent setting, invalid value, unavailable interface, missing
default route, or allocation failure leaves the original adapter list visible.
The default installation mode remains `all`, preserving the known-good host.

On an affected multi-homed host, choose Ubuntu's lowest-metric default route at
each service start:

```bash
./install.sh --skip-packages --skip-account-login \
  --network-interface default
```

A fixed Linux interface name is also accepted. Roll back without removing the
bridge or account state:

```bash
./install.sh --skip-packages --skip-account-login \
  --network-interface all
```

`verify.sh` now checks both the mapped filter and the concrete interface in the
running UU server environment. The existing quarter-second supervisor reuses
its bounded health cycle to compare the preferred interface every ten seconds.
If the default moves, it exits once and lets systemd rebuild the complete relay
on the new route. This avoids a second watcher while preventing a long-running
UU process from remaining pinned to a stale adapter.

## 13. Make physical-key experiments observable and reversible

After the preferred adapter reduced aggregate relay delay, the operator still
reported the same fast-typing loss. That disproved the adapter mismatch as the
complete explanation. The earlier `routine` diagnostic quota was also
insufficient: mouse movement consumed it before the first physical-key call,
so an apparently empty keyboard trace was not evidence that no key arrived.

The bridge and broker now classify calls as `text`, `keyboard`, `mouse`, or
`other`, with an independent bounded quota for each category. Timing fields
separate the original API, broker pipe, injection, and total call boundaries.
They record neither key codes nor typed content.

A second persistent setting adds optional physical-key back-pressure:

```bash
./install.sh --skip-packages --skip-account-login \
  --physical-key-delay-ms 8
```

Its repository default is zero so an already-working host does not change.
The delay occurs only after the broker has accepted a physical-key segment.
There is no retry, replay, or inferred key, avoiding duplicate input if an
original event arrives late. The quick verifier checks that the running broker
uses the saved value.

## 14. Separate a stale RDP client from an unhealthy desktop

A later macOS Windows App attempt remained on **Configuring**. XRDP had several
established TCP handlers, and every attempt reached TLS but stopped before
capability exchange. Xorg, GNOME Shell, and the localhost VNC mirror were still
alive. A local FreeRDP authentication-only probe advanced through capabilities
immediately, placing this failure on the controller side rather than in the
Ubuntu desktop.

Restarting XRDP cleared the handlers, but Ubuntu's unit dependency also
restarted the main session manager. The old Xorg session initially survived;
when Windows App later connected, the new manager created another display and
the configured single-session lifecycle ended the old display. This is why a
server restart is not the safest first response when VNC mirrors an XRDP
display.

The decisive recovery was smaller: gracefully quit the several-days-old
Windows App process and reopen it. The next attempt immediately progressed
through capabilities, authentication, `login successful`, and `connected ok`.
Future recovery should therefore reset the client first and restart XRDP only
when its listener is demonstrably unhealthy.

Creating the fresh desktop also caused the supervised UU bridge to restart and
attach to that desktop. The operator reported a drastic UU keyboard
improvement, although a few letters could still be omitted at the fastest
typing speed. Content-free metadata showed that all physical-key calls which
reached the hook had `focus=ready`, `paced-physical=1`,
`physical-delay-ms=8`, matching result counts, and `error=0`.

That observation validates the improvement from the combined fresh-relay and
pacing state, not a complete fix or either change in isolation. The logs prove
that recorded calls were accepted, but their privacy boundary deliberately
prevents reconstructing the intended text or proving that the controller sent
every event. The next bounded experiment was therefore 12 ms of physical-key
pacing. A reconnect is required after changing the setting; otherwise typing
can occur through an older or different path and is not evidence about the new
value.
The reusable commands, warnings, and rollback are in
[XRDP Client Stall and UU Keyboard Recovery](xrdp-and-keyboard-recovery.md).

The fresh XRDP session then changed size dynamically with the Windows App
window. Its live desktop became smaller than UU's persistent private relay,
which made UU render the desktop at the left of a larger white canvas. Reducing
UU to that window size removed the white region but made the desktop too low
resolution. The correct recovery restored the live XRDP display to
`1620x1080` with the existing local FreeRDP resize helper, then set UU to the
same size.

That helper initially printed the complete FreeRDP usage page: FreeRDP 3 now
rejects its explicit `subtype:0` keyboard option. Omitting that field retains
the default subtype, preserves the declared Japanese layout and keyboard type,
and allowed the in-place resize to complete. The GNOME session survived; the
active RDP viewer could disconnect briefly, and the VNC mirror was reattached
to the resized display.

## 15. Remove the lossy keyboard hop instead of adding more delay

The 12 ms physical-pacing trial still omitted fast letters, Enter, and Ctrl
combinations. The broker's content-free sample contained 219 physical-key
calls, and every recorded call reported a matching result and `error=0`.
Injection commonly spent the configured 12 ms inside the broker, while total
call time occasionally rose much higher. More pacing would increase upstream
back-pressure without proving that SDL FreeRDP and GNOME RDP consumed every
accepted Windows event.

Direct RDP typing into the same XRDP Xorg desktop remained normal. The target
display exposed XTEST, and its scan-code map was verified for normal keys,
Enter, both Ctrl keys, navigation keys, keypad Enter, and Super/Menu. That made
a narrower architecture possible: keep UU's video, mouse, clipboard, and phone
text on the established local RDP relay, but route physical keyboard-only
arrays from the normal-token broker to a native X11 helper on the target
desktop.

The implementation is intentionally additive:

- repository and migrated-install defaults remain `keyboard-route=rdp`
- `x11` is opt-in, while `auto` chooses it only for an X11 target
- the helper binds loopback on an ephemeral port and requires a fresh token
- the entire bounded request is mapped before the first XTEST event
- unsupported or unavailable preflight falls back to RDP before injection
- an ambiguous partial failure is not replayed
- disconnect releases tracked held keys, and helper exit restarts the service
- the physical delay becomes a minimum hold time on X11; zero adds no broker
  back-pressure

An isolated Xvfb test then sent a fast 58-event stream containing Ctrl+A,
Enter, and every Latin letter. The target observed exactly 29 presses and 29
releases, including both Ctrl and Enter transitions. The live workstation was
deployed with:

```bash
./install.sh --skip-packages --skip-account-login \
  --keyboard-route x11 --physical-key-delay-ms 0
```

The verifier confirmed that the native helper, broker route, target Xorg
display, runtime digest, and all pre-existing relay components were active.

The operator then reconnected through direct UU and reported very smooth
typing, with almost all prior omissions resolved. The bounded broker sample
independently contained 256 physical-key calls after the final X11 startup
line; every sample used `route=x11`, returned one requested event, and reported
`error=0`. This closes the main local conversion defect. It does not justify
host-side retries or a claim that UU's upstream controller/network can never
omit an event, so the no-replay safety rule remains.

## 16. Explain why the old route looked partly healthy

The former design was not an arbitrary detour. It was the portable route that
also worked with a Wayland target, where an XTEST helper cannot inject directly
into the desktop:

```text
UU controller
  -> Wine user-token input broker
  -> Windows SendInput queue
  -> SDL FreeRDP
  -> GNOME RDP/libei
  -> XRDP Xorg desktop
```

The broker solved the first proven problem—UU's service token received access
denied—but its successful `SendInput` result described only the beginning of
that chain. It meant Wine accepted the requested records. It did not prove
that every later event loop, keyboard conversion, focus boundary, and RDP hop
delivered every key transition to the final Xorg application.

This distinction explains the otherwise confusing symptoms:

- **Slow typing often worked.** A pause between keys gave the nested queues and
  event loops time to drain. It reduced the symptom without removing the
  unreliable conversion boundary.
- **Fast typing lost letters.** Physical keyboard input consists of discrete
  key-down and key-up edges, commonly arriving in small separate requests.
  Losing or delaying either edge changes the result; an intermediate event
  cannot safely be merged with the next one.
- **Enter and Ctrl combinations were especially fragile.** A missing Enter
  edge removes the action completely. A missing modifier press or release can
  invalidate the complete shortcut or leave transient modifier state behind.
- **The mouse could still look healthy.** Pointer motion is state-like: many
  applications can coalesce intermediate coordinates and display the newest
  position. Mouse clicks also occur much less frequently than a fast stream of
  keyboard edges. A visually smooth pointer therefore did not prove that the
  keyboard path was lossless.
- **More pacing only helped partly.** It lowered burst pressure but retained
  every conversion and acknowledgement boundary. At 12 ms, all 219 sampled
  broker calls were still accepted while the operator could reproduce missing
  keys.

The direct route changes only the failing part:

```text
UU controller -> normal-token broker -> authenticated X11 helper
              -> XTEST + XSync -> XRDP Xorg desktop
```

At the `v0.2.0` acceptance boundary, video, mouse, clipboard, and phone text
remained on the established relay. The physical keyboard no longer passed
through Wine's input queue and two nested RDP keyboard conversions. An
isolated test preserved all 58 requested press/release transitions, and the
accepted live sample contained 256 successful `route=x11` calls while the
operator reported smooth typing.

Those observations localize the dominant workstation defect to the old local
nested route or its resulting back-pressure. They do not identify one exact
proprietary UU, Wine, SDL FreeRDP, GNOME RDP, or libei function as the sole
culprit, and they cannot guarantee that the controller or network upstream of
the broker will never omit an event. This is why the fix removes the measured
bad boundary instead of adding retries or making a broader unsupported claim.

## 17. Reuse the proven direct route for normalized phone text

A later live A/B test made the remaining boundary equally clear. The UU
computer-keyboard panel was exact through `route=x11`, while the phone's normal
keyboard visibly omitted several characters. For one fixed 13-character ASCII
trial, all 13 text requests reached the current broker, each was normalized,
and every call returned its complete source count with `error=0`. Only eleven
characters appeared in the target. The controller and broker had therefore
done their work; loss remained after Wine accepted the translated chords on
the nested RDP route.

The narrow correction keeps `VkKeyScanW` normalization unchanged, then offers
the complete translated keyboard-only array to the already authenticated X11
helper before requesting relay focus or calling `SendInput`. A failure known
to happen during preflight can still use RDP because nothing was injected. An
ambiguous partial X11 failure returns an error and is never replayed.

The broker also used to send the small request header and event array in two
loopback TCP writes. Nagle/delayed-ACK interaction made otherwise healthy X11
requests take about 41 ms. The request is now one packet and the socket enables
`TCP_NODELAY`; new live physical-key metadata measured 0 ms broker/helper
round trips without changing event semantics.

An isolated acceptance test sent a fixed 26-letter Unicode batch into the
Windows broker. The broker reported `route=x11-text`, returned all 52 source
records with `error=0`, and the X11 target observed exactly 26 presses and 26
releases in order. The reusable test is:

```bash
./scripts/test-x11-phone-text.sh
```

This improves layout-representable text. It does not turn XTEST into a general
Unicode or IME protocol: a character that `VkKeyScanW` cannot represent still
fails explicitly, and Wayland hosts retain the compatible RDP route.

The deployed workstation then completed the real acceptance test through the
phone's normal keyboard. The operator reported that typing was fixed. The
first 72 bounded live text records independently used `route=x11-text`, each
returned its complete source count with `error=0`, and broker/helper processing
took 0-2 ms. No typed character or key value was recorded. This confirms that
the successful visible result came from the new route rather than the still-
available RDP fallback or the computer-keyboard panel.

## 18. Separate a “finding routes” stall from transport routing

An accepted in-place update from UU 4.33.0.8907 to 4.34.0.8979 passed file,
login-state, relay, and warm-runtime checks, but a later cold launch left the
controller indefinitely at “finding routes.” The new server log stopped at
`update_gvinput start`; it had not yet joined its signaling room, so changing
the physical network route could not address that state.

The first bounded experiment made the audited `devcon.exe` unavailable. That
had previously made controller-time input initialization return in about one
second, while the unsupported executable consumed one CPU for 84–218 seconds.
A no-op executable returning success was also rejected: UU waited for the
kernel device to appear after the process returned. A fake success was
therefore less correct than an immediate, explicit “file not found.”

Because 4.34 still failed its production cold-start boundary, automatic
promotion was disabled and the complete preserved 4.33 prefix was restored
with an atomic same-filesystem directory swap. The 4.34 prefix was retained
for analysis. XRDP remained active with the same PID throughout. Reinstalling
the exact committed 4.33 runtime passed every bridge check—but its first cold
start reached the same high-CPU scan. That disproved “4.34 alone is broken”
and localized the real state outside the release executable.

The dedicated prefix's `system.reg` was 34,389,195 bytes and contained:

- 527 stale `ROOT\HIDCLASS` `gvinput` devices;
- 518 matching fake mouse devices;
- 1,044 matching `gvinput.inf`/`gvinputmf.inf` class instances; and
- 21,894 `WINEBTH\DEVICE` roots represented by 87,582 registry sections.

Ubuntu exposed only 29 `/sys/class/input` entries. Bluetooth discovery was
active, and Wine had retained every observed Bluetooth address in this
long-lived dedicated prefix. UU's startup detector synchronously traversed the
amplified device registry at about 190% CPU before signaling.

The repair was deliberately prefix-local:

1. Retain a private complete `system.reg` backup.
2. Validate that every target root HID/mouse device belongs to `gvinput`.
3. Remove those stale enum records, matching class records, and unsupported
   driver services.
4. Set Wine's `winebth` service to disabled and remove its accumulated device
   records.
5. Keep Ubuntu Bluetooth, XRDP, routes, DNS, and the firewall unchanged.

After cleanup, `system.reg` fell to about 3.9 MB. Two consecutive cold starts
recorded `input_device_count:0`; `update_gvinput` completed in 8–9 ms and the
signaling room reached `room_state_changed: created` about four seconds later.
The 4.33 account state and the existing XRDP PID were unchanged.

The permanent implementation is `scripts/clean-wine-device-registry`, backed
by the fail-closed inspector `scripts/inspect-wine-device-registry.py`. The
installer suppresses only an audited `devcon.exe`, keeps
`devcon.exe.uu-original`, and runs the idempotent cleanup before startup.
Operators can safely rerun the same transaction with:

```bash
uu-remote repair-registry
```

Future release acceptance must include a genuinely stopped-prefix cold start
and fresh signaling-room evidence. A warm process check can prove that an
already-running relay survived; it cannot prove that startup-only driver and
device enumeration will finish.

## 19. Separate device visibility from a connectable media session

The host later appeared in every UU controller, but selecting it waited
forever. This was not another route-selection failure: the server log showed a
real controller participant and peer states 1 through 3. It then stopped at
playout initialization, before a usable media path or connected device entry.

Three bounded audio experiments localized the failure:

1. Forcing `PULSE_SINK=xrdp-sink` and `PULSE_SOURCE=xrdp-source` left Wine
   enumerating duplicate stale XRDP nodes and prevented signaling startup.
2. `UURB_UU_AUDIO=off` removed every GameViewer PipeWire stream and restored
   host visibility, but an actual controller stopped at
   `AudioDeviceModuleImpl::InitPlayout`.
3. Wine ALSA pointed at a private `type null` playback/capture namespace. Both
   media factories initialized immediately, signaling connected, and the room
   reached `created`, while `wpctl status` and `/proc/asound` showed no UU
   access to the speaker, webcam microphone, or another physical PCM.

The resulting boundary is prefix- and service-scoped: disable `winepulse.drv`,
select Wine's ALSA driver only in the UU prefix, and set `ALSA_CONFIG_PATH` only
for `uu-remote-bridge.service`. Do not alter global ALSA defaults or restart
PipeWire, WirePlumber, XRDP, GDM, or GNOME.

A second defect appeared during the same cold-start work. The bootstrap helper
minimized UU's layered Wine/Qt management window while Qt was replacing its
top-level X windows. `xdotool` received `BadWindow`, the GUI IPC client closed,
and the server destroyed the newly created signaling room. Keeping that window
mapped behind the supervised full-screen relay removed the race. Hiding a
management window is cosmetic; preserving its IPC lifetime is functional.

The complete acceptance boundary is deliberately stronger than “the device is
online”:

- both `create pc factory ... success` records occur;
- signaling reports success and the room reports `created`;
- a fresh controller participant reaches peer states 1 through 3;
- media initialization returns and video capture starts; and
- no GameViewer stream or physical PCM appears when silent audio is selected.

## 20. Route mouse input with the relay architecture, not its old focus gate

After the native loopback VNC relay restored a connectable video session, a
controller could see the desktop but could neither click nor type reliably.
Fresh privacy-safe broker records made the mouse failure deterministic:

```text
category=mouse route=rdp focus=timeout result=0 error=21
```

The input hook and normal-token broker were both healthy. The mismatch was
architectural: the old mouse fallback searched for a Wine window titled
`Ubuntu-Desktop-Relay`, requested Win32 foreground focus, and then called
`SendInput`. The replacement relay is a native Linux VNC viewer. X11 correctly
focused that native window, but Wine could not represent it as the expected
foreground `HWND`, so every mouse record failed before injection. Restarting
XRDP, changing the network, or repeatedly forcing focus could not repair that
boundary.

The correction extends the already authenticated direct-X11 protocol instead
of adding another daemon or restoring the fragile nested RDP viewer. Protocol
version 2 carries bounded keyboard and mouse records. The helper preflights the
whole request, then maps relative and normalized absolute movement, left/right/
middle/X buttons, and vertical/horizontal wheel events to XTEST on the selected
live X11 desktop. Unsupported preflight still falls back before injection; an
ambiguous partial failure is never replayed. Disconnect cleanup now releases
held mouse buttons as well as keys. Hosts that retain
`UURB_KEYBOARD_ROUTE=rdp` are unchanged.

The live XRDP desktop had also resized from 1680x1050 to 1920x1080 while the
private UU canvas remained at the older size. The saved relay resolution was
aligned to 1920x1080 before one bridge-only restart, preserving XRDP and every
open desktop application.

The reusable isolated acceptance is:

```bash
./scripts/test-x11-mouse.sh
```

It sends normalized absolute motion plus a complete left click through the
Windows broker. The isolated X server observed the exact expected pointer
position and ordered click/wheel transitions; broker metadata reported
`route=x11-mouse result=6 error=0`. The existing 52-transition phone-text test
and all 97 repository tests continued to pass. Live verification then confirmed
that the private canvas and selected desktop were both 1920x1080 and that the
same supervised X11 helper remained active; no XRDP, GNOME, GDM, PipeWire, or
WirePlumber process was restarted.

## 21. Preserve dictated text semantics instead of turning it into keys

Direct UU phone input later exposed a different boundary. English dictation
worked, but a second line behaved like a real Enter and Chinese commits failed.
The broker evidence separated this from network loss: most phone characters
arrived as paired `KEYEVENTF_UNICODE` records and returned exact counts, while
212 non-representable requests ended with Windows error 1113. The bridge was
faithfully converting a newline to `VK_RETURN` and relying on `VkKeyScanW` for
every other character. That is correct key emulation but incorrect text
semantics for a terminal prompt or arbitrary Unicode.

The correction is adaptive rather than replacing the proven key path.
Representable ordinary text still uses `route=x11-text`. Newline, tab, CJK,
emoji, and other non-representable commits use a bounded semantic-text record
over the existing authenticated loopback helper. The helper validates UTF-16,
normalizes CRLF, converts to UTF-8 in memory, gives the target `CLIPBOARD` and
`PRIMARY` selections to scoped `xclip` owners, and emits `Shift+Insert`.
Owning both prevents VTE from reading an older `PRIMARY`. Backspace remains an editing
key. Payloads are neither logged nor written to runtime files.

The first live retest exposed one more composition detail. UU could send
deletion/editing events around a revised dictation commit. The deletion reached
the target, while the Chinese replacement still took the old translation path
and returned error 1113, leaving the visible text stripped. The semantic route
therefore accepts ordered mixtures of ordinary keyboard/mouse records and
Unicode text, and treats every non-ASCII UTF-16 unit as semantic without
depending on Wine's `VkKeyScanW` result. Ordinary representable English remains
on the established fast route.

The first live semantic attempt exposed a timing and feedback defect. The
helper waited 20 ms and checked only that `xclip` remained alive; it could emit
`Shift+Insert` before the new clipboard owner existed, repeatedly pasting the
old clipboard. Bidirectional VNC cut-text could then echo target semantic text
back into the private display. The corrected helper polls
`XGetSelectionOwner`, fails without any paste if ownership is not confirmed,
sets RealVNC `ServerCutText=0`, and starts x11vnc with `-seldir recv`.
`ClientCutText=1` remains enabled for UU/private-to-Ubuntu copy, while reverse
feedback is intentionally blocked.

The isolated acceptance is:

```bash
./scripts/test-x11-clipboard-text.sh
./scripts/test-vnc-clipboard-relay.sh
```

It delivered an editing-key-plus-text batch, Chinese, two lines, and an emoji
whose surrogate pair was split across requests exactly into an editable GTK
application, then confirmed `route=x11-clipboard-text`, matching result count,
and `error=0`. The established fast-text and VNC-keyboard tests still passed,
so the change extends rather than replaces those known-good paths. The VNC
clipboard test additionally confirms receipt of client cut text, exact target
Unicode paste, and absence of target-to-private clipboard feedback.

## 22. Keep UU's terminal transport and replace only Wine's empty shell

UU's direct terminal on the Ubuntu bridge host appeared to fail with
`exit 0`. Server evidence showed the opposite: the controller request arrived,
verification succeeded, a terminal session opened, and UU returned
`code=0 message=ok`. The process then closed immediately. Running Wine's
bundled `powershell.exe` directly reproduced a silent successful exit, while a
self-directed UU terminal request using `cmd` delivered a unique marker. That
separated a missing shell executable from the UU account, signaling, ConPTY,
or network paths.

Adding localhost SSH would have duplicated authentication and introduced a
key plus persistent listener. The narrower correction preserves the proven UU
channel. A tiny Windows `powershell.exe` compatibility proxy receives the
existing ConPTY streams and forwards framed input, output, EOF, and resize
events to a native helper. The helper binds only IPv4 loopback, validates a
fresh inherited 256-bit token in constant time, caps concurrent sessions, and
opens the current user's login shell with `forkpty`. Commands and output are
never logged.

Installer and uninstaller guards compare the deployed executable with the
canonical proxy and refuse unknown files. The isolated test first proves that
a wrong token fails explicitly, then verifies exact native-shell, Chinese
UTF-8, home-directory, and `24x80` resize markers in a disposable Wine prefix.
The terminal broker joins the existing service supervision, so no new system
service, SSH daemon, password, desktop logout, or reboot is required.

The first real controller launch exposed one more process boundary that a
direct proxy test had hidden. `GameViewerServer.exe` inherited both bridge
variables, but UU used `CreateProcessAsUser` with a newly constructed default
environment for the ConPTY child. The proxy therefore reported “not
configured” before contacting the broker. The corrected launcher atomically
writes one exact, mode-0600 runtime handoff beside the proxy. The proxy prefers
the inherited values when present and otherwise discovers that sibling file
from its own module path. The acceptance test explicitly removes both
environment variables, exercises this fallback, and still rejects a wrong
token. Verification also requires exact schema, owner, mode, token, port, and
listener agreement.

The first working shell exposed a presentation-only edge case: at UU's real
`92x30` size, the visible prompt fit comfortably, but `$` appeared alone on
the next row. Capturing raw PTY output showed that the bytes before `$` were
longer than the row because the service had inherited GNOME VTE state. Login
startup added OSC title/working-directory markers and ANSI colors that VTE
knows are non-printing, while the UU/ConPTY path treated them as occupying
columns. Setting `PS1` before startup was not reliable because VTE and Conda
hooks run later. An intermediate `TERM=screen` boundary removed the wrapping,
but real-controller input then rendered at the upper-left: UU's ConPTY surface
expects xterm cursor semantics. The final fix keeps `TERM=xterm-256color`,
unsets only inherited VTE markers, and uses Bash's `PROMPT_COMMAND` after login
startup to replace the decorated prompt. The normal login files and aliases
still load. The integration test now fails if OSC title, prompt colors, or
cursor-home sequences reappear and requires the xterm identity explicitly.
