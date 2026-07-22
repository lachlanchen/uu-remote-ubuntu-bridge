# Input Behavior Tracks

The bridge has two independently useful keyboard paths. Calling them "v1" and
"v2" hides the important difference and can encourage an unnecessary upgrade
on a computer that already works. Semantic release tags remain available for
source history, while descriptive tags identify the behavior that an operator
has validated on a particular host.

## Parallel track names

| Descriptive tag | Source point | Intended host behavior |
| --- | --- | --- |
| `track-rdp-broker-v1` | Current union source with the saved `rdp` profile | Keep the original Wine broker and nested RDP keyboard path on a host where phone text and physical keys are already smooth |
| `track-direct-x11-v1` | Same union source with the saved `x11` profile | Use the authenticated X11/XTEST helper for physical keys and normalized phone text on an X11/XRDP host where accepted keys are lost by the nested RDP conversion |

Both aliases can point to the same source commit because the validated route is
a persistent runtime profile, not a forked implementation. The final `v1`
belongs to each independent track. It does not mean that the
RDP track is older or inferior to the X11 track. Both aliases are immutable;
future incompatible changes receive a new suffix instead of moving a tag.
The semantic tags `v0.1.0` and `v0.2.0` are also retained and never rewritten.

## RDP broker track

Use `track-rdp-broker-v1` when the host already passes all of these checks:

- UU video and pointer input remain stable
- the computer-keyboard panel handles rapid physical keys
- the phone's normal keyboard produces `abcXYZ123,.!?` exactly once
- no direct-X11 helper is needed

This is the known-good profile for the original smooth host. Migrating its
absent `UURB_TEXT_KEY_DELAY_MS` value intentionally preserves the original
unpaced behavior, and its keyboard route remains `rdp`. The exact historical
source is still available under `v0.1.0` for explicit rollback.

## Direct X11 track

Use `track-direct-x11-v1` only on a confirmed X11 or XRDP desktop after the
broker reports successful input but visible fast keys are still omitted. Its
runtime profile is:

```text
UURB_KEYBOARD_ROUTE=x11
UURB_PHYSICAL_KEY_DELAY_MS=0
```

The helper accepts only authenticated loopback requests and keyboard
categories. Video, pointer, clipboard, and the UU transport stay on the normal
relay. Unsupported text or a failed X11 preflight falls back without replaying
a partially handled request.

## Select a track

The maintenance configurator detects the saved keyboard route. It chooses the
RDP-broker track for `rdp` and the direct-X11 track for `x11`. An explicit tag
is clearer when handing a machine to another operator:

```bash
# Host whose compatible RDP/broker path is already smooth
./scripts/configure-updater.sh enable --track track-rdp-broker-v1

# X11/XRDP host validated with direct keyboard injection
./scripts/configure-updater.sh enable --track track-direct-x11-v1
```

The selected tag is the known-good reinstall point. The daily checker never
switches tracks, changes keyboard timing, or enables X11 routing by itself.
Changing tracks requires a visible installer command and a new acceptance test.

## Handoff record

Keep this record locally on each computer:

```text
Behavior track: track-rdp-broker-v1 / track-direct-x11-v1
Desktop type: Wayland / Xorg / XRDP
Saved keyboard route: rdp / x11 / auto
Phone keyboard abcXYZ123,.!?: pass / fail
Computer-keyboard rapid alphabet: pass / fail
Quick verifier: pass / fail
```

Do not commit the hostname, UU account, controller identity, raw logs, or other
machine-specific data. Use the
[mobile keyboard parity handoff](mobile-keyboard-parity-handoff.md) when the
same controller behaves differently on two computers.
