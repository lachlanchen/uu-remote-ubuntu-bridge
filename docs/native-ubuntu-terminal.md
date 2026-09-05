# Native Ubuntu terminal through UU Remote

## Result

The UU controller's **Terminal** feature can open the bridge host's real
Ubuntu login shell. The controller may still label the choice `PowerShell`;
on this Wine-hosted Ubuntu device that label is a compatibility entry point,
not the shell that ultimately runs.

Choose `PowerShell` in the UU terminal panel. The resulting PTY runs as the
same unprivileged Ubuntu user as `uu-remote-bridge.service`, starts in that
user's home directory, loads the normal login-shell configuration, supports
interactive programs and UTF-8, and follows controller resize events.

### Controller compatibility is a separate acceptance check

The working native shell adapter does not guarantee that every vendor client
can open it. On 2026-09-05, a Windows CLI running under Wine progressed to
terminal startup against another bridge but received error1004 / "Client
version too low", although both installed products were 4.39.2.1561. Static
inspection of the audited server found separate payload-version and
`controller_cli_v2_unsupported platform=` rejection paths using that error.
The exact live rejection branch was not decoded. The opposite one-shot test
failed earlier with Streamer9012, also before the native shell broker opened
a session. Neither test establishes working desktop/terminal coexistence.

Do not change keyboard patches, restart RDP, bypass a takeover prompt, or
automatically upgrade the healthy host based solely on that generic error.
Coordinate one bounded compatibility test and check for actual native shell
output. A session-list query can itself initialize UU transport; it is not an
ownership-neutral health check. Remote command and file-transfer adapters must
also preserve exit status and byte-exact data rather than scrape a terminal
screen or inject commands into the user's existing desktop terminal.

## Why the terminal previously closed with exit code 0

UU's host received and accepted the remote request. Its log recorded a new
terminal session with `code=0`, but the bundled ConPTY helper then launched
`powershell.exe`. Wine supplies a compatibility placeholder with that name;
it produced no shell and returned success immediately. The controller
therefore accurately displayed a process that had exited with code 0. The UU
network path, account authentication, and terminal protocol were not broken.

Running the same request with UU's `cmd` option produced output, proving the
vendor terminal transport and ConPTY path before changing the runtime.

## Data path

```text
UU controller Terminal panel
        |
        | authenticated UU terminal channel
        v
GameViewerServer / conpty_bridge.exe under Wine
        |
        | launches bin/powershell.exe
        v
uu-terminal-proxy.exe
        |
        | random token + framed I/O, 127.0.0.1 only
        v
uu-terminal-bridge
        |
        | forkpty()
        v
Ubuntu user's interactive login shell
```

The Windows proxy is deliberately small. It forwards standard input and
output and reports terminal-size changes. The native broker owns PTY creation,
so commands execute in Ubuntu rather than in Wine.

## Why this does not use SSH

For normal `ssh`, `scp`, `rsync`, or a two-computer return path, use the separate
[SSH and port-mapping workflow](ssh-and-port-mapping.md). It reuses UU's native
TCP forwarding and does not replace or modify this terminal implementation.

SSH would add a second long-lived authentication path, a private key to
manage, and an avoidable network listener. UU has already authenticated the
controller and delivered the terminal stream to the local host. The bridge
therefore continues that stream through an ephemeral localhost socket instead
of logging back into the same computer.

Each service start generates a new 256-bit token. UU rebuilds a default user
environment when it launches the terminal through `CreateProcessAsUser`, so
the proxy cannot rely on inheriting service-only variables. The launcher
instead writes the port and token to `uu-terminal-bridge.runtime` beside the
audited proxy with mode `0600`, then removes it during bridge shutdown. The
ready file still contains only the port, and the token is absent from command
lines. A stale file cannot authenticate after its one broker exits and is
atomically replaced at the next start.

The native listener binds only to IPv4 loopback, compares the complete token,
accepts at most four sessions, and logs session metadata—not commands, output,
or terminal text. It grants no root access and does not bypass `sudo`.

## Prompt rendering compatibility

At UU's narrow terminal width, the final `$` can appear on a separate row.
The prompt contains non-printing title, color, and Readline controls that a
normal terminal understands but UU may count imperfectly. This is cosmetic:
commands should still appear at the active input cursor and execute normally.

