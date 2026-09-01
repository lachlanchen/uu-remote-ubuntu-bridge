# Automated Repair Agent Handoff

This is the required operational memory for a Codex session launched by the
UU automatic updater. It summarizes the two-host investigation and points to
the detailed, versioned evidence. Read it before changing patch manifests,
input routing, process supervision, installer handling, or recovery behavior.

The updater copies task-specific release evidence into
`build/automated-repair/CONTEXT.md`. That generated file is authoritative for
the candidate version, hashes, staging paths, selected behavior track, and
safety boundaries. This handoff supplies the engineering history that must not
be rediscovered or accidentally undone.

## Objective

Produce a reviewable, proprietary-binary-free source repair for a newly
observed UU release while preserving the behavior already validated on two
different Ubuntu hosts. An automated session may audit, compare, write source
or a draft manifest, and run tests. It may not approve its own binary
interpretation or deploy to the live Wine prefix.

## The Two Validated Host Profiles

The hosts intentionally use different input tracks. Neither is a generic
"older" or "newer" machine.

### Known-good Wayland reference

The `OptiPlex-7090` reference used Ubuntu 24.04, GNOME 46 on Wayland, Wine 11,
and the compatible RDP/broker route. Both UU's computer-keyboard panel and the
phone's native keyboard were smooth. This host proved that the original
broker/RDP behavior can be correct and must remain available. Do not enable
XTEST globally or reinterpret this profile as broken merely because the other
workstation needs direct X11 input.

The complete snapshot and privacy-safe comparison procedure are in
[Mobile Keyboard Parity Handoff](mobile-keyboard-parity-handoff.md).

### Affected XRDP/Xorg workstation

The second workstation runs the live GNOME desktop inside XRDP/Xorg. On this
host, Wine accepted fast physical-key and normalized phone-text requests, but
events could disappear after broker acceptance in the nested
Wine `SendInput` -> SDL FreeRDP -> GNOME RDP -> Xorg chain. Deliberate slow
typing and 8 ms/12 ms pacing improved the symptom but did not eliminate it.

The validated profile is therefore:

```text
UURB_KEYBOARD_ROUTE=x11
UURB_PHYSICAL_KEY_DELAY_MS=0
```

The authenticated loopback X11/XTEST helper handles physical keys,
layout-representable normalized phone text, adaptive Unicode/multiline
clipboard paste, and mouse motion/buttons/wheel. The explicit UU clipboard
channel remains on the selected local desktop relay. The detailed
recovery and rollback are in
[XRDP Client Stall and UU Keyboard Recovery](xrdp-and-keyboard-recovery.md).

## Keyboard Boundaries That Must Stay Separate

UU exposes two keyboard surfaces:

1. The computer-keyboard panel emits ordinary physical Windows key events.
2. The phone's normal keyboard/IME emits `KEYEVENTF_UNICODE` text batches.

An acceptance test for one surface does not validate the other. The phone-text
path normalizes each representable character with `VkKeyScanW` into ordinary
modifier and virtual-key chords. On a direct X11 target, adaptive mode sends
newline and non-representable Unicode as semantic clipboard text plus one paste
chord instead of emitting an unrelated key.

Important evidence from the XRDP workstation:

- The early broken phone path could turn letters into one repeated key and
  numbers into punctuation.
- A later fixed 13-character A/B run reached the broker 13/13 times but only
  11 characters were visible through the nested RDP route.
- The isolated direct-X11 phone test preserved 52/52 transitions in exact
  order.
- The first 72 privacy-safe live phone-text calls used `route=x11-text`,
  returned exact result counts with `error=0`, and completed in 0–2 ms.
- The computer-keyboard panel was separately confirmed complete.

The helper still accepts bounded, non-Unicode keyboard records only. Unicode
interpretation belongs in the broker.

## Proven Troubleshooting Lessons

Preserve these decisions:

1. **Wine service-token input denial:** UU's signed Windows HID driver cannot
   run under Wine. The audited hook and normal-user broker adapt only the
   required `SendInput` boundary.
2. **API success is not visible delivery:** a matching `SendInput` result
   proves Wine accepted a request, not that every nested RDP hop delivered it.
3. **No replay after ambiguity:** delayed originals can still arrive. Never
   retry a possibly delivered key, modifier, or shortcut.
4. **Pacing is evidence, not the final XRDP fix:** 8 ms and 12 ms reduced
   pressure but retained the lossy conversion chain. The direct X11 route is
   the validated solution on the affected Xorg host.
5. **Small-packet latency was real:** writing the X11 request header and events
   separately caused about 41 ms latency. One coalesced write plus
   `TCP_NODELAY` reduced it to 0–2 ms.
6. **Source and runtime are different:** `git pull` does not update
   `~/.local/bin`, the Wine compatibility binaries, or the active service.
   Preserve runtime-digest verification.
7. **Long-session input loss had a separate cause:** Ubuntu's libei 1.2.1
   leaked received keymap file descriptors. The bridge-local reviewed backport,
   higher supervised descriptor limit, and bounded guard address it without
   replacing a desktop-wide library.
8. **Multi-homed adapter selection can affect UU transport:** keep the
   network-interface filter fail-open and host-specific. Do not modify system
   routes, DNS, NetworkManager, or firewall rules as an input workaround.
