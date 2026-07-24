# Changelog

All notable bridge changes are recorded here. The project uses semantic
version tags for bridge releases; the separately audited UU version remains
locked by the release manifest.

## [Unreleased]

### Added

- opt-in daily official-release checks and a 15-minute health monitor that
  persist across reboot without periodically restarting a healthy bridge
- resumable Codex repair workspaces using explicit `codex-auto-review` and
  `medium`
  settings, atomic thread/session state, structured output, bounded retry, and
  an independently rerun test suite
- immutable `track-rdp-broker-20260724` and `track-direct-x11-20260724` aliases that name
  the two validated input behaviors without treating them as a linear upgrade
- opt-in guarded promotion for a newer exact-hash release carrying a complete
  maintainer acceptance record, with in-place account reuse and full-prefix
  rollback

### Security

- gate automatic Codex repairs at 20% included usage, fail closed when the
  limit cannot be verified, and ignore purchased or reset credits
- strip expiring CDN query keys from state, cap downloads, disable repair-clone
  pushes, and keep unknown UU binaries behind static staging and human semantic
  approval
- make live recovery observation-only by default; restart and known-good
  reinstall require an explicit `--auto-reinstall` opt-in after two
  consecutive health failures
- require acceptance to be bound to both installer and patched-server hashes,
  wait for a quiet UU window, compare login/account state before opening UU,
  and keep XRDP outside every promotion action

### Documentation

- document automatic maintenance, Codex resume state, reboot behavior, track
  selection, another-computer handoff, and the remaining approval boundary
- explain why the old nested input route could accept every sampled
  `SendInput` call while losing fast keyboard transitions, why slow typing and
  pointer motion could mask that fault, and why the direct X11 route fixes the
  local defect without claiming a universal upstream guarantee

### Fixed

- use the installed `codex-auto-review` model at medium reasoning effort for
  resumable repair tasks by default, while preserving explicit overrides
- persist the absolute Codex executable selected during configuration so NVM
  installations remain reachable from the smaller systemd user-service `PATH`
- snapshot the complete two-host keyboard and troubleshooting handoff into
  every repair checkout before starting or resuming Codex
- preflight the Ubuntu Bubblewrap/AppArmor path before spending a Codex
  attempt, retain repair evidence across an explicit retry, and keep
  `workspace-write` instead of bypassing the sandbox
- record an explicit non-promotion result for every automated repair so a
  completed source patch cannot transfer into the live UU prefix before
  semantic review and controller acceptance
- document the recurring Wine `devcon` connection stall and its reversible
  live mitigation as evidence for a permanent rollback-safe fix
- query the persistent user-manager bus, accept any matching GNOME RDP process
  that actually owns the listener, and distinguish a recent restart storm from
  an old cumulative restart count
- make known-good live reinstallation opt-in and refuse live recovery when the
  service-manager probe itself is indeterminate
- import operator-authorized networkless staging on retry only after checking
  its method and all recorded binary hashes
- keep the repair manager outside systemd's pre-created
  `unprivileged_userns` mount namespace so Codex can establish its required
  Bubblewrap `workspace-write` sandbox under Ubuntu's AppArmor restrictions
- distinguish a repository-approved binary patch from end-to-end promotion
  acceptance, and correct the updater so an approved newer baseline is not
  mistaken for an already installed release
- snapshot the complete existing Wine prefix before a normal in-place UU
  installer update, preserve old audited backups, and recover automatically
  after an interrupted or failed transaction without automatic retry
- avoid duplicate GitHub validation runs by validating feature work on pull
  requests and direct pushes only on `main`

- wait for the actual FreeRDP relay window after Wine's short-lived Unix
  launcher exits, verify that the spawned GNOME daemon owns its configured
  listener instead of accepting another RDP service on the same port, and
  rate-limit failed starts to prevent a CPU-intensive restart storm from
  freezing the desktop
- route layout-representable UU native-phone-keyboard text through the
  authenticated X11/XTEST helper after Unicode normalization, avoiding the
  same nested RDP keyboard conversion that lost accepted physical keys
- coalesce each helper request and enable `TCP_NODELAY`, removing the observed
  roughly 41 ms loopback request delay without changing input semantics

### Validation

- all 73 source, shell, documentation, updater, transaction, migration, and
  helper-build tests pass
- the promotion fixture preserves an existing account through an in-place
  update, while deliberate registry damage restores the complete old prefix
- source tests assert that promotion never starts, stops, restarts, or reloads
  XRDP
- an isolated fixed-alphabet Unicode request returned all 52 source records on
  `route=x11-text`, while X11 observed all 52 press/release transitions in the
  exact expected order
- the operator confirmed normal phone-keyboard typing was fixed; the first 72
  bounded live text calls all used `route=x11-text`, matched their requested
  counts, returned `error=0`, and completed in 0-2 ms

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

### Validation

- all 40 source, shell, documentation, migration, and helper-build tests pass
- an isolated Xvfb/XTEST run captured all 58 requested Ctrl, Enter, and
  alphabet press/release transitions
- a live direct-UU run sampled 256 successful `route=x11` physical-key calls
  with no broker errors; the operator reported very smooth typing with almost
  all former omissions resolved

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
