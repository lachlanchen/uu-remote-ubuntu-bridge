# Mobile Keyboard Parity Handoff

Use this note when UU's normal phone keyboard works correctly on one Ubuntu
bridge host but not another. It records the known-good `OptiPlex-7090`
reference, separates the two UU keyboard paths, and provides a privacy-safe
comparison and acceptance procedure.

This is for computers and UU accounts that the operator is authorized to
administer. Never use a password field for keyboard testing.

## Known-good reference

This snapshot was captured on 2026-07-17 in `Asia/Shanghai`. Smooth keyboard
behavior is a user-observed end-to-end result. The content-free bridge logs
independently confirm that phone text reached the Unicode normalization path
without an error.

| Field | OptiPlex-7090 reference |
| --- | --- |
| Host OS | Ubuntu 24.04.2 LTS, x86-64 |
| Desktop | GNOME Shell 46.0, live Wayland session on `:0` |
| Locale and layout | `en_US.UTF-8`, X11 layout `us`, model `pc105` |
| Wine | Wine 11.0 |
| Upstream UU host | UU Remote `4.33.0.8907`, approved release manifest |
| Installed bridge | `v0.1.0`, commit `f86c825` |
| Relay | GNOME RDP on port `3390`, `1920x1080` |
| Private display | Saved as `auto`; the observed service run selected `:20` |
| Service | `uu-remote-bridge.service` enabled and active |
| Reboot path | GDM autologin, TPM credential, and keyring unlock enabled |
| Keyboard pacing | No explicit `UURB_TEXT_KEY_DELAY_MS`; this is the `v0.1.0` behavior |

At capture time the append-only, content-free logs contained:

- 153 successful `text=normalized` broker calls
- zero normalized-text calls with a nonzero error
- 1,878 successful `route=broker result=1 error=0` bridge calls
- a successful normalized batch with `count=14`, `result=14`, and `error=0`

These counts are historical totals, not performance measurements. They prove
that both the phone-text and ordinary broker paths have worked, but the manual
acceptance test remains the authority for visible output and responsiveness.

The controller phone model, phone OS, mobile UU version, mobile keyboard/IME,
and UU network route were not captured with the original success report. Record
them on both sides before attributing a remaining difference to Ubuntu.

### Source and deployed runtime are different concepts

The installed launcher and CLI matched the `v0.1.0` checkout byte for byte. The
repository's `main` branch had advanced to `54a7d4c` before this note was added,
but those later sources were not deployed on the known-good host. A `git pull`
does not update `~/.local/bin`, compatibility DLLs, the broker, or the relay.

Always record both values:

```bash
git describe --tags --always --dirty
git rev-parse HEAD
sha256sum scripts/uu-remote-bridge ~/.local/bin/uu-remote-bridge
sha256sum scripts/uu-remote ~/.local/bin/uu-remote
```

Run `scripts/verify.sh` from the same revision used by `install.sh`. The
`build/compat` directory is generated and untracked. On `v0.1.0`, deleting or
rebuilding that directory separately can make the health-stub comparison fail
even though the active input path still works. Reinstalling from the selected
revision rebuilds, deploys, and immediately verifies one consistent runtime.
Do not dismiss any other verifier failure.

## Why the two keyboards behave differently

UU's phone client exposes two independent input paths:

1. The UU computer-keyboard panel emits ordinary Windows physical key events.
2. The phone's normal keyboard or IME submits text batches marked
   `KEYEVENTF_UNICODE`.

The first path passes through the normal `SendInput` fallback. The second path
cannot be sent directly to SDL FreeRDP because Wine's synthetic Unicode events
are interpreted as physical scancodes. The characteristic failure is every
letter becoming one repeated key, often `d`, while numbers become punctuation,
often a period.

`uu-input-bridge.dll` sends Unicode batches to `uu-input-broker.exe`. The broker
maps each character through the active Wine keyboard layout with `VkKeyScanW`,
emits ordinary virtual-key chords, focuses the `Ubuntu-Desktop-Relay` window,
and returns success only when the complete input request was accepted. It does
not log key codes, characters, clipboard content, or typed text.

A Windows UU host followed by RDP can appear unaffected because native Windows
converts the phone's Unicode input before RDP sees it. That result does not
prove the direct Wine bridge has the same broker or deployed revision.

## Supported release first

For the repeated-letter or number-to-period symptom, first put the other host
on the supported `v0.1.0` release. This preserves the existing UU account state,
relay credential, port, resolution, and unattended setting:

```bash
cd ~/Projects/uu-remote-ubuntu-bridge
git status --short
git fetch --tags origin
git checkout v0.1.0
./install.sh --skip-packages --skip-account-login
./scripts/verify.sh --quick
```

