# Update Handoff

Use this note when transferring `v0.2.0` to another authorized Ubuntu operator.
It separates the message to send from the maintainer and recipient checklists.
For a keyboard that works on one host but not another, use the
[mobile-keyboard parity handoff](mobile-keyboard-parity-handoff.md) to capture
the known-good baseline, controller variables, and bounded comparison evidence.

## Copy-ready update message

```text
UU Remote Ubuntu Bridge v0.2.0 is available.

This backward-compatible union release keeps the v0.1.0 input fallback and adds
bounded pacing, privacy-safe diagnostics, and relay-recovery hardening. An
upgrade from v0.1.0 preserves that host's unpaced text behavior; physical-key
pacing and network filtering remain off unless explicitly selected. The update
also includes an opt-in direct X11 physical-key route; the compatible RDP route
remains the default. The update is for x86-64 Ubuntu 24.04, GNOME 46, and UU
Remote 4.33.0.8907 only.

The public repository is available at:
https://github.com/lachlanchen/uu-remote-ubuntu-bridge

Expect a brief UU disconnect while the service is rebuilt and restarted.
Existing UU login state, bridge credentials, resolution, port, and unattended
settings are preserved.

Update commands:

  cd ~/Projects/uu-remote-ubuntu-bridge
  git status --short
  git fetch --tags origin
  git switch --detach v0.2.0
  ./install.sh --skip-packages --skip-account-login
  ./scripts/verify.sh --quick

Stop before checkout if git status reports local changes. After the service is
online, reconnect the phone and type: abcXYZ123,.!?
```

## Maintainer checklist

- Confirm the recipient is authorized to administer the target computer and UU
  account.
- Share the official public `v0.2.0` release URL and verify the repository owner
  is `lachlanchen` before the recipient runs code.
- Confirm the target is Ubuntu 24.04 x86-64 with GNOME 46 and UU
  `4.33.0.8907`.
- Ask whether the installation is a direct clone or the parent repository's
  `code/uu-remote-ubuntu-bridge` submodule.
- Warn that the updater restarts the bridge and briefly disconnects UU.
- Do not request passwords, Wine-prefix archives, or unredacted UU logs.

## Recipient preflight

Verify the repository remote and a clean checkout:

```bash
cd ~/Projects/uu-remote-ubuntu-bridge
git status --short
git remote -v
```

For a missing direct clone:

```bash
mkdir -p ~/Projects
git clone https://github.com/lachlanchen/uu-remote-ubuntu-bridge.git \
  ~/Projects/uu-remote-ubuntu-bridge
cd ~/Projects/uu-remote-ubuntu-bridge
git fetch --tags origin
git switch --detach v0.2.0
```

Do not discard a dirty worktree. Record or review local changes before updating.

## Install and verify

For an existing authenticated UU installation:

```bash
./install.sh --skip-packages --skip-account-login
./scripts/verify.sh --quick
uu-remote status
```

For a first installation, use `./install.sh` without the two skip options and
complete the official UU account sign-in window.

If unattended startup was previously enabled, verify that it remains active:

```bash
./scripts/configure-unattended.sh status
systemctl --user status uu-keyring-unlock.service
```

## Mobile-keyboard acceptance

1. Reconnect UU from the phone after the service restart.
2. Focus an ordinary text field on Ubuntu.
3. Type `abcXYZ123,.!?` with the phone's normal keyboard.
4. Confirm the exact text appears; do not use UU's computer-keyboard panel for
   this acceptance test.
5. Check only the non-content diagnostic result:

```bash
log="$HOME/.local/share/wineprefixes/uu-remote/drive_c/users/$USER/Temp/uu-input-broker.log"
tail -80 "$log" | rg 'text=normalized .*error=0'
```

Do not accept a test performed only with UU's computer-keyboard panel. It uses
a different input path from the phone's normal keyboard.

## Optional physical-key acceptance on Xorg/XRDP

Do not enable this on a host whose default RDP route already works. If fast
computer-keyboard input remains incomplete despite successful broker records,
and the target session is confirmed X11:

```bash
./install.sh --skip-packages --skip-account-login \
  --keyboard-route x11 --physical-key-delay-ms 0
./scripts/verify.sh --quick
```

Reconnect UU, type the alphabet rapidly, press Enter, and test Ctrl+A/C/V.
Require both the visible result and a fresh content-free
`category=keyboard route=x11 ... result=1 error=0` record. Restore
`--keyboard-route rdp` if the target is Wayland or the helper cannot preflight
the display.

## Failure handoff

Collect these bounded diagnostics:

```bash
git describe --tags --always --dirty
./scripts/verify.sh --quick
systemctl --user --no-pager --full status uu-remote-bridge.service
tail -80 ~/.local/state/uu-remote-bridge/freerdp.log
```

Report the test time, whether video and the computer-keyboard panel work, and
the incorrect visible result. Do not send the Wine prefix or proprietary UU
logs without first removing account and device metadata.

When the same phone keyboard behaves differently across computers, use the
[detailed parity checklist](mobile-keyboard-parity-handoff.md#collect-a-parity-snapshot)
and its private handoff record instead of collecting unbounded logs.

## Rollback and acceptance record

Rollback commands are in the [v0.2.0 release notes](releases/v0.2.0.md#rollback).
Record the target hostname locally, operator, completion time, installed tag,
quick-verifier result, phone acceptance result, and whether unattended status
was checked. Do not commit that machine-specific record to this repository.