9. **Controller transport and host injection are different boundaries:**
   direct RDP can remain healthy while a forced/high-latency UU relay drops
   keys before they reach the hook. Do not synthesize host-side retries.
10. **XRDP client stalls are not bridge patch failures:** reset a stale
    Windows App client before restarting XRDP. XRDP, VNC, dynamic resolution,
    and the UU private capture canvas are related operationally but use
    distinct listeners.
11. **Process exits need bounded recovery:** Wine launcher exit alone must not
    create a restart storm. Preserve systemd rate limits, health confirmation,
    and the hardened behavior-track snapshots.
12. **Logs are privacy-bounded:** routine logging stops after quotas and never
    records keycodes or typed content. A quiet bounded log is not proof that an
    input API was never called.
13. **Wine driver installation can block connection setup:** on the affected
    workstation, a controller retry still reached UU's `devcon.exe` path even
    with the approved 4.33 server patches. Each unsupported `gvinput`/HID
    install consumed one CPU and delayed setup by roughly 84–218 seconds.
    Reversibly making only `devcon.exe` unavailable reduced the same input-init
    boundary to roughly 0.8–1.1 seconds. A success-returning stub was not
    equivalent because UU then waited for a kernel device that Wine cannot
    create. Preserve the audited vendor file as `devcon.exe.uu-original`.
14. **“Finding routes” can precede route selection:** a later cold start spent
    about two CPU cores in `update_gvinput` before signaling. The dedicated
    Wine registry contained 527 failed `gvinput` roots and 21,894 retained
    Bluetooth observations. Prefix-local cleanup and disabling Wine-only
    Bluetooth enumeration reduced the scan to 8–9 ms and restored fresh
    signaling-room creation. Do not change host routes, DNS, XRDP, Ubuntu
    Bluetooth, or the firewall for this symptom. Use
    `uu-remote repair-registry`; its fail-closed inspector refuses unrelated
    root devices and retains a private registry backup.
15. **Warm promotion checks are not cold-start acceptance:** UU 4.34 passed a
    warm guarded promotion but failed the next production cold start. The
    complete 4.33 snapshot was atomically restored without changing XRDP, and
    4.33 then reproduced the same registry scan. Require a stopped-prefix cold
    start, `update_gvinput end`, and fresh `room_state_changed: created`
    evidence for future releases.

The chronological evidence is in
[Debugging Journey](debugging-journey.md), and the reusable investigation
method is in [Methodology and Toolkit](methodology-and-toolkit.md).

## Automated Repair Action Contract

The updater-launched Codex session owns only its private repair checkout.

It may:

- inspect the generated task context and non-executing staged candidate;
- use `strings`, `xxd`, `objdump`, PE parsers, and repository audit scripts;
- compare complete hashes, sections, functions, signatures, and control flow;
- update compatibility source, tests, and documentation;
- create a manifest only with a non-approved review state;
- run focused tests and the complete proprietary-binary-free unit suite;
- return `ready_for_review`, `no_change`, or `blocked` through the required
  output schema.

It must not:

- run `sudo`, push, publish, or touch the source clone;
- edit the live Wine prefix, account state, keyring, desktop, or systemd units;
- execute an unknown installer outside the explicit staging sandbox;
- copy proprietary executables into Git;
- mark a new binary manifest `approved`;
- change the selected RDP/X11 behavior track;
- trade safety for an uninterrupted automatic deployment.

If the wrapper cannot be extracted without execution, return a precise blocked
result requesting the documented root-managed, network-isolated staging step.
Do not weaken the gate.

## Required Reading Order

1. Generated `build/automated-repair/CONTEXT.md`
2. This handoff
3. [Upstream Maintenance](upstream-maintenance.md)
4. [Security](security.md)
5. [Input Behavior Tracks](release-tracks.md)
6. [Automatic Checks and Resumable Repair](automatic-updates.md)
7. [Debugging Journey](debugging-journey.md)
8. [Mobile Keyboard Parity Handoff](mobile-keyboard-parity-handoff.md)
9. [XRDP Client Stall and UU Keyboard Recovery](xrdp-and-keyboard-recovery.md)
10. [Troubleshooting](troubleshooting.md)

## Evidence Required Before Any Live Upgrade

Automated completion is not live approval. A maintainer must still verify:

- complete installer and target-binary hashes;
- patch signatures and their surrounding instruction semantics;
- patch, expected-state verification, and byte-identical restore;
- no proprietary or private artifacts in Git;
- complete unit-suite success;
- disposable Wine/Windows behavior where required;
- controller video, mouse, reconnect, computer-keyboard, and native-phone
  keyboard acceptance;
- the selected host track remains unchanged;
- rollback is available before touching the healthy live relay.

The normal phone-keyboard acceptance string is `abcXYZ123,.!?`. On the direct
X11 track, require fresh content-free `category=keyboard route=x11`,
`category=text route=x11-text`, and `category=mouse route=x11-mouse` records
with matching result counts and `error=0`. On the compatible RDP track,
preserve its already-validated broker behavior rather than forcing the X11
helper.

## Privacy

Do not commit completed host handoff records, raw Codex JSONL, UU/NetEase logs,
installer archives, Wine prefixes, account identifiers, device identifiers,
network addresses, tokens, passwords, browser profiles, or desktop captures.
Keep task evidence under the updater's mode-0700 private state directory and
summarize only non-sensitive engineering conclusions in tracked documentation.
