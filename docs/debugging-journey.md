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
3. use separate bounded text/routine telemetry quotas, buffer successful logs,
   and flush failures immediately

The delay is persisted as `UURB_TEXT_KEY_DELAY_MS` and can be changed safely:

```bash
./install.sh --skip-packages --skip-account-login --text-key-delay-ms 8
```

The diagnostic line records only `focus`, `focus-wait-ms`, `paced`,
`delay-ms`, counts, and result codes. It does not record what was typed.

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
printing IP addresses, client IDs, account data, or typed content. It also
retains the important counterexample: earlier automatic sessions may show P2P
punching blocked by NAT/firewall and an even slower relay fallback. Connection
mode should be selected from measured delay, not from the word “P2P” alone.

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
running UU server environment. There is no route watcher or retry loop; after
an intentional default-route change, restart the bridge once so `default` is
resolved again.
