# Security

## Scope and authorization

Use this bridge only on a computer and UU account you are authorized to
administer. It preserves the normal UU account login and GNOME RDP credential;
it is not an account recovery, password bypass, persistence, or hidden access
mechanism.

## Boundaries

- The complete bridge runs as the logged-in Unix user.
- The Wine prefix is under `~/.local/share/wineprefixes/uu-remote`.
- Xvfb uses an Xauthority cookie and does not listen on TCP.
- The input broker pipe exists inside that Wine prefix's wineserver namespace.
- The FreeRDP hop targets `127.0.0.1` only and pins GNOME's configured TLS
  certificate by SHA-256 fingerprint.
- The systemd unit is a user unit and has no root privileges.
- `sudo` is used only while installing Ubuntu and WineHQ packages.

GNOME Remote Desktop may listen on the LAN as configured by GNOME. Protect
the host with the normal firewall and a strong, unique relay password. The
bridge itself never forwards port 3390 beyond localhost.

## Credentials and private data

The installer prompts without echo and stores the relay password with
`secret-tool` in the user's login keyring. The launcher feeds it to FreeRDP on
standard input, then unsets the shell variable. No credential is in this
repository, the systemd unit, or a process command line.

UU's own tokens and account data remain in the dedicated Wine prefix. Do not
publish that prefix or UU's logs: they can include device identifiers,
signaling endpoints, and account metadata.

Diagnostic input logs contain only count, Windows input type, flag bits,
route, result, and error. They intentionally omit virtual key codes, scan
codes, Unicode values, mouse coordinates, and clipboard data.

## Binary modification controls

`patch-gameviewer.py` accepts only these two SHA-256 states:

- Upstream GameViewerServer 4.33.0.8907:
  `be1c6c108e6e4d0d5cc15dcd22650dc5fde34c7e7b9f19eee72aba0160ea3494`
- Audited patched result:
  `30cad61560213c7a66244c6f79c9017cc9dfa81996d7faa15a0e8bf330aa0948`

It also checks each unique instruction signature at its expected file offset.
An unknown update fails closed. The original is retained as
`GameViewerServer.exe.uu-original` and can be restored without this repository.

The installer applies the same policy to GameViewerHealthd and pins the UU
installer, SDL FreeRDP artifact, FreeRDP source commit, and MSYS2 dependency
packages.

## Residual risk

This remains unsupported proprietary Windows software running under Wine and
receiving remote input. UU can update itself, its cloud behavior can change,
and Wine does not provide a hard security sandbox for processes owned by the
same Unix user. A process already running as that user can generally control
the same desktop, whether or not this pipe exists.

Use a separate Unix account for stronger isolation. Keep the OS, Wine, UU, and
GNOME patched. Review a new UU build before adding its hash or signatures.
Do not disable the patcher's version checks to make an update "work."

## Repository policy

Commit source, scripts, documentation, hashes, and disassembly notes only.
Do not commit:

- NetEase executables or DLLs
- FreeRDP/MSYS2 compiled artifacts
- Wine prefixes or registry files
- RDP passwords, UU tokens, device IDs, or raw production logs
- Crash dumps or screenshots containing private desktop content
