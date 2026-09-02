# Changelog

All notable bridge changes are recorded here. The project uses semantic
version tags for bridge releases; the separately audited UU version remains
locked by the release manifest.

## [Unreleased]

### Fixed

- prevent UU's native Ubuntu prompt from wrapping its final `$` onto a new row
  by removing inherited VTE-only controls and using a plain `screen` terminal
  profile only inside UU child shells; normal desktop terminal prompts remain
  unchanged and the Wine-to-PTY acceptance test guards the regression

### Added

- an authenticated loopback terminal compatibility bridge that keeps UU's
  native terminal transport but replaces Wine's immediately exiting
  PowerShell placeholder with the Ubuntu user's real PTY login shell; the
  isolated acceptance covers wrong-token rejection, exact UTF-8, home-directory
  startup, and terminal resizing without adding SSH or storing credentials

- adaptive direct-X11 phone text: ordinary representable characters retain
  the fast key route, while multiline and non-English Unicode use a bounded,
  authenticated clipboard paste; composition editing keys can remain ordered
  inside the same batch, and an isolated test verifies exact Chinese, two-line,
  and split-surrogate delivery without touching the logged-in desktop
- fail-closed semantic paste ownership verification plus a one-way VNC
  clipboard boundary: UU/private cut text may enter Ubuntu, while target text
  cannot feed back into the private viewer and trigger stale repeated pastes
- an isolated VNC clipboard acceptance test covering client cut-text receipt,
  exact target Unicode paste, and absence of reverse clipboard feedback
- deterministic semantic paste ownership for both X11 `CLIPBOARD` and
  `PRIMARY`, preventing VTE's `Shift+Insert` from inserting an older selection
  when phone dictation or smart punctuation uses the Unicode text route

- a persistent, validated `UURB_VNC_GRAB_KEYBOARD` setting that defaults to
  `on` for the dedicated nested VNC relay, plus explicit layout-aware x11vnc
  options so Shift/Ctrl and semantic symbols survive intermediate desktops
- an isolated RFB keyboard probe that verifies 21 shifted symbols and two CJK
  keysyms in exact order against a Japanese XKB target without touching the
  logged-in desktop
- opt-in stable desktop-resolution following for the X11/VNC relay; it aligns
  at startup, debounces later RDP size changes, ignores tiny transient windows,
  and restarts only the UU bridge
- an opt-in `UURB_UU_AUDIO=off` boundary that disables Wine PulseAudio only
  inside UU's dedicated prefix when a controller must never open UU's WebRTC
  capture channel; the compatibility default remains `system`
- persistent `auto`, `xrdp`, `physical`, and exact-display desktop targeting;
  explicit targets wait instead of falling back to a different GNOME session
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
- hash-bound UU `4.34.0.8979` patch support after semantic review; its former
  promotion acceptance is withdrawn until a stopped-prefix cold-start and
  fresh signaling test pass
- an absolute `UURB_WINEPREFIX` canary override for testing a copied prefix
  without replacing the production prefix
- a runtime-discovered `uu-agent` wrapper for the vendor controller CLI,
  private display inspection, and bounded Mac terminal-agent workflows
- a reusable `uu-remote upgrade` transaction that fast-forwards clean source,
  promotes only a fully accepted UU build, preserves login and keyboard
  settings, refreshes bridge code, verifies XRDP state, and keeps local
  rollback copies
- an opt-in process-local cursor guard for hosts where hidden or
  cross-process-invalid Wine cursor handles break UU's independent cursor
  channel; existing hosts retain the unmodified path by default
- a single-instance GNOME launcher that presents only UU's installed
  management window through a loopback-only TigerVNC sidecar while every Wine
  process remains on the private display
- an authenticated, SSH-tunneled macOS launcher for viewing and controlling
  the current physical Ubuntu desktop without a second GNOME RDP client
- an explicit `uu-remote console` command for the localhost-only noVNC
  diagnostic view

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
- bind the local UU console's VNC and WebSocket listeners exclusively to
  loopback, disable x11vnc's implicit IPv6 listener, and discover only the
  bridge-owned Xauthority file
- bind the external current-desktop VNC relay to Ubuntu loopback, require both
  SSH and VNC authentication, and remove it after the viewer disconnects

### Documentation

- distinguish digital mute from a genuinely closed ALSA PCM, cover regenerated
  SHI review builds, and document the final prefix-scoped UU audio cutoff
- distinguish UU's audio-disabled internal RDP relay from an unrelated SDL
  application holding a physical PipeWire sink open, with a scoped diagnosis
  and Unreal `-nosound` recovery path; also document the later Wine UU
  playback/capture streams and service-scoped XRDP audio isolation
- document why a multi-session host can show an empty UU desktop and how to
  bind UU to the existing XRDP desktop without restarting or logging it out
- document automatic maintenance, Codex resume state, reboot behavior, track
  selection, another-computer handoff, and the remaining approval boundary
- distinguish a smaller XRDP source that leaves white space from a larger XRDP
  source that clips the relay, and document resolution alignment that restarts
  UU without restarting XRDP
- explain why the old nested input route could accept every sampled
  `SendInput` call while losing fast keyboard transitions, why slow typing and
  pointer motion could mask that fault, and why the direct X11 route fixes the
  local defect without claiming a universal upstream guarantee

