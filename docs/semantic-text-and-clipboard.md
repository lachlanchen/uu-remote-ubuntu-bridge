# Semantic phone text and clipboard relay

UU exposes physical keyboard events, phone-IME Unicode commits, and clipboard
updates as different input classes. They must remain separate. Treating a
dictated newline as a physical Enter submits a terminal prompt, while reducing
CJK text to the current XKB layout rejects characters that have no key chord.

## Adaptive phone-text route

`UURB_PHONE_TEXT_MODE=auto` is the default:

- ordinary layout-representable text keeps the established low-latency XTEST
  key route;
- newline, tab, CJK, emoji, and other non-representable Unicode use semantic
  clipboard text plus a synthesized `Shift+Insert` paste;
- Backspace remains an editing key and is never converted to clipboard data.

The clipboard path is available only when the selected target is X11 and the
direct helper is active. The Wine broker sends a bounded UTF-16 request over
the existing token-authenticated loopback connection. The native helper
validates it, joins split UTF-16 surrogate commits, converts it to UTF-8,
normalizes CRLF to one newline, makes `xclip` the target desktop's clipboard
owner, verifies that ownership through X11, and only then emits one paste
chord. If the new owner is not confirmed within a bounded interval, the helper
fails closed and does not paste the previous clipboard. It never writes the
payload to logs or disk. A communication failure after an ambiguous injection
is not replayed.

Two explicit behavior tracks remain available:

```bash
./install.sh --skip-packages --skip-account-login \
  --phone-text-mode keys

./install.sh --skip-packages --skip-account-login \
  --phone-text-mode clipboard
```

`keys` preserves the former key-only behavior. `clipboard` pastes every phone
text commit except editing keys. `auto` is preferable because it retains fast
ASCII typing while fixing dictation revisions, multiline text, and non-English
commits. Composition editing keys may be interleaved with a semantic text
batch; the broker preserves their order instead of rejecting the whole batch.

Clipboard paste deliberately leaves the committed text in the desktop
clipboard. This makes a later manual paste useful and avoids racing an
asynchronous clipboard restore. Do not test this path in a password field.

## UU clipboard over the VNC desktop relay

The dedicated VNC relay intentionally permits only the UU/private-to-Ubuntu
direction:

```text
ClientCutText=1
ServerCutText=0
SendPrimary=0
SendInitialClipboard=0
ServerClipboardGraceTime=5000
x11vnc -seldir recv
```

`SendPrimary=0` is important. UU and Wine update the X11 `CLIPBOARD`
selection; preferring `PRIMARY` can send a stale selection or only the most
recent selected line. Initial transfer stays disabled so startup cannot
replace a user's clipboard. The reverse direction is also disabled at both
the viewer and x11vnc boundaries: semantic text placed on Ubuntu's target
clipboard must never echo into the private display and trigger another paste.

This channel is independent of phone-IME input. Copying text on a UU client
uses the VNC clipboard relay; typing or dictating into UU's phone keyboard uses
the adaptive broker route.

## Isolated acceptance

The test creates a temporary X display and Wine prefix. It does not type into
the logged-in desktop or inspect the user's clipboard:

```bash
./scripts/test-x11-clipboard-text.sh
./scripts/test-vnc-clipboard-relay.sh
```

The first pass proves that Chinese, an emoji split across two commits, and two
lines survive exactly, the target app receives one real paste, and broker
metadata reports:

```text
route=x11-clipboard-text error=0
```

The second pass proves that a client cut-text packet reaches the isolated VNC
server, reverse clipboard feedback is disabled, and a target-side Unicode
paste remains exact without a loop.

Retain the established regression tests as separate boundaries:

```bash
./scripts/test-x11-phone-text.sh
./scripts/test-vnc-keyboard-relay.sh
```

The first proves the fast representable-text route. The second proves physical
symbols and CJK keysyms through the nested VNC keyboard path.

## Live diagnosis

Only inspect content-free metadata:

```bash
tail -n 100 \
  "$HOME/.local/share/wineprefixes/uu-remote/drive_c/users/$USER/Temp/uu-input-broker.log" \
  | rg 'category=text|phone-text-mode'
```

Expected routes are `x11-text` for representable text and
`x11-clipboard-text` for semantic clipboard text. `error=1113` means the old
key-only path could not translate a Unicode character; after this feature is
deployed, CJK/newline requests should no longer reach that failure on an X11
target.
