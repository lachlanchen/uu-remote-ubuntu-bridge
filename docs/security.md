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
- The optional X11 input helper binds an ephemeral loopback-only port,
  requires a fresh 256-bit token from the supervised launcher, and publishes
  its port only in the user's mode-0700 runtime directory.
- The native terminal helper independently binds an ephemeral IPv4
  loopback-only port, requires its own fresh 256-bit token, accepts at most
  four sessions, and launches only the bridge user's login shell. A mode-0600
  ephemeral handoff beside the audited proxy crosses UU's reconstructed user
  environment and is removed when the bridge stops.
- The local management-window sidecar binds an uncredentialed VNC listener to
  IPv4 loopback only, exports one UU X window rather than the private root
  desktop, and exists only while its local TigerVNC viewer is open.
- The optional macOS current-desktop relay exports only the existing
  `Ubuntu-Desktop-Relay` window, binds authenticated VNC to Ubuntu loopback,
  and is reachable from the Mac only through passwordless SSH. Its x11vnc
  password file is obscured rather than encrypted, so it is mode 0600 and
  never substitutes for the SSH boundary.
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

The installer also derives the loopback VNC authentication file from the first
eight bytes of that credential, which is the limit of classic VNC password
authentication. Truncating explicitly avoids x11vnc rejecting a longer RDP
credential during non-interactive setup. The file is user-readable only and
x11vnc uses it solely for the short-lived SSH-tunneled current-desktop relay.
macOS Screen Sharing can retain the matching eight-character prefix in the
user's login keychain.

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

Terminal commands and output cross the authenticated UU channel and an
authenticated localhost socket only. They are never written to bridge logs;
the terminal log records only readiness, session PID/size, rejection, and
close metadata. The per-start terminal token is absent from command lines and
the port-only ready file. It exists in a user-readable-only runtime handoff
because UU deliberately rebuilds the terminal child's environment; shutdown
removes that file, and an old token cannot reach a stopped broker. The helper
neither starts `sshd` nor stores a password or SSH key. A terminal has the
normal authority of the logged-in Ubuntu user, and `sudo` retains the host's
normal policy.

The X11 helper accepts at most 2,048 keyboard, mouse, or semantic-text records
per request. This finite ceiling covers long provisional dictation while
preventing caller-controlled unbounded allocation.
Representable phone text is normalized to ordinary key chords. Newline, CJK,
emoji, and other non-representable commits may cross the token-authenticated
loopback protocol as bounded UTF-16, are converted in memory to UTF-8, and are
owned by a target-desktop `xclip` process for paste. Payloads are never logged
or written to repository/runtime files, but they deliberately remain in the
user's clipboard after a successful paste. The helper verifies a new X11
`CLIPBOARD` and `PRIMARY` owners before synthesizing the paste and fails closed
on timeout, so
stale clipboard content is not pasted. The nested VNC relay accepts client
cut-text but blocks target-to-private clipboard feedback. The helper preflights each complete
request before the first XTEST call and releases all tracked held keys and
buttons when its authenticated broker connection closes. Mouse coordinates,
key values, and text are never logged. The token is supplied through inherited
process environments, not a command-line argument or persistent configuration
file.

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
explicit `--sandbox-install` fallback prefers Bubblewrap with all namespaces
unshared, no network namespace, no capabilities, the real home hidden, the
host filesystem read-only, and only one private staging directory writable.
Where unprivileged user namespaces are unavailable, the explicit systemd
backend applies equivalent root-managed transient-service controls including
private networking, private devices/tmp, no-new-privileges, and denied Internet
address families. An unknown installer should still be staged in a separate VM
when stronger isolation is required.

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

The optional maintenance timers do not make binary approval autonomous. A
daily check can download and statically stage a newer installer, and Codex can
resume source analysis in a private repair clone, but its output remains a
draft until a maintainer verifies instruction semantics and completes the
Windows/controller acceptance procedure. The repair clone has a disabled push
URL and Codex runs with workspace-write access, no interactive approvals, and
`NoNewPrivileges`; a healthy live relay is never restarted by a check.

Automatic live promotion is a separate opt-in and accepts neither a Codex
result nor binary approval alone. The exact official installer and patched
server hashes must be bound into a committed maintainer acceptance record
covering disposable-prefix behavior, controller input, reconnect, service
restart, login preservation, and at least 270 stable seconds. Evidence must
exist in the same pinned commit.

Before the accepted installer runs, the promotion helper verifies the current
runtime, checks local login-state markers, waits for the configured quiet
window, stops only the UU bridge, and snapshots the complete Wine prefix. The
installer runs over that same prefix to preserve UU's normal account state.
The login registry section and account-state trees must remain byte-identical
before UU is reopened. Any mismatch, runtime failure, process interruption, or
reboot restores the whole old prefix and blocks automatic retry. XRDP is
queried only to prove its active state did not change; the promotion helper
contains no XRDP mutation command.

Updater state can contain proprietary binaries and local diagnostic context.
It is stored outside the repository with user-only permissions and must not be
copied to another computer or published. CDN query credentials are removed
before metadata is persisted.

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
