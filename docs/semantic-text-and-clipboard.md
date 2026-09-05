# Semantic phone text and clipboard relay

UU exposes physical keyboard events, phone-IME Unicode commits, and clipboard
updates as different input classes. They must remain separate. Treating a
dictated newline as a physical Enter submits a terminal prompt, while reducing
CJK text to the current XKB layout rejects characters that have no key chord.

## Adaptive phone-text route

`UURB_PHONE_TEXT_MODE=auto` is the default:

- ordinary layout-representable text keeps the selected low-latency keyboard
  route (`rdp` by default, or XTEST on the opt-in direct X11 track);
- newline, tab, CJK, emoji, and other non-representable Unicode use semantic
  clipboard text plus a synthesized `Shift+Insert` paste;
- Backspace remains an editing key and is never converted to clipboard data.

In `auto` mode, a Unicode composition batch containing Backspace uses the
bounded semantic editing path even if its replacement is entirely ASCII.
Plain ASCII insertion keeps its fast route, and a physical Backspace without
Unicode text remains an ordinary key.

The clipboard path is available when the selected desktop exposes an
authorized X11 or Xwayland display and the native helper is active. This also
works with the default RDP relay. In that split mode, the helper owns the
physical desktop clipboard but emits the paste chord into UU's private Wine/
FreeRDP display; the existing RDP session carries that chord to the focused
physical application. Routine keyboard and mouse events remain on RDP. This
avoids both Wine's broken Unicode-to-FreeRDP conversion and a second remote
desktop session.

The Wine broker sends a bounded UTF-16 request over the existing
token-authenticated loopback connection. The native helper
validates it, joins split UTF-16 surrogate commits, converts it to UTF-8,
normalizes CRLF to one newline, makes `xclip` own both the target desktop's
`CLIPBOARD` and `PRIMARY` selections, verifies both owners through X11, and only
then emits one paste chord. Owning both is required because VTE terminals read
`PRIMARY` for `Shift+Insert`, while other applications may read `CLIPBOARD`.
Each commit keeps persistent owners and reads `xclip`'s private request counter.
The new pair takes ownership **before** the old pair is retired. Replacing a
selection must not introduce an owner=None gap; see the GNOME race below.
It first waits for eager clipboard-manager reads to become quiet, emits the
paste chord, and then requires a new `CLIPBOARD` or `PRIMARY` request before it
reports success. This matters on a full GNOME desktop: a clipboard manager may
legitimately request the new `CLIPBOARD` value before the focused application,
so ownership—or a fixed timer—does not prove that any text reached the target.
The helper serves semantic requests serially, preventing a following dictation
update from replacing the selection before the application consumed the
earlier commit. The acceptance test includes one eager clipboard-manager read
per fresh owner pair and verifies the later target request independently.
Composition Backspace is limited to text inserted recently by the same broker
client. A new client, an idle gap, or unrelated keyboard/mouse input clears
that allowance, so a fresh dictation commit cannot erase a message that was
already present in the target field. Continuous revisions can still replace
their own provisional text during the bounded activity window. Each accepted
Backspace pair is flushed and briefly paced at the X11 boundary; without that
small edit-only delay, a full GNOME application may process only the first few
events from a long revision even though XTEST accepted the whole batch.
If either new owner is not confirmed, the manager reads never settle, or no
post-chord selection request arrives within a bounded interval, the helper
fails closed and does not grant broker revision credit. It never writes the
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

Continuous dictation can grow one provisional Windows `SendInput` call far
beyond a normal keystroke pair. The original 64-record transport therefore
accepted a short phrase but rejected live calls of 70, 76, 92, 98, 114, and
332 records with `result=0 error=5`. The bridge now preserves one complete call
through a bounded 2,048-record transaction. It deliberately does not split a
semantic text call into several clipboard pastes: X11 selections are lazy, so
rapidly replacing the owner can make every queued paste read only the final
fragment. A call beyond the bound fails before injection rather than partially
replacing text.

Clipboard paste deliberately leaves the committed text in the desktop
`CLIPBOARD` and `PRIMARY` selections. This makes a later manual paste useful,
keeps `Shift+Insert` deterministic across application toolkits, and avoids
racing an asynchronous selection restore. Do not test this path in a password
field.

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
./scripts/test-rdp-semantic-text.sh
./scripts/test-x11-clipboard-text.sh
./scripts/test-vnc-clipboard-relay.sh
```

The first pass creates separate clipboard and Wine relay displays. It proves
that `UU broker 中文 123` crosses the default RDP semantic path exactly, the
paste chord reaches only the private relay window, and a separate ASCII batch
still reports `route=rdp`.

The second pass proves that Chinese, an emoji split across two commits, two
lines, and a 2,000-record Unicode composition survive exactly, the target app
receives one real paste for the long composition, and broker metadata reports:

```text
route=x11-clipboard-text error=0
```

The third pass proves that a client cut-text packet reaches the isolated VNC
server, reverse clipboard feedback is disabled, and a target-side Unicode
paste remains exact without a loop.

Retain the established regression tests as separate boundaries:

```bash
./scripts/test-x11-phone-text.sh
./scripts/test-vnc-keyboard-relay.sh
```

The first proves the fast representable-text route, including one 2,000-record
call delivered in exact order. The second proves physical symbols and CJK
keysyms through the nested VNC keyboard path.

## Mixed-language revision regression

A follow-up regression test on 5 September reproduced another way to lose
earlier text, even with the clipboard handoff and socket-deadline fixes below.
Every broker request returned its full count with error0, but the final editor
contents were wrong: the preceding four-character Chinese phrase disappeared.

The causes were in composition accounting, not the physical keyboard layout:

1. An ASCII-only replacement after Backspaces took the fast key route. That
   path neither bounded the deletions against recent composition text nor
   subtracted them from the allowance. Switching the replacement language to
   Chinese changed deletion behavior unexpectedly.
2. Within one semantic request, inserted characters were credited only after
   all events were processed. A text/Backspace/text sequence could therefore
   drop a legitimate edit, then grant too much allowance to a later revision.

The repair keeps all Unicode editing batches on the same bounded semantic
path, irrespective of replacement language. Prospective insert credit follows
event order and is committed only when the request's segments succeed. Plain
ASCII typing, physical keys, mouse routing, the two-second activity window,
and the explicit legacy `keys` mode are unchanged.

`test-x11-clipboard-text.sh` includes `language-revisions`: Chinese → ASCII →
Chinese, excess stale Backspaces, and interleaved insert/delete operations.
It checks the complete editor contents, including text written by earlier
clients. Checking only transport success would miss this regression.

These are bounded GUI edits, not an atomic editor transaction. The bridge
cannot infer every application's selection, cursor movement from another
client, grapheme deletion rules, or phone IME composition boundaries. It never
replays ambiguous input. A real controller/app dictation test is still needed
after deployment; a passing fixture is not a claim that every phone is fixed.

## Live diagnosis

Only inspect content-free metadata:

```bash
tail -n 100 \
  "$HOME/.local/share/wineprefixes/uu-remote/drive_c/users/$USER/Temp/uu-input-broker.log" \
  | rg 'category=text|phone-text-mode'