Several narrower-prompt approaches were tested: changing `TERM`, stripping
inherited VTE variables, replacing `PS1` after Bash startup, disabling
Readline bracketed paste with a private inputrc, and avoiding login-shell
logout controls. Isolated PTY captures looked clean, but the real UU
controller then drew locally echoed keystrokes at the upper-left or beginning
of the row. The host still received the correct bytes, proving that the
controller's local echo depends on cursor state from the original startup
stream.

The bridge therefore keeps `TERM=xterm-256color` and launches the configured
shell as a login shell, matching the first proven implementation. Correct
interactive input placement takes priority over eliminating the wrapped `$`.
Do not globally edit `.bashrc` or `.inputrc` to hide this UU-only cosmetic
artifact.

## Install and use

For a terminal-to-terminal connection, use the short helper on either bridge.
The peer profile explicitly selects `terminal` or `ssh`; the helper never tries
one and silently falls back to the other:

```bash
# Native Terminal is the default for old and newly created profiles.
uu-ssh add lab --port 22709 --user YOUR_REMOTE_USER \
  --device-id UU_DEVICE_ID --shell-transport terminal
uu-shell lab

# Explicitly resume a known vendor session instead of opening a fresh one:
uu-shell lab --session-id SESSION_ID

# A verified mapped-SSH profile accepts normal ssh arguments/commands instead:
uu-ssh add lab --port 22709 --user YOUR_REMOTE_USER --shell-transport ssh
uu-shell lab 'hostname; id -un'
uu-shell --help
```

For `terminal`, it delegates to the existing native Terminal adapter and opens
a fresh session by default. For `ssh`, it executes the profile's pinned
`uu-PEER` OpenSSH alias. Both paths pass arguments literally and preserve the
selected transport's exit status and normal I/O/signals. It does not start a
daemon, open a desktop, activate Port Mapping, retry, or fall back to another
route. The helper itself does not fix controller-compatibility failures or a
closed mapping; acceptance still requires a real remote shell. Session-list
requests are explicit and can initialize vendor transport. File transfer
remains a separate acceptance test; use a verified mapped SSH/scp path, not
pasted terminal text as an unverified file channel.

To update only the shell/SSH entry points without restarting the desktop:

```bash
install -m 0755 scripts/uu-ssh scripts/uu-shell "$HOME/.local/bin/"
```

The installer, upgrade backup and uninstaller also include `uu-shell`.

The normal installer builds and deploys both helpers:

```bash
./install.sh --skip-packages --skip-account-login
```

It replaces `GameViewer/bin/powershell.exe` only when that path is absent or
already contains this repository's installed proxy. An unexpected vendor or
user file causes installation to fail closed. The bridge service supervises
the native broker and restarts the complete UU stack if it exits.

In the remote UU client:

1. Open the Ubuntu device.
2. Choose **Terminal**.
3. Leave the shell on **PowerShell**.
4. Run Ubuntu commands normally; use `exit` to close that terminal.

The `cmd` choice remains Wine's diagnostic command processor. Use the
`PowerShell` choice for the native Ubuntu shell.

## Verification

The isolated test creates a disposable Wine prefix and never touches the
logged-in desktop:

```bash
./scripts/build-compat.sh build/compat
./scripts/test-terminal-bridge.sh
```

It launches the proxy without either service environment variable, proving
the same mode-0600 runtime-file handoff used by UU's reconstructed user
environment. It also proves that an incorrect token is rejected and that the
accepted path delivers an interactive native shell, exact UTF-8 Chinese, the
user's home directory, and a `24x80` PTY.

For the installed service:

```bash
./scripts/verify.sh --quick
systemctl --user status uu-remote-bridge.service --no-pager
tail -n 30 ~/.local/state/uu-remote-bridge/terminal-bridge.log
```

The log intentionally contains only readiness, session PID/size, rejection,
and close events.

## Removal and compatibility

`./uninstall.sh` removes the compatibility executable only when it is
byte-identical to the installed proxy. It refuses to remove an unknown file.
`./uninstall.sh --purge` additionally removes the dedicated Wine prefix as
described in the main removal guide.

The bridge targets the audited UU host behavior in this repository. A future
UU release may change the executable name or terminal launch contract; normal
runtime-digest and release checks should reject drift rather than guessing.
Updating or restarting only `uu-remote-bridge.service` briefly disconnects UU
but does not log out GNOME, restart XRDP, or close the user's desktop apps.
