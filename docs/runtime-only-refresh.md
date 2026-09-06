# Refresh helpers without upgrading UU

Use this when the installed, audited UU release works but the repository has
new keyboard, dictation, launcher or terminal helpers. Product updates and
runtime updates are different operations.

```bash
./scripts/upgrade-uu-remote.sh apply --runtime-only --no-pull --now
```

The explicit `--now` acknowledges a brief UU reconnect. GNOME, SSH and the
logged-in applications are not restarted. Run this through an independent
terminal or SSH session; do not use UU Terminal as the only management path.

This mode runs repository tests and a live preflight, requires an approved
manifest for the installed product, captures the existing runtime, calls the
existing installer with account login skipped, and verifies the result. A
runtime installation/verification failure invokes the existing rollback.
Saved input, desktop, audio and login state are retained. It does not check
the vendor update endpoint, promote a pending release, run Codex, or change
the enabled/disabled state of maintenance timers. The optional shared X11 VNC
backend remains opt-in; Wayland hosts must retain their working RDP relay.

An interrupted machine or power failure cannot be recovered by a shell trap;
the private rollback tree remains under `~/.local/state/uu-remote-upgrader`.
Do not claim reboot or real-phone acceptance from source tests alone.