### Fixed

- carry the native-terminal port and per-start token across UU's
  `CreateProcessAsUser` environment reconstruction with an atomic mode-0600
  runtime handoff; the proxy still prefers inherited configuration, and the
  isolated test now removes both variables before proving authentication

- keep UU's layered Wine/Qt login window mapped behind the focused relay;
  minimizing it during window replacement could raise `BadWindow`, close the
  login IPC client, and destroy an otherwise healthy signaling room
- keep the controller's mandatory media setup alive without touching host
  audio by pairing the prefix-scoped PulseAudio cutoff with a private ALSA
  null playback/capture backend; `off` alone could advertise the device yet
  leave a controller waiting forever in `InitPlayout`
- rediscover the native VNC relay after RealVNC replaces its startup window
  while entering full-screen mode, so UU's management window cannot remain in
  front of the shared desktop
- prevent the validated host from remaining invisible after an apparently
  successful room request: forced duplicate XRDP Pulse endpoint names stalled
  Wine Core Audio before signaling; the host now reaches
  `room_state_changed: created` through the prefix-local silent backend and
  leaves no UU stream attached to PipeWire or a physical PCM
- add an opt-in, loopback-only native VNC desktop relay for X11/XRDP hosts
  where nested GNOME RDP authenticates but renders a uniform black or white
  UU canvas; the RDP relay remains the compatibility default
- prevent UU from silently switching from a long-lived XRDP desktop to a new
  physical/GDM desktop when the systemd user-manager display changes
- reject a mismatched live X11 desktop/private UU canvas during verification,
  so top-left-only video with black right or bottom space is diagnosed from
  geometry instead of passing an otherwise healthy runtime check
- explicitly use classic VNC's eight-byte credential width when deriving the
  loopback current-desktop password, allowing long RDP relay credentials to
  survive non-interactive installation
- prevent the desktop launcher from splitting one Wine prefix across physical
  and private X displays, which left video working but caused broker
  `focus=timeout`, `result=0`, and `error=21` for keyboard and mouse input
- replace the recursive full-desktop launcher view with a window-scoped
  sidecar; closing it minimizes UU and restores the private RDP relay focus
- replace a Mac shortcut that tunneled to an unrelated Xvfb display with a
  probe-tolerant view of the existing `Ubuntu-Desktop-Relay` window
- keep the private `Ubuntu-Desktop-Relay` window focused after controller or
  terminal-agent diagnostics activate the UU GUI, preventing Wine focus
  timeouts from leaving video visible while mouse and keyboard input fail
- preserve the 65536 open-file limit when a system application-profile
  wrapper crosses `runuser`/PAM, and teach verification to find both the
  wrapper service and GNOME RDP's listener inside its network namespace
- make `uu-agent` query the persistent systemd user bus so XRDP, VNC, SSH, and
  nested desktop session buses cannot hide the healthy bridge
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
- build the deterministic compatibility verifier inside a pinned promotion
  checkout, distinguish expected pre-refresh source drift from binary drift,
  and require the wrapper to inspect the terminal promotion phase before
  reporting success
- permit an operator-requested retry of a failed accepted promotion only after
  promotion tooling changed, while retaining the failed task under
  `tasks/retired` and refusing an unchanged retry loop
- make new MinGW compatibility builds omit PE timestamps and compare legacy
  health stubs after normalizing only the COFF timestamp and PE checksum,
  retaining byte-exact rejection for every executable field
- wait for the actual GNOME relay listener and the selected direct-X11 helper
  before initial runtime verification, preventing stale Wine process names
  from turning normal service startup into a false promotion failure
- suppress the exact audited `devcon.exe` while retaining its vendor backup,
  transactionally remove accumulated `gvinput` records, and disable Bluetooth
  enumeration only inside UU's dedicated Wine prefix
- prevent a “finding routes” startup stall caused by 527 failed virtual-input
  roots and 21,894 retained Wine Bluetooth devices; cold device initialization
  now completes in 8–9 ms instead of consuming two CPU cores for minutes
- require the current service start to complete device initialization and
  create a fresh signaling room, so a warm canary cannot authorize promotion
  by itself
- avoid duplicate GitHub validation runs by validating feature work on pull
  requests and direct pushes only on `main`
- keep the login-preservation gate strict for registry, user-cache, identity,
  token, and remote-assist state while excluding only UU 4.34's non-account
  `setting.ini` guide state
- run the complete installed bridge verifier before a promotion snapshot so
  stale RDP port, libei, descriptor-limit, or source-runtime state fails
  without interrupting the working UU release
- contain an upstream Wine memory or thread runaway with service-level memory,
  swap, and task ceilings so systemd rebuilds only the relay instead of
  allowing it to freeze the desktop
- resolve extended direct-X11 navigation keys through the active display's
  keysym map instead of assuming one fixed XFree86 keycode table

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

- all 91 source, shell, documentation, updater, transaction, migration, and
  helper-build tests pass
- production promotion from UU `4.33.0.8907` to `4.34.0.8979` passed both
  runtime checks while preserving the account, direct-X11 input profile, and
  the independently running XRDP process
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
