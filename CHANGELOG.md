# Changelog

All notable bridge changes are recorded here. The project uses semantic
version tags for bridge releases; the separately audited UU version remains
locked by the release manifest.

## [Unreleased]

No changes yet.

## [0.2.0] - 2026-07-18

Union release that preserves the `v0.1.0` fallback while packaging the later
stability, diagnostics, and opt-in host-specific extensions.

### Added

- privacy-safe `uu-remote network` transport and key-watchdog diagnosis
- deterministic installed-runtime digest verification, so a pulled checkout
  cannot be mistaken for deployed compatibility binaries
- persistent GNOME RDP descriptor threshold with bounded relay recovery
- verified, bridge-local backport of upstream libei's received-keymap FD fix
- opt-in, process-local UU adapter selection for multi-homed hosts, with
  `all`, Ubuntu-default-route, and fixed-interface modes
- opt-in physical-key pacing with a conservative zero default and a persistent
  `--physical-key-delay-ms` installer setting
- opt-in direct X11/XTEST physical-key routing with `rdp`, `x11`, and `auto`
  modes; the universally compatible RDP route remains the default
- bounded privacy-safe input categories and per-boundary timing for keyboard,
  phone text, mouse, and other calls
- a validated XRDP/Windows App recovery note that puts client reset before a
  potentially session-replacing server restart
- a complete debugging journey covering input, lifecycle, deployment, and
  unattended boot discoveries

### Changed

- pace translated phone text one character chord at a time with a persistent,
  configurable 8 ms default delay
- split bounded text, physical-keyboard, mouse, and other input telemetry and
  avoid synchronous disk flushes for successful events on the serial path
- raised the supervised GNOME RDP descriptor limit to 65536
- extended the bounded GDM/keyring startup wait to 120 seconds and retained a
  visible successful oneshot state
- pinned unattended GI checks and execution to Ubuntu's system Python so an
  active Conda environment cannot shadow `python3-gi`

### Fixed

- restored the proven original-call-then-broker fallback for ordinary input;
  selecting the route from service-side relay-window visibility can disable all
  mouse and keyboard input under Wine
- confirm the FreeRDP relay owns foreground focus before acknowledging brokered
  input, preventing successful API returns from hiding dropped keystrokes
- stopped Ubuntu 24.04's libei 1.2.1 from leaking one `mutter-shared`
  descriptor for every received keyboard-keymap message
- made Xvfb lock-file cleanup silent and ownership-safe when the server removes
  its lock during a supervised restart
- stopped UU from binding the first Wine-enumerated adapter instead of
  Ubuntu's preferred route on an affected multi-homed host
- restart the existing bridge supervisor after a debounced preferred-route
  interface change, so `default` does not remain pinned to a stale adapter
- order completed transport reports by their embedded timestamp and label
  reports older than five minutes as stale
- report cross-region relay selection without exposing either endpoint's
  location, so controller VPN/proxy routing is distinguishable from host input
- preserve a `v0.1.0` installation's unpaced text setting during upgrade;
  fresh installations retain the robust 8 ms text default
- bypass the lossy nested Wine/FreeRDP keyboard conversion on an affected
  XRDP Xorg workstation while retaining the proven relay for every other
  channel and host
- release tracked modifiers when the direct helper disconnects and refuse to
  replay any request after an ambiguous partial injection

## [0.1.0] - 2026-07-17

First supported handoff release.

### Added

- supervised UU, Wine, Xvfb, SDL FreeRDP, and GNOME RDP desktop relay
- bounded user-token input broker and automatic DLL re-injection
- opt-in TPM2-backed unattended startup after GDM automatic login
- persistent validated resolution, port, and private-display settings
- release staging, binary audit, fail-closed patching, and rollback tooling
- normal RDP clipboard relay for copy and paste

### Fixed

- normalized UU phone `KEYEVENTF_UNICODE` batches into physical virtual-key
  chords, fixing the repeated `d` and period output from mobile keyboards
- bound the bridge to the live GNOME session bus across Wayland, Xorg, and XRDP
- replaced Wine's unsupported UU event-log call with a Windows-shaped failure
- hardened complete-relay restart, prefix-scoped cleanup, and UU account
  bootstrap after process replacement

### Validation

- 28 repository tests pass locally and in GitHub Actions
- the live broker accepted a 16-event Unicode batch with `error=0`
- an end-to-end relay probe produced `aZ0.,!?` exactly on the GNOME desktop
- the full runtime verifier kept one UU server PID stable for 270 seconds

### Upgrade

Follow the [v0.1.0 release notes](docs/releases/v0.1.0.md) or the
[operator handoff](docs/update-handoff.md). Existing installations can update
without deleting the Wine prefix or signing into UU again.

[0.1.0]: https://github.com/lachlanchen/uu-remote-ubuntu-bridge/releases/tag/v0.1.0
[0.2.0]: https://github.com/lachlanchen/uu-remote-ubuntu-bridge/releases/tag/v0.2.0
