# Security

## Scope and authorization

Use this bridge only on a computer and UU account you are authorized to
administer. It preserves the normal UU account login and GNOME RDP credential;
it is not an account recovery, password bypass, or hidden access mechanism.
The optional unattended mode is explicit, visible systemd/GDM configuration
that the same setup script can reverse.

## Boundaries

- The complete bridge runs as the logged-in Unix user.
- The Wine prefix is under `~/.local/share/wineprefixes/uu-remote`.
- Xvfb uses an Xauthority cookie and does not listen on TCP.
- The input broker pipe exists inside that Wine prefix's wineserver namespace.
- The optional X11 physical-key helper binds an ephemeral loopback-only port,
  requires a fresh 256-bit token from the supervised launcher, and publishes
  its port only in the user's mode-0700 runtime directory.
- The FreeRDP hop targets `127.0.0.1` only and pins GNOME's configured TLS
  certificate by SHA-256 fingerprint.
- The systemd unit is a user unit and has no root privileges.
- The persistent environment file contains only a validated port, resolution,
  and private-display choice; it never contains either account credential.
- `sudo` is used while installing packages and, in unattended mode, while
  changing two GDM keys, group membership, and root-only rollback state.

GNOME Remote Desktop may listen on the LAN as configured by GNOME. Protect
the host with the normal firewall and a strong, unique relay password. The
bridge itself never forwards the configured RDP port beyond localhost.

The launcher may temporarily stop the regular
`gnome-remote-desktop.service` to bind the daemon to the actual GNOME session
bus (notably under XRDP). If that service was active beforehand, cleanup
restores it. A fixed private X display is never reused when its socket or lock
file already exists.

## Credentials and private data

The installer prompts without echo and stores the relay password with
`secret-tool` in the user's login keyring. The launcher feeds it to FreeRDP on
standard input, then unsets the shell variable. No credential is in this
repository, the systemd unit, or a process command line.

Unattended mode additionally needs the GNOME login keyring password because
PAM cannot unlock the keyring during GDM automatic login. The configurator
encrypts that password with `systemd-creds --with-key=tpm2`. Only the encrypted
blob is stored in the user's configuration directory. At session startup,
systemd decrypts it into a protected runtime credential and a oneshot helper
unlocks the login collection over D-Bus before GNOME Remote Desktop starts.
The plaintext is not stored in an environment variable, command line, unit,
or journal entry.

Adding the account to `tss` grants access to the TPM resource-manager device.
Until that membership is active at the next login, setup applies an equivalent
per-user ACL so the current bridge can still restart. The device is recreated
without that ACL during reboot, and rollback removes it when still present.

The unlock helper uses a GNOME Keyring-specific private D-Bus method available
on the validated Ubuntu 24.04/GNOME 46 stack. A future incompatible keyring
release causes the oneshot and dependent bridge startup to fail rather than
falling back to plaintext storage.

UU's own tokens and account data remain in the dedicated Wine prefix. Do not
publish that prefix or UU's logs: they can include device identifiers,
signaling endpoints, and account metadata.

Diagnostic input logs contain only count, Windows input type, flag bits,
route, result, and error. They intentionally omit virtual key codes, scan
codes, Unicode values, mouse coordinates, and clipboard data.

The X11 helper accepts physical keyboard records only. It cannot inject mouse
events or phone-text payloads, preflights each complete bounded request before
the first XTEST call, and releases all tracked held keys when its authenticated
broker connection closes. The token is supplied through inherited process
environments, not a command-line argument or persistent configuration file.

The local FreeRDP `cliprdr` channel is enabled for normal copy and paste.
Clipboard content can therefore cross between the Wine relay and the logged-in
GNOME desktop while a remote session is active. The bridge does not persist or
log that content. UU's phone IME uses `KEYEVENTF_UNICODE`, not clipboard data;
the broker translates those inputs without logging their character values.

## Binary modification controls

`patch-gameviewer.py` loads only manifests whose `review_status` is
`approved`. The current manifest accepts only these two SHA-256 states:

- Upstream GameViewerServer 4.33.0.8907:
  `be1c6c108e6e4d0d5cc15dcd22650dc5fde34c7e7b9f19eee72aba0160ea3494`
- Audited patched result:
  `30cad61560213c7a66244c6f79c9017cc9dfa81996d7faa15a0e8bf330aa0948`

It also checks each unique instruction signature at its expected file offset.
An unknown update fails closed. The original is retained as
`GameViewerServer.exe.uu-original` and can be restored without this repository.

Draft manifests produced by `audit-gameviewer.py` are deliberately rejected.
Finalization requires every candidate to be marked reviewed, validates PE
identity and non-overlapping same-length signatures, computes the complete
patched hash in memory, and does not modify the executable.

The installer applies the same policy to GameViewerHealthd and pins the UU
installer, SDL FreeRDP artifact, FreeRDP source commit, and MSYS2 dependency
packages. It also downloads libei 1.2.1 from its upstream GitLab archive with
a fixed SHA-256, applies the published one-line keymap-FD fix, and loads the
result only into the supervised GNOME RDP child. It never overwrites Ubuntu's
system libei.

`stage-uu-release.sh` first attempts non-executing archive extraction. Its
explicit `--sandbox-install` fallback uses a root-managed transient systemd
service that runs as the desktop UID with the real home hidden, the host
filesystem read-only, a single private staging directory writable, private
devices/tmp, no-new-privileges, and Internet address families disabled. An
unknown installer should still be staged in a separate VM when stronger
isolation is required.

## Residual risk

This remains unsupported proprietary Windows software running under Wine and
receiving remote input. UU can update itself, its cloud behavior can change,
and Wine does not provide a hard security sandbox for processes owned by the
same Unix user. A process already running as that user can generally control
the same desktop, whether or not this pipe exists.

Use a separate Unix account for stronger isolation. Keep the OS, Wine, UU, and
GNOME patched. Review a new UU build before adding its hash or signatures.
Do not disable the patcher's version checks to make an update "work."
Follow `docs/upstream-maintenance.md` and preserve each old approved manifest.

GDM automatic login removes the local login gate after boot. Anyone with
physical access can use the desktop account, and code running as that user can
access the unlocked keyring. TPM binding prevents offline reuse of the
credential on another machine; it does not defend an already logged-in
desktop. A pre-boot disk-encryption prompt also remains interactive.

## Repository policy

Commit source, scripts, documentation, hashes, and disassembly notes only.
Do not commit:

- NetEase executables or DLLs
- FreeRDP/MSYS2 compiled artifacts
- Wine prefixes or registry files
- RDP passwords, UU tokens, device IDs, or raw production logs
- Crash dumps or screenshots containing private desktop content
