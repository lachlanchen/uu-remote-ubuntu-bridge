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

## Install and use

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