```

Expected direct-X11 routes are `x11-text` for representable text and
`x11-clipboard-text` for semantic clipboard text. With the default RDP route,
ordinary text remains `rdp` and CJK, newline, emoji, or dictation text reports
`rdp-clipboard-text`. `error=1113` means the old key-only RDP path could not
translate a Unicode character; after this feature is deployed, CJK/newline
requests should no longer reach that failure when the selected physical
clipboard display is authorized.
On an older deployment, a bridge record with `count` above 64 followed by
`result=0 error=5` identifies the former continuous-dictation size limit. A
successful current deployment reports the full original count from both the
bridge and broker.

## September 2026 regression: GNOME ownership handoff and long revisions

Two independently reproduced defects explained the renewed missing Chinese
characters and dictation flushing. Neither needed a keyboard-layout change,
clipboard-manager disabling, or a network workaround.

### Clipboard restoration raced the replacement

On the affected shared GNOME/XRDP desktop, a temporary, explicitly focused
editor and a separate diagnostic helper reproduced 8/10, then 6/10 and 6/10
successful six-character CJK/punctuation commits. Failed commits returned
native error8195, mapped to broker error31, in about27–55ms. Content-free
diagnostics showed the CLIPBOARD xclip exiting normally before paste. XRes
client-PID lookup identified the new owner as `gnome-shell`.

The old helper killed its previous xclip owners before creating replacements.
That briefly made CLIPBOARD owner=None. GNOME's cached-selection restoration
could then arrive after the replacement had started and take its ownership.
The helper correctly refused a possibly stale paste, but the intended text
was lost. An isolated XFixes fixture modeling delayed restoration after the
None gap reproduced error31 with the old installed helper.

The fix is an ownership handoff: retain the old owned processes until the new
CLIPBOARD/PRIMARY pair is established and quiet, then reap the old processes.
The first same-desktop A/B retest passed10/10 exactly. The regression fixture
now verifies there is no ownership gap across ordinary commits, a split emoji,
dictation revisions, and a long Unicode composition. No retry, global daemon,
keymap change, or clipboard contents logging was added.

### The socket deadline was shorter than legitimate editing

A300-character provisional Chinese dictation commit succeeded, but its
608-record revision failed with result0/error1236. The helper deliberately
paces each Backspace pair by5ms:300 deletions require about1500ms. The broker's
fixed1000ms socket receive timeout therefore disconnected after deleting part
of the draft, before sending its replacement. This was independently
reproduced even after fixing the clipboard handoff.

The receive budget now covers the requested work: ordinary input retains
1000ms; a semantic selection request gets3000ms; each paced Backspace release
adds the shared5ms constant. Counts remain capped at2048 records, so the budget
is finite. This is a deadline, not an added sleep. Ambiguous input is never
replayed. The300-character revision now returns608/608/error0 and leaves the
unrelated editor prefix intact.

Run the expanded regressions serially:

```bash
python3 -m unittest discover -s tests -v
bash scripts/test-x11-clipboard-text.sh
bash scripts/test-x11-phone-text.sh
bash scripts/test-rdp-semantic-text.sh
bash scripts/test-vnc-clipboard-relay.sh
bash scripts/test-vnc-keyboard-relay.sh
```

All use disposable displays/prefixes, not the user's typing field. The gap
guard reads ownership events only, never clipboard data. Failed-test artifacts
are reported for inspection; successful fixtures clean their owned processes.

Both input binaries must be rebuilt (`uu-x11-input`, `uu-input-broker.exe`).
Use the normal guarded runtime deployment to retain the host's saved behavior
track. If an operator deploys only these two binaries, record that partial
deployment and their hashes privately; do not falsely stamp the entire pulled
runtime as installed. A bridge-only restart loads them and preserves the
underlying GNOME/XRDP desktop and applications. A pull alone does not update
the running input helpers, and reconnect/phone-client acceptance still matters.

Bounded diagnostics report failure stage and child exit metadata, never text.
They are evidence for a failure boundary, not proof of every upstream client
or every application's behavior. New focus changes or external clipboard
replacement during an already-started edit can still interrupt it; do not
promise arbitrary GUI edits are atomic or retry an ambiguous composition.
