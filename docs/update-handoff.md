# Update Handoff

Use this note when transferring `v0.1.0` to another authorized Ubuntu operator.
It separates the message to send from the maintainer and recipient checklists.

## Copy-ready update message

```text
UU Remote Ubuntu Bridge v0.1.0 is available.

This update fixes the normal mobile keyboard producing repeated letters (often
"d") and turning numbers into periods. It also includes unattended-startup and
relay-recovery hardening. The update is for x86-64 Ubuntu 24.04, GNOME 46, and
UU Remote 4.33.0.8907 only.

The private repository must be accessible from your GitHub account. Expect a
brief UU disconnect while the service is rebuilt and restarted. Existing UU
login state, bridge credentials, resolution, port, and unattended settings are
preserved.

Update commands:

  cd ~/Projects/uu-remote-ubuntu-bridge
  git status --short
  git fetch --tags origin
  git checkout v0.1.0
  ./install.sh --skip-packages --skip-account-login
  ./scripts/verify.sh --quick

Stop before checkout if git status reports local changes. After the service is
online, reconnect the phone and type: abcXYZ123,.!?
```

## Maintainer checklist

- Confirm the recipient is authorized to administer the target computer and UU
  account.
- Grant the recipient read access to the private
  `lachlanchen/uu-remote-ubuntu-bridge` repository.
- Confirm the target is Ubuntu 24.04 x86-64 with GNOME 46 and UU
  `4.33.0.8907`.
- Ask whether the installation is a direct clone or the parent repository's
  `code/uu-remote-ubuntu-bridge` submodule.
- Warn that the updater restarts the bridge and briefly disconnects UU.
- Do not request passwords, Wine-prefix archives, or unredacted UU logs.

## Recipient preflight

Authenticate GitHub access and verify a clean checkout:

```bash
gh auth status
cd ~/Projects/uu-remote-ubuntu-bridge
git status --short
git remote -v
```

For a missing direct clone:

```bash
mkdir -p ~/Projects
gh repo clone lachlanchen/uu-remote-ubuntu-bridge \
  ~/Projects/uu-remote-ubuntu-bridge
cd ~/Projects/uu-remote-ubuntu-bridge
git fetch --tags origin
git checkout v0.1.0
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

## Rollback and acceptance record

Rollback commands are in the [v0.1.0 release notes](releases/v0.1.0.md#rollback).
Record the target hostname locally, operator, completion time, installed tag,
quick-verifier result, phone acceptance result, and whether unattended status
was checked. Do not commit that machine-specific record to this repository.
