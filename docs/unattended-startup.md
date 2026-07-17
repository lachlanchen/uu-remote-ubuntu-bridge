# Unattended Startup

UU normally starts with the logged-in GNOME session. GDM automatic login is
needed when the machine must become reachable through UU after a reboot with
no local or RDP login first. Automatic login introduces a second problem:
PAM receives no password, so GNOME Keyring remains locked and GNOME Remote
Desktop cannot read its relay credential.

This repository solves both parts explicitly. It does not remove the Unix
account password or store a plaintext password in a launcher.

## Enable

For a new installation, use the single installer:

```bash
./install.sh --unattended
```

For an existing bridge installation:

```bash
./scripts/configure-unattended.sh enable
```

The command asks for the GNOME login keyring password, which is normally the
Ubuntu login password. It then:

1. verifies that the host has TPM2 support
2. encrypts the keyring password with `systemd-creds --with-key=tpm2`
3. stores only the encrypted blob under `~/.config/uu-remote-bridge`
4. adds the desktop account to the `tss` group for TPM access after login
5. grants a temporary per-user TPM ACL until that group is active
6. enables `uu-keyring-unlock.service` before GNOME Remote Desktop
7. preserves the previous GDM values in a root-only rollback record
8. enables GDM automatic login for the current desktop user

Reboot once to activate the new group membership and exercise the complete
boot path. A LUKS full-disk encryption prompt, firmware password, or other
pre-GDM boot gate still requires local interaction.

## Boot sequence

```text
GDM automatic login
        |
        v
GNOME Wayland session + gnome-keyring-daemon
        |
        v
systemd decrypts login-keyring-password.cred through TPM2
        |
        v
uu-keyring-unlock.py unlocks the login collection over session D-Bus
        |
        v
GNOME Remote Desktop reads its normal keyring credential
        |
        v
uu-remote-bridge.service launches Wine, UU, Xvfb, and FreeRDP
        |
        v
UU device becomes reachable from the authorized controller
```

The decrypted credential exists only in systemd's protected runtime
credential directory while the oneshot unit runs. The helper uses the Secret
Service D-Bus protocol; the password is not placed in an environment variable,
process argument, repository file, or journal entry.

The master-password call is a GNOME Keyring-specific D-Bus interface rather
than a portable Secret Service method. It is validated on Ubuntu 24.04 with
GNOME Keyring 46. After a desktop upgrade, verify this unit before relying on
unattended access; an incompatible interface fails closed.

GDM can start the user manager before GNOME Keyring acquires the Secret
Service bus name. The helper waits for that specific boot dependency for up to
120 seconds. The oneshot remains `active (exited)` after success, making both
dependency state and boot verification unambiguous.

`loginctl enable-linger` is deliberately unnecessary. The user unit starts
under `default.target`, but it waits for a real GNOME Shell instead of creating
a pre-login synthetic desktop. GDM automatic login supplies that session.

## Verify

Before reboot, inspect the non-secret state:

```bash
./scripts/configure-unattended.sh status
systemctl --user status uu-keyring-unlock.service
systemctl --user status uu-remote-bridge.service
scripts/verify.sh --quick
```

Before the first reboot, `Account in tss group` should be `yes` while
`tss active in this login` can still be `no`. A temporary ACL gives this
current login the same TPM device access so bridge restarts remain reliable.
The device is recreated without that ACL at reboot, when the normal `tss`
group membership becomes active. Both status values should then be `yes`.

After reboot, verify the order and result:

```bash
journalctl --user -b \
  -u uu-keyring-unlock.service \
  -u gnome-remote-desktop.service \
  -u uu-remote-bridge.service
./scripts/configure-unattended.sh status
scripts/verify.sh --quick
```

The unlock unit must report `status=0/SUCCESS`, GNOME RDP must listen on the
configured relay port, and the bridge verifier must pass.

## Password changes

Changing the Unix password does not necessarily change the existing GNOME
login keyring password. After changing the keyring password, replace the
TPM-bound credential and reboot:

```bash
./scripts/configure-unattended.sh enable --replace-credential
```

The command prompts twice and never accepts the password as a command-line
option. A wrong keyring password makes the unlock unit fail closed; it does
not expose or reset the keyring.

## Disable and rollback

```bash
./scripts/configure-unattended.sh disable
sudo reboot
```

Disable removes the encrypted credential, temporary TPM ACL, and bridge
drop-in; disables the unlock unit; restores the prior GDM values when they
still match the managed configuration; and removes the `tss` membership if
this script added it. If someone changed GDM after setup, the script preserves
those newer values instead of overwriting them.

`./uninstall.sh` calls the same rollback before removing bridge files.

## Tools and reusable method

| Tool or interface | Role |
| --- | --- |
| `crudini` | Change only the two GDM INI keys and restore prior values |
| `systemd-creds` | Encrypt a named credential against the local TPM2 |
| `/dev/tpmrm0` and `tss` | Permit the post-login user manager to decrypt it |
| systemd user units | Enforce keyring, GNOME RDP, and bridge ordering |
| Secret Service D-Bus | Unlock the existing login collection without a GUI |
| `gdbus` | Inspect or test collection lock state without printing secrets |
| `stat` and `getfacl` | Audit credential permissions and temporary device ACLs |
| `systemd-analyze verify` | Validate unit syntax and dependency declarations |
| `journalctl --user -b` | Prove the boot result from the current boot only |

The reusable debugging sequence is:

1. Draw the complete boot dependency chain, including credential providers.
2. Identify what an interactive login supplies implicitly.
3. Replace only that missing input with a least-exposure mechanism.
4. Preserve old configuration before changing privileged files.
5. Test credential decryption separately from application startup.
6. Lock and unlock the real collection in a controlled session.
7. Restart the consumer and run end-to-end verification.
8. Remove temporary test permissions and document exact rollback.

This method applies to other GUI applications that start correctly after a
password login but fail under GDM automatic login because their Secret Service
collection remains locked.

The complete development and incident trail is recorded in
[`debugging-journey.md`](debugging-journey.md).

## Security tradeoff

GDM automatic login means anyone with physical access after boot can use the
desktop account. TPM binding protects the keyring password from being copied
off the disk and decrypted on another machine, but it does not protect the
desktop from code already running as the logged-in user. Use this mode only
where unattended remote availability is more important than local login-gate
protection.
