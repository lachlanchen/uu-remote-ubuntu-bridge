# Changelog

All notable bridge changes are recorded here. The project uses semantic
version tags for bridge releases; the separately audited UU version remains
locked by the release manifest.

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
