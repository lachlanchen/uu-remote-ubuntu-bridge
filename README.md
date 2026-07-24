<div align="center">

[English](README.md) · [العربية](i18n/README.ar.md) · [Español](i18n/README.es.md) · [Français](i18n/README.fr.md) · [日本語](i18n/README.ja.md) · [한국어](i18n/README.ko.md) · [Tiếng Việt](i18n/README.vi.md) · [中文 (简体)](i18n/README.zh-Hans.md) · [中文（繁體）](i18n/README.zh-Hant.md) · [Deutsch](i18n/README.de.md) · [Русский](i18n/README.ru.md)

[![LazyingArt banner](https://github.com/lachlanchen/lachlanchen/raw/main/figs/banner.png)](https://lazying.art)

# UU Remote Ubuntu Bridge

**Use NetEase UU Remote to view and fully control the Ubuntu GNOME desktop.**

[![Ubuntu 24.04](https://img.shields.io/badge/Ubuntu-24.04-E95420?logo=ubuntu&logoColor=white)](https://ubuntu.com/)
[![GNOME 46](https://img.shields.io/badge/GNOME-46-4A86CF?logo=gnome&logoColor=white)](https://www.gnome.org/)
[![UU Remote](https://img.shields.io/badge/UU_Remote-4.33.0.8907-00A870)](https://uuyc.163.com/)
[![Wine 11](https://img.shields.io/badge/Wine-11.0-800000?logo=wine&logoColor=white)](https://www.winehq.org/)
[![Patch policy](https://img.shields.io/badge/Patches-fail--closed-1F883D)](docs/security.md)
[![License MIT](https://img.shields.io/badge/License-MIT-2F81F7)](LICENSE)
[![Website](https://img.shields.io/badge/Website-lazying.art-0A7EA4)](https://lazying.art)

</div>

An experimental compatibility bridge that runs the official Windows UU client
in an isolated Wine prefix, presents the real GNOME desktop through a
local RDP relay, and makes mouse and keyboard control work normally.

| Capability | Validated result |
| --- | --- |
| Desktop video | Live GNOME session at `1920x1080` |
| Mouse | Motion, buttons, wheel, focus, and clicks through UU |
| Keyboard | Physical keys, shortcuts, and normalized phone IME text |
| Recovery | User systemd restart, boot autostart, and DLL re-injection |
| Stability | One UU server PID beyond the former four-minute failure window |
| Authentication | Normal UU sign-in and separate GNOME RDP credential |

> This is not a native UU Linux port and is not affiliated with NetEase. The
> current manifest is intentionally locked to UU Remote `4.33.0.8907`.

The supported host is x86-64 Ubuntu 24.04 with a logged-in GNOME 46 desktop
(physical, Wayland, Xorg, or XRDP). The installer checks this boundary and
fails before making partial changes on an unsupported OS or architecture.

## Releases and behavior tracks

| Tag | Purpose | Default input behavior |
| --- | --- | --- |
| `v0.1.0` | Immutable known-good baseline from the original working host | Original unpaced phone text and physical-key path |
| `v0.2.0` | Union release with the baseline fallback plus optional host-specific extensions | New installs pace phone text by 8 ms; physical pacing is off, the compatible RDP keyboard route remains selected, and all network adapters remain visible |

The `v0.1.0` tag is never moved or rewritten. Upgrading an existing `v0.1.0`
installation preserves its missing text-delay field as `0`, so merely
installing `v0.2.0` does not change the timing of that known-good host. A new
installation starts at 8 ms. In both cases, an explicit saved or command-line
setting takes precedence.

Use descriptive parallel tags when recording the input path validated on a
specific machine:

| Behavior tag | Use when |
| --- | --- |
| `track-rdp-broker-20260724` | The compatible Wine broker and RDP keyboard route are already smooth |
| `track-direct-x11-20260724` | An X11/XRDP host needs the authenticated direct keyboard route |

These aliases do not rank one path above the other and the updater never
switches between them automatically. Read the [behavior-track handoff](docs/release-tracks.md).

## Quick start

Run from the logged-in Ubuntu GNOME desktop session:

```bash
./install.sh
```

The one installer:

1. installs Ubuntu, WineHQ, build, X11, RDP, and keyring dependencies
2. downloads and verifies the approved UU installer when needed
3. builds all original compatibility DLLs and helpers
4. builds the pinned Windows WinPR runtime used by SDL FreeRDP
5. backs up and applies only approved binary signatures
6. configures GNOME Remote Desktop with a pinned TLS certificate
7. stores the relay password in GNOME Keyring, never in a script
8. installs and starts the supervised user service
9. runs immediate end-to-end verification

The first run prompts for a local relay password without echo and opens the
official UU window on the logged-in desktop before starting the private relay.
Complete account sign-in and close that window. Re-running the same command is
idempotent; unchanged FreeRDP build outputs are checksum-verified and reused.

Port, resolution, private-display, phone-text pacing, optional physical-key
pacing, physical-key route, and an optional UU-only network-interface choice
are persistent and can be set without editing the service:

```bash
./install.sh --rdp-port 3391 --resolution 2560x1440 --display auto \
  --text-key-delay-ms 8 --physical-key-delay-ms 0 \
  --keyboard-route rdp \
  --network-interface all
```

They are validated and stored in
`~/.config/uu-remote-bridge/environment`. `auto` safely chooses the first free
private X display from `:20` through `:99`, avoiding existing VNC/Xvfb
sessions. A later plain `./install.sh` preserves these choices.
Requested ports and fixed displays are checked before use. A conflicting
non-GNOME listener fails closed, and an installer error restarts a bridge that
was active before the attempted upgrade.

On the compatible `rdp` route, the default 8 ms text-key delay prevents UU's
phone keyboard from overwhelming the Wine-to-FreeRDP input boundary. An
upgrade from `v0.1.0` preserves that release's unpaced behavior as `0`. The
broker confirms that the relay window has focus before acknowledging an input
request and sends translated text one character chord at a time. Values from 0
through 50 ms are accepted; change the delay only when a controlled test
supports it. The opt-in `x11` route bypasses this RDP pacing boundary after it
has normalized the complete representable phone-text request.

Physical-key pacing defaults to `0`, preserving the ordinary path on hosts
that already work. If slow typing succeeds but fast physical-key input omits
events, `--physical-key-delay-ms 8` adds bounded back-pressure after each
accepted broker segment. It never retries or synthesizes a key. See the
[validated recovery note](docs/xrdp-and-keyboard-recovery.md) before changing
this host-specific setting.

If broker metadata shows accepted physical-key or normalized phone-text calls
but the nested Wine/FreeRDP route still loses fast keys on an Xorg or XRDP
desktop, the opt-in direct route removes only that final keyboard hop:

```bash
./install.sh --skip-packages --skip-account-login \
  --keyboard-route x11 --physical-key-delay-ms 0
```

Mouse, video, and clipboard continue through the proven RDP relay. Physical
keys and layout-representable phone text go through an authenticated loopback
helper and XTEST into the selected X11 desktop. Phone text is still normalized
into ordinary virtual-key chords before that boundary; unsupported Unicode
fails explicitly rather than becoming an unrelated key. The global default
remains `rdp`; `auto` selects the direct route only for an X11 target. If
preflight cannot verify the target display or helper before injection, the
request safely uses the compatible RDP route. No event is replayed after an
ambiguous partial injection.

On the validated XRDP workstation, the first live direct-UU run produced 256
content-free sampled physical-key calls on `route=x11`; every sampled call
returned its requested single event with `error=0`. The operator reported that
typing became very smooth and that almost all prior omissions were resolved.
This is strong practical acceptance, while deliberately not claiming that an
upstream controller can never omit an event under every network condition.
Post-`v0.2.0` source also includes an isolated phone-text acceptance test. A
fixed 26-letter Unicode batch crossed the Wine broker on `route=x11-text` and
arrived as all 52 ordered X11 press/release transitions. Run it without
touching the live desktop:

```bash
./scripts/test-x11-phone-text.sh
```

After live deployment, the operator confirmed that normal phone-keyboard
typing was fixed. The first 72 bounded phone-text calls all used
`route=x11-text`, returned their complete requested counts with `error=0`, and
completed in 0-2 ms. The logs contained no character values or typed content.

If individual keys lag or disappear while direct RDP remains responsive, check
the transport before changing input code:

```bash
uu-remote network
```

The report shows only aggregate path, delay, P2P, and key-watchdog metadata. It
never prints addresses, device IDs, account data, or typed text. It includes
the completion time and labels reports older than five minutes as stale, so an
old session is not mistaken for the current idle bridge. It also reports only
whether controller and host relay geography matched, without printing either
location. A forced relay near UU's key-watchdog threshold is an upstream
network problem; host-side retries can duplicate keys that arrive late.

On a host with several active adapters, UU under Wine can choose the first
enumerated adapter even when Ubuntu routes through a different, faster one.
If `uu-remote network` and a direct-RDP comparison point to that condition,
select Ubuntu's preferred default route at each bridge start:

```bash
./install.sh --skip-packages --skip-account-login \
  --network-interface default
```

This loads a fail-open adapter view only into UU's Wine service tree. It does
not edit routes, NetworkManager, firewall rules, Docker, or system libraries.
The repository and installer default remains `all`, preserving existing hosts.
While `default` is active, the existing bridge supervisor checks the preferred
interface every ten seconds. If it changes, the whole relay is rebuilt once on
the new route; no additional watcher or service is installed. Use
`--network-interface all` to remove the restriction.

Ubuntu 24.04's libei 1.2.1 leaks the received keyboard-keymap descriptor after
duplicating it. The installer builds the exact upstream one-line fix from a
hash-verified 1.2.1 archive and loads that library only into this bridge's
GNOME RDP child. A raised child limit and persistent 4096-descriptor relay
guard remain as defense in depth:

```bash
./install.sh --skip-packages --skip-account-login \
  --grd-fd-restart-threshold 4096
```

Set the threshold to `0` only when deliberately disabling that guard.

### Update an existing installation

Use the latest supported tag without deleting UU account state or changing the
saved relay settings:

```bash
cd ~/Projects/uu-remote-ubuntu-bridge
git status --short
git fetch --tags origin
git switch --detach v0.2.0
./install.sh --skip-packages --skip-account-login
./scripts/verify.sh --quick
```

Stop if the status command reports local changes. Installation briefly restarts
the relay. Read the [v0.2.0 release notes](docs/releases/v0.2.0.md), use the
[public GitHub release](https://github.com/lachlanchen/uu-remote-ubuntu-bridge/releases/tag/v0.2.0),
and send the [copy-ready operator handoff](docs/update-handoff.md) when updating
another authorized machine.

Use an already downloaded installer or a future approved release manifest:

```bash
./install.sh \
  --uu-installer ~/Downloads/UU-Remote/uuyc_4.33.0.exe \
  --release-manifest patches/uu-remote-4.33.0.8907.json
```

### Unattended reboot startup

To make UU available after reboot without first logging in locally or through
RDP, enable the opt-in TPM-backed boot path:

```bash
./install.sh --unattended
```

For an existing installation, run
`./scripts/configure-unattended.sh enable`. This enables GDM automatic login,
so anyone with physical access can use the desktop after boot. The keyring
password remains encrypted against this machine's TPM and is never stored in
a script or process argument.

[Read setup, verification, password-change, and rollback
details](docs/unattended-startup.md).

### Daily update checks and repair resume

Opt into zero-downtime daily release checks, relay health monitoring, and a
reboot-resumable Codex repair workspace:

```bash
./scripts/configure-updater.sh enable \
  --track track-rdp-broker-20260724 \
  --model gpt-5.6-sol --reasoning-effort xhigh
```

Use `track-direct-x11-20260724` only on a host already validated with the direct X11
route. Checks never restart a healthy relay. Unknown installers are downloaded
and statically staged outside the Wine prefix; Codex can prepare a reviewable
repair but cannot approve or deploy its own binary patch. Interrupted work
persists its thread ID and resumes after reboot with bounded backoff.
Before an automatic Codex run, the updater verifies that included usage is at
most 20%. It fails closed when usage is unavailable and never considers or
consumes purchased credits.

[Read the complete automatic-maintenance and handoff procedure](docs/automatic-updates.md).

## Architecture

```text
Phone / Windows / macOS UU controller
                  |
                  | UU signaling, video, and input
                  v
       GameViewerServer.exe in Wine
             |                 |
       captures window    SendInput IAT hook
             |                 |
             v                 v
   Ubuntu-Desktop-Relay   bounded named-pipe broker
       SDL FreeRDP          |             |
             |              | RDP         | optional physical keys
             |              |             | + normalized phone text
             +--------------+             v
                    |             native X11/XTEST helper
             RDP on 127.0.0.1              |
                    |                      |
                    v                      |
         GNOME Remote Desktop              |
                    |                      |
                    +----------+-----------+
                               v
                    logged-in GNOME desktop
                     (Wayland or Xorg/XRDP)
```

UU sees one ordinary Windows desktop window. SDL FreeRDP relays that window to
GNOME Remote Desktop, which owns supported GNOME capture and input. The
launcher discovers the D-Bus of the live GNOME Shell, including XRDP sessions
that use a private session bus, and keeps the RDP hop local to the host. When
Wine denies `SendInput` from UU's service token, so a bounded broker repeats
the same input request from a normal user Wine process. On an explicitly
selected X11 target, physical keys and normalized, layout-representable phone
text can instead bypass the nested RDP input conversion; video, mouse,
clipboard, and all non-keyboard channels keep the original relay.

[Read the complete architecture](docs/architecture.md).
The [debugging journey](docs/debugging-journey.md) records the failed
hypotheses, decisive evidence, Unicode keyboard correction, deployment-drift
check, descriptor protection, and unattended boot dependency chain.

## Daily commands

```bash
uu-remote status
uu-remote restart
uu-remote stop
uu-remote logs
uu-remote login       # one-time sign-in or account recovery on this desktop
scripts/verify.sh --quick
scripts/verify.sh
```

The full verifier waits 270 seconds and proves the same server PID crosses
UU's former four-minute failure interval. It also confirms that the installed
runtime was built from the current checkout and that GNOME RDP remains below
its guarded descriptor threshold.

## Updating for a new UU release

Unknown binaries are never patched automatically. The maintenance toolkit
turns an update into a reproducible review:

```bash
# Stage the installer without touching the live Wine prefix.
scripts/stage-uu-release.sh \
  --installer ~/Downloads/UU-Remote/uuyc_NEW.exe \
  --sandbox-install

# Produce PE maps, semantic landmarks, candidate signatures,
# targeted disassembly, and a deliberately non-runnable draft manifest.
scripts/audit-gameviewer.py inspect \
  --server build/upstream/NEW/GameViewerServer.exe \
  --healthd build/upstream/NEW/GameViewerHealthd.exe \
  --installer ~/Downloads/UU-Remote/uuyc_NEW.exe \
  --baseline patches/uu-remote-4.33.0.8907.json \
  --version NEW_VERSION
```

After manual semantic review, `audit-gameviewer.py finalize` derives the full
patched hash and creates an approved manifest. The generic patch engine then
handles patch, verify, and byte-identical restore without source changes.

[Learn the complete upstream workflow](docs/upstream-maintenance.md).

## Binary safety model

The patch engine verifies:

- approved manifest status
- complete original SHA-256 and file size
- one long original signature at every exact file offset
- equal-length, non-overlapping replacements
- complete patched SHA-256
- matching audited backup before restore

An update with one changed byte outside the approved result fails closed. A
draft manifest cannot be used by the installer or patcher.

The bridge does not edit OS account databases, bypass a login, install a
kernel input driver, expose X11 over TCP, or add a new remote-control protocol.
The RDP hop targets loopback and pins GNOME's certificate fingerprint.

[Review all trust boundaries and residual risk](docs/security.md).

## Repository map

| Path | Purpose |
| --- | --- |
| `patches/` | Versioned approved UU identities and patch signatures |
| `CHANGELOG.md` | Tagged bridge release history and upgrade entry points |
| `src/` | Input hook, broker, injector, service helper, adapter filter, and SSPI shim |
| `scripts/gameviewer_patchlib.py` | Generic release-manifest engine |
| `scripts/patch-gameviewer.py` | Patch, verify, status, field, and restore CLI |
| `scripts/stage-uu-release.sh` | Private installer staging sandbox |
| `scripts/audit-gameviewer.py` | New-release evidence and approval workflow |
| `scripts/uu_update_manager.py` | Daily checks, health recovery, and resumable Codex repair state machine |
| `scripts/configure-updater.sh` | Install, select a behavior track, and remove maintenance timers |
| `scripts/uu-remote-bridge` | Supervised UU/Xvfb/FreeRDP orchestration |
| `scripts/uu_connection_status.py` | Privacy-safe transport and key-watchdog diagnosis |
| `scripts/configure-unattended.sh` | TPM-backed GDM autologin setup and rollback |
| `scripts/uu-keyring-unlock.py` | Secret Service unlock before GNOME RDP |
| `install.sh` / `uninstall.sh` | Idempotent setup and reversible removal |
| `tests/` | Proprietary-binary-free manifest unit tests |

No NetEase executable, FreeRDP artifact, Wine prefix, password, token, device
ID, raw production log, screenshot, or private desktop content is committed.

## Documentation

- [Architecture](docs/architecture.md)
- [Changelog](CHANGELOG.md)
- [v0.2.0 union release notes](docs/releases/v0.2.0.md)
- [v0.1.0 release notes](docs/releases/v0.1.0.md)
- [Update handoff for another operator](docs/update-handoff.md)
- [Input behavior tracks](docs/release-tracks.md)
- [Automatic checks and resumable repair](docs/automatic-updates.md)
- [Mobile-keyboard parity handoff](docs/mobile-keyboard-parity-handoff.md)
- [XRDP client stall and UU keyboard recovery](docs/xrdp-and-keyboard-recovery.md)
- [Unattended startup after reboot](docs/unattended-startup.md)
- [Methodology and tool inventory](docs/methodology-and-toolkit.md)
- [Reverse-engineering record with exact `xxd` and `objdump` evidence](docs/reverse-engineering.md)
- [Maintaining the bridge across upstream updates](docs/upstream-maintenance.md)
- [Windows reference comparison](docs/windows-reference.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Security](docs/security.md)
- [Contributing](CONTRIBUTING.md)

## Removal

Restore the audited upstream files and remove bridge components while keeping
the dedicated UU account state:

```bash
./uninstall.sh --dry-run
./uninstall.sh
```

The dry run verifies both rollback backups without changing the service or any
file. `./uninstall.sh --purge` also deletes the dedicated Wine prefix, bridge
credential, and GNOME RDP enablement.

## Support

Support continued maintenance, upstream release audits, and reusable
documentation through any of these channels:

| GitHub Sponsors | LazyingArt Donate | PayPal | Stripe |
| --- | --- | --- | --- |
| [![GitHub Sponsors](https://img.shields.io/badge/GitHub-Sponsor-EA4AAA?style=for-the-badge&logo=githubsponsors&logoColor=white)](https://github.com/sponsors/lachlanchen) | [![Donate](https://img.shields.io/badge/LazyingArt-Donate-0EA5E9?style=for-the-badge&logo=ko-fi&logoColor=white)](https://chat.lazying.art/donate) | [![PayPal](https://img.shields.io/badge/PayPal-Donate-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/RongzhouChen) | [![Stripe](https://img.shields.io/badge/Stripe-Donate-635BFF?style=for-the-badge&logo=stripe&logoColor=white)](https://buy.stripe.com/aFadR8gIaflgfQV6T4fw400) |

<details>
<summary>Alipay and WeChat Pay QR codes</summary>

<p align="center">
  <img src="https://raw.githubusercontent.com/lachlanchen/the-art-of-lazying/main/figs/donate_alipay.png" alt="Alipay donation QR code" width="220">
  &nbsp;&nbsp;&nbsp;
  <img src="https://raw.githubusercontent.com/lachlanchen/the-art-of-lazying/main/figs/donate_wechat.png" alt="WeChat Pay donation QR code" width="220">
</p>

</details>

## Project

Created as part of [The Art of Lazying](https://lazying.art): automate the
tedious parts, preserve the reasoning, and make the result reusable.

Original source is MIT licensed. UU Remote, Wine, FreeRDP, GNOME, OpenSSL, and
other third-party components retain their own licenses and trademarks.
