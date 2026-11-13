# Fixing question marks and garbled Unicode in UU's mobile clipboard

Validated on 13 November 2026 with UU **4.44.1.3978**, Wine 11 and the
Ubuntu X11/VNC desktop relay. The affected direction was **copy on Ubuntu,
paste on a phone**. The phone confirmed readable Chinese, Japanese and emoji
after the final correction. This does not establish support for every client,
file/image transfer or a different UU release. The subsequent
[4.47 review](releases/4.47.0.5146-review.md) adds that build's exact call sites
and fixes startup attachment when the launcher and GUI share an executable name.

## Three boundaries, three different failures

| Boundary | Observed failure | Required correction |
| --- | --- | --- |
| Host X11 → Wine clipboard | Valid Unicode in the private X selection did not establish valid Win32 clipboard contents. | Publish fresh authorized host copies directly as `CF_UNICODETEXT`. |
| Wine clipboard → UU byte string | UU explicitly requested `CF_TEXT`; Wine's ANSI code page replaced CJK and emoji with `?`. | Return a bounded UTF-8 snapshot only for the reviewed export call. |
| Queued UU byte string → outgoing text | UU decoded those UTF-8 bytes as ANSI before encoding them again as UTF-8. | Match that exact export at the queued decoder and use UTF-8 for both its size query and conversion. |

The first correction alone left the phone receiving question marks. Correcting
the second boundary without the third changed `中` into text resembling `ä¸­`.
That changed symptom was evidence of another conversion, not a successful fix.

The queued decoder also ran on a **different thread** from the reader. A
thread-local marker therefore failed even after the correct callback was
identified. Live metadata recorded export on thread 2472 and decode on thread
996. Those IDs are from this run, not configuration values.

## The working implementation

The existing host helper obtains fresh, same-user X11 clipboard text and
publishes it directly through the Wine clipboard companion. It excludes
bridge-owned input helpers, ignores the startup clipboard and does not inject
a paste shortcut. The established incoming clipboard and dictation routes
remain separate.

`uu-clipboard-unicode.dll` attaches to `GameViewer.exe` when outbound host
clipboard forwarding is enabled. It checks the reviewed PE metadata and
instruction signatures before replacing three import-table pointers:

- `GetClipboardData`: only the identified mobile `CF_TEXT` export receives a
  UTF-8 snapshot made from `CF_UNICODETEXT`. Other consumers keep normal behavior.
- `CloseClipboard`: releases that thread's temporary snapshot handle.
- `MultiByteToWideChar`: only the identified queued callback, with bytes that
  exactly match a recorded export, switches from ANSI to UTF-8.

A process-wide table connects the read and conversion without assuming thread
identity or callback order. It holds at most 16 exports of at most 60 KiB each.
The size query leaves the matching entry available; successful output conversion
consumes it, zeroes its contents and frees it. Entries older than 30 seconds are
discarded when another copy arrives. A full table falls back to the original
reader behavior and emits bounded metadata instead of growing indefinitely.
Clipboard text is held only in memory and is never written to logs or disk.

This guard does not change Wine's global ANSI code page, keyboard layouts,
the clipboard's original formats or the vendor executable on disk. It does
not enable a second VNC clipboard channel. Those broader changes could affect
unrelated applications or bring back the clipboard/dictation feedback loop.

## Install and retain the correction

Use the normal bridge installer to build and install the compatibility tools
while preserving the deployment's existing relay and input options. A source
pull alone does not refresh installed helpers. The outbound feature remains
opt-in through the existing user-service override:

```ini
# ~/.config/systemd/user/uu-remote-bridge.service.d/30-host-clipboard.conf
[Service]
Environment=UURB_HOST_CLIPBOARD=on
```

The launcher loads the guard during account bootstrap, including normal
bridge startup after reboot. Its path lookup and attachment attempts are
bounded; a failed attachment leaves remote access available and verification
reports missing support. There is no new periodic injection service.

The live repair was applied without restarting UU or the desktop. That was a
controlled maintenance operation, not a general recommendation to stack live
patches. For a routine restart after installation, first retain independent
SSH, RDP or VNC access, then restart **only** `uu-remote-bridge.service` during
a suitable reconnect window. A desktop logout, reboot or Wine-prefix reset is
not required. Reboot persistence is wired into startup; a reboot was not part
of this validation.

## Verify the actual phone result

From the bridge repository:

```bash
./scripts/verify.sh --quick
systemctl --user is-active uu-remote-bridge.service
```

The verifier checks that the guard is mapped in the live GUI process with a
fresh initialization receipt. The guard's bounded log is
`uu-clipboard-guard.log` under the Wine user's `AppData/Local/Temp` directory.
For a new copy, expect both stages, for example:

```text
mobile-clipboard result=ready ... mode=queued-bytes
mobile-clipboard result=exported encoding=utf8 thread=2472
mobile-clipboard result=decoded encoding=utf8 thread=996
```

Thread IDs will vary. A running service, a loaded DLL or an `exported` line
alone does not prove that the decoder correction ran. The live repair produced
two export/decode pairs, followed by confirmation from the phone.

Freshly copy and paste this from Ubuntu to the real mobile client:

```text
中文测试 日本語 😀 “引号”
第二行 123 ' @
```

Then make a different copy. Verify mobile-to-Ubuntu paste and dictation too;
do not infer their behavior from the outgoing test. Multiline transfer and
overlapping queued copies were covered by automated tests; the recorded phone
confirmation covered the supplied Unicode phrase.

## Regression coverage and upgrade boundary

```bash
UURB_TEST_WINE=1 python3 -m unittest discover \
  -s tests -p test_clipboard_guard.py -v
```

The native test reads the Win32 clipboard on real worker threads, closes it,
queues a second copy and decodes both on another thread in reverse order.
It checks exact Unicode, both decoder calls, nonmatching ANSI data, invalid
UTF-16, size limits, capacity, expiry and allocation lifetime. Controlled
stack frames test the call-site predicate; a real client is still required
to qualify the installed proprietary build. The full local suite completed
264 tests with six optional skips, and GitHub CI passed. Existing inbound
Unicode/multiline integration tests also passed.

The guard currently recognizes **4.44.1.3978 only**. Unknown executable builds
are left unmodified and reported as unreviewed. Before promoting a new UU
version, review its export and decoder paths, update signature checks if
needed, run the regression tests and repeat the real phone test. Do not
reuse offsets based only on a similar version number.

Implementation and acceptance history:

- [Host-to-Win32 publication, PR #30](https://github.com/lachlanchen/uu-remote-ubuntu-bridge/pull/30)
- [Queued mobile export correction, PR #31](https://github.com/lachlanchen/uu-remote-ubuntu-bridge/pull/31)
- [Guard source](../src/uu_clipboard_guard.c)
- [Cross-thread native probe](../tests/probes/uu_clipboard_guard_probe.c)
- [Semantic input and clipboard routes](semantic-text-and-clipboard.md)

To return to inbound-only clipboard behavior, remove only the host-clipboard
opt-in override, reload user systemd and restart the UU bridge in a reconnect
window. Preserve the Wine prefix, login state, shared desktop and independent
remote access. Do not unload a DLL while import-table pointers still refer to
it; a normal process restart clears those mappings safely.