Stop if `git status --short` prints local changes. Installation intentionally
restarts the bridge and briefly disconnects UU. For a first installation, run
`./install.sh` without the skip options and complete the official UU sign-in.

`v0.2.0` includes an 8 ms per-character pacing option, foreground
focus confirmation, installed-runtime digest checks, privacy-safe transport
diagnostics, and an isolated libei keymap-descriptor fix. It also retains the
proven original-call-then-broker fallback restored at commit `54a7d4c`. The
union release preserves an upgraded `v0.1.0` environment's missing text-delay
field as `0`; fresh installations use 8 ms. Do not describe a moving `main`
checkout as either release; pin and record an exact tag.

The known-good 7090 did not have the 8 ms option deployed, so pacing is not a
proven explanation for the difference between the two computers.

## Collect a parity snapshot

Run these commands locally on both hosts. Keep their output in the handoff
ticket or local operator record, not in the public repository.

### Host and layout

```bash
date -Is
hostnamectl --static
uname -m
lsb_release -ds
gnome-shell --version
wine --version
localectl status
setxkbmap -query
```

The native phone text mapper follows Wine's active layout. First compare with a
US English layout and the established ASCII acceptance string. A non-English
character that `VkKeyScanW` cannot represent fails explicitly rather than
becoming an unrelated key.

### Checkout and installed runtime

```bash
cd ~/Projects/uu-remote-ubuntu-bridge
git status --short
git describe --tags --always --dirty
git rev-parse HEAD
git remote get-url origin
sha256sum scripts/uu-remote-bridge ~/.local/bin/uu-remote-bridge
sha256sum scripts/uu-remote ~/.local/bin/uu-remote
./scripts/verify.sh --quick
```

On post-release source, the verifier explicitly reports whether the installed
runtime digest matches the checkout. On `v0.1.0`, matching launcher and CLI
hashes plus a verifier run immediately after installation provide the equivalent
deployment check.

### Safe relay settings and service state

```bash
sed -n -E \
  '/^UURB_(RDP_PORT|RESOLUTION|DISPLAY|GRD_FD_RESTART_THRESHOLD|TEXT_KEY_DELAY_MS|PHYSICAL_KEY_DELAY_MS|NETWORK_INTERFACE)=/p' \
  ~/.config/uu-remote-bridge/environment
systemctl --user is-enabled uu-remote-bridge.service
systemctl --user is-active uu-remote-bridge.service
uu-remote status
./scripts/configure-unattended.sh status
```

The descriptor, text-delay, and network-interface keys do not exist in the
original `v0.1.0` release. Their absence is expected on the 7090 reference.
Use `uu-remote status`; do not run `scripts/uu-remote-bridge` directly because
that file is the systemd daemon, not the operator CLI.

### Content-free input evidence

After one normal-phone-keyboard test, inspect only bounded metadata:

```bash
broker="$HOME/.local/share/wineprefixes/uu-remote/drive_c/users/$USER/Temp/uu-input-broker.log"
bridge="$HOME/.local/share/wineprefixes/uu-remote/drive_c/users/$USER/AppData/Local/Temp/uu-input-bridge.log"
rg 'text=normalized .*error=0' "$broker" | tail -n 10
rg 'route=broker .*error=0' "$bridge" | tail -n 10
```

A working normal-phone-keyboard commit has `text=normalized`, a result equal to
the original count, and `error=0`. Post-release text logs also show
`focus=ready`, `paced-text=N`, and `text-delay-ms=N`; physical-key logs use
`category=keyboard`, `paced-physical=N`, and `physical-delay-ms=N`. Do not
require those newer fields from `v0.1.0`.

The bridge-owned logs above are designed to omit content. Do not substitute
raw NetEase logs, a Wine-prefix archive, or a process dump in a community issue.

### Transport and long-session evidence

If direct RDP is responsive but UU drops or delays individual keys, the local
RDP input path is probably healthy and the UU transport must be compared.
Post-release installations provide:

```bash
uu-remote network
```

This command reports aggregate P2P/relay delay and key-watchdog metadata without
addresses, account data, device IDs, or typed text. Do not add host-side key
retries to hide a slow route because the late original event can create a
duplicate.

If input starts correctly and degrades only after a long session, capture GNOME
RDP descriptor metadata:

```bash
rdp_port="$(sed -n 's/^UURB_RDP_PORT=//p' \
  ~/.config/uu-remote-bridge/environment)"
pid="$(pgrep -o -f "gnome-remote-desktop-daemon --rdp-port ${rdp_port:-3390}")"
find "/proc/$pid/fd" -maxdepth 1 -type l | wc -l
sed -n '/Max open files/p' "/proc/$pid/limits"
```

Rapid descriptor growth points to Ubuntu 24.04's libei 1.2.1 keymap-FD leak,
not the phone's Unicode mapping. The post-release bridge-local libei backport
and descriptor guard address that separate long-session failure.

