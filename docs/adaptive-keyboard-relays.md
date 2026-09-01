# Adaptive keyboard relays

One shared Ubuntu X11 desktop can be reached through several very different
keyboard transports. Treating all of them as raw hardware scan codes is the
source of most apparently random symbol failures.

| Path | What should cross the boundary | Host responsibility |
| --- | --- | --- |
| XRDP | RDP keyboard metadata and scan codes | Let XRDP select the client-reported layout |
| RealVNC/x11vnc | X11/RFB keysyms | Keep `modtweak`, XKB lookup, and temporary keysym support enabled |
| UU computer keyboard | Physical Windows key events | Use the selected `rdp` or direct `x11` behavior track |
| UU native phone keyboard | Unicode commits normalized by the broker | Keep this separate from the physical-key path |

This distinction matters for a shared XRDP desktop. A Japanese Mac keyboard,
an ANSI keyboard, and a phone keyboard can all produce the same physical key
number while intending different symbols. No server-side layout guess can
recover information a client did not send. The robust rule is therefore:

1. preserve semantic keysyms or Unicode where the protocol supplies them;
2. use a raw layout only for a genuinely physical-key path;
3. never run a global `setxkbmap` loop to chase whichever client connected
   most recently.

For direct X11 targets, semantic text has a second distinction. Ordinary
representable characters remain key chords; newline, tab, CJK, emoji, and
other non-representable commits use the target clipboard and one paste chord.
This prevents a dictated newline from acting as a terminal submission and
avoids reducing Unicode to whichever physical layout is currently active.
See [semantic phone text and clipboard relay](semantic-text-and-clipboard.md).

## Dedicated nested VNC viewer

The VNC fallback is a private, full-screen viewer whose only job is to place
the selected Ubuntu desktop inside UU's canvas. It now defaults to:

```text
UURB_VNC_GRAB_KEYBOARD=on
```

The corresponding viewer receives `-GrabKeyboard=1`. This is important in a
nested chain: without the grab, the intermediate X desktop may consume Shift,
Ctrl, Alt, or Super while the base key still reaches the inner desktop. The
visible symptom is exact and misleading: `(` becomes `8`, `?` becomes `/`,
`@` becomes `2`, and Ctrl shortcuts stop working.

The localhost x11vnc boundary is launched explicitly with:

```text
-repeat -nobell -modtweak -xkb -add_keysyms
```

`modtweak` reconstructs the modifier chord required by the target XKB map,
`-xkb` uses the complete XKB keymap, and `-add_keysyms` permits semantic
keysyms that are not already present. VNC remains bound to IPv4 loopback and
has no unauthenticated LAN listener.

Disable the grab only when this is not a dedicated relay window:

```bash
./install.sh --skip-packages --skip-account-login \
  --vnc-grab-keyboard off
```

## Reproducible acceptance test

The repository includes a local RFB client and an isolated Xvfb test. It does
not touch the logged-in desktop, type into an application, or log the user's
text:

```bash
./scripts/test-vnc-keyboard-relay.sh
```

The probe checks 21 shifted punctuation symbols followed by `你好` against a
Japanese XKB target. A passing result is:

```text
vnc-symbols=23/23 order=exact target-layout=jp
isolated VNC keyboard acceptance passed
```

For operator acceptance, use a disposable text field and test all four input
classes separately:

- unshifted digits and punctuation;
- shifted symbols such as `()$&@"?!{}#%*+_|~<>`;
- Ctrl+A, Ctrl+C, Ctrl+V, Enter, and Backspace;
- Chinese or Japanese input through the intended IME.

Do not use a password field for keyboard testing.

## Scope and fallback

This correction does not change the live desktop's XKB layout, restart XRDP,
log out GNOME, or alter IBus. That preserves a known-good Japanese raw-key RDP
chain while making VNC semantic input independent of it. If one physical UU
client still needs a different raw layout, select the appropriate behavior
track or change that client profile explicitly; do not hard-code the shared
desktop for every transport.