## End-to-end acceptance matrix

Use an ordinary scratch text field, never a terminal containing a pending
privileged command and never a password field.

| Test | Expected result | What it isolates |
| --- | --- | --- |
| Video | Live GNOME desktop updates | UU capture and local RDP video |
| Mouse | Move, click, scroll, and focus | Ordinary broker input |
| UU computer-keyboard panel | Physical letters, numbers, Shift, Backspace | Physical-key path |
| Normal phone keyboard | `abcXYZ123,.!?` appears exactly once | Unicode normalization path |
| Direct RDP | Same scratch field is responsive | GNOME RDP and libei without UU transport |
| Reconnect | Repeat normal phone string after reconnect | Account bootstrap and hook continuity |

Do not accept a test performed only with UU's computer-keyboard panel. That
panel can pass while the phone's native IME path is still broken.

Record the visible result as a short description, not by pasting private text
or credentials into a log. Also record phone OS, mobile UU version, keyboard
app/IME and language, network type, and whether UU reports P2P or relay mode.

## Symptom decision table

| Symptom | Most likely boundary | Next action |
| --- | --- | --- |
| Every phone letter becomes `d`; numbers become `.` | Old or undeployed Unicode normalizer | Install `v0.1.0`, reconnect, require `text=normalized ... error=0` |
| Computer-keyboard panel works; normal phone keyboard does not | Native IME path only | Compare installed broker revision and Wine layout |
| Text is correct but keys lag or disappear | UU transport, focus, or text pacing | Compare direct RDP, controller route, and post-release metadata |
| Multi-homed host binds a nonpreferred adapter | UU selected Wine's first adapter instead of Ubuntu's route | Test the post-release `--network-interface default` mode |
| Mouse and both keyboard modes fail | Injection hook, broker, or relay focus | Run the quick verifier and inspect bounded bridge metadata |
| Input works after restart, then degrades over hours | GNOME RDP/libei descriptor exhaustion | Inspect FD count and use the reviewed post-release backport |
| ASCII works but a language-specific character fails | Character unavailable in active Wine layout | Match the intended layout or use the physical-key/clipboard path |
| Windows UU to RDP works; direct Ubuntu UU does not | Windows pre-converts Unicode before RDP | Verify the Ubuntu broker rather than changing GNOME RDP |
| Video is black as well as input failing | Capture or local RDP startup | Follow the separate black-video checks in troubleshooting |

See [Troubleshooting](troubleshooting.md) for the command-level repair paths.

## Copy-ready handoff message

```text
The OptiPlex-7090 reference has smooth UU keyboard input with Ubuntu 24.04.2,
GNOME 46, Wine 11, US layout, UU host 4.33.0.8907, and bridge v0.1.0. Its normal
phone-keyboard input reached the Unicode normalizer successfully; this is a
different path from UU's computer-keyboard panel.

On the other authorized Ubuntu host, please install and verify the same release:

  cd ~/Projects/uu-remote-ubuntu-bridge
  git status --short
  git fetch --tags origin
  git checkout v0.1.0
  ./install.sh --skip-packages --skip-account-login
  ./scripts/verify.sh --quick

The installer briefly restarts UU but preserves account and relay settings.
Stop if git status reports local changes.

After reconnecting, focus a scratch text field and type abcXYZ123,.!? with the
phone's normal keyboard, not UU's computer-keyboard panel. Report whether video,
mouse, the panel keyboard, normal phone keyboard, and direct RDP each work.
Also report the host OS/GNOME/Wine/layout, phone OS, mobile UU version, keyboard
app and language, network type, P2P/relay mode, exact git revision, quick
verifier result, and only the bounded text=normalized/error metadata.

Do not send passwords, account or device IDs, a Wine prefix, private desktop
content, raw NetEase logs, or text typed outside the deliberate acceptance test.
```

## Handoff record template

Keep this machine-specific record private:

```text
Operator:
Test time and timezone:
Target hostname:
Host OS / architecture:
GNOME / session type:
Wine version:
Locale / XKB layout:
UU host version:
Bridge git describe / commit:
Installed runtime matches checkout: yes / no
Relay resolution / port / display mode:
Phone model / OS:
Mobile UU version:
Keyboard app / IME / language:
Network type and P2P / relay mode:
Video: pass / fail
Mouse: pass / fail
UU computer-keyboard panel: pass / fail
Normal phone keyboard abcXYZ123,.!?: pass / fail
Direct RDP comparison: pass / fail / not tested
Reconnect test: pass / fail
Normalized metadata observed: yes / no
Quick verifier: pass / fail, failing check names only
Notes:
```

Do not commit a completed record because host and controller details can become
identifying metadata.
