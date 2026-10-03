# One shell shortcut, explicit transports

`uu-shell DEVICE` can now use an **enrolled LazyTunnel SSH route**, the existing
UU port-mapped SSH profile, or UU's native terminal. The profile chooses the
transport. There is no automatic fallback, desktop takeover, mapping reconnect,
new daemon, or credential distribution.

```bash
uu-shell --list
uu-shell lab                 # transport selected in the private profile
uu-shell --lazy lab          # explicitly use enrolled LazyTunnel SSH
uu-shell --lazy lab hostname
uu-shell --native lab        # explicitly use UU's vendor terminal
```

The LazyTunnel route prints `uu-shell: LazyTunnel SSH -> lab` on stderr. It uses
the existing pinned SSH configuration and the device's own login key. Normal
commands, interactive shells, and their SSH exit statuses retain their meaning.
This route works independently of a UU desktop connection. File transfer still
uses the existing `scp-lazy` command.

Select this route on Linux or macOS after ordinary LazyTunnel enrollment:

```bash
uu-ssh add-fleet lab --fleet-peer lab --device-id YOUR_UU_DEVICE_ID
uu-shell lab
uu-ssh check lab
```

For a Mac destination add `--terminal-shell zsh`. The native Ubuntu adapter uses
the `powershell` compatibility entry. Old profiles and `ssh uu-DEVICE` retain
their existing meanings. `add-fleet` backs up a changed profile and leaves old
mapping metadata and SSH keys untouched. Passing `--native` never substitutes
a cloud connection when the vendor terminal fails.

## Install the shortcuts without restarting remote desktops

Linux/macOS have Python 3 and Bash. This optional installer updates only the
two shell helpers, privately backs up changed files, and records the available
Python interpreter in the helper's shebang:

```bash
python3 scripts/install-shell-tools.py
```

For several devices, an operator can supply a reviewed private inventory:

```json
{
  "lab": {
    "name": "lab",
    "shell_transport": "lazytunnel",
    "fleet_peer": "lab",
    "device_id": "YOUR_UU_DEVICE_ID",
    "terminal_shell": "powershell"
  }
}
```

```bash
python3 scripts/install-shell-tools.py --inventory /private/path/peers.json
```

On Windows, the equivalent helpers require PowerShell and the already installed
LazyTunnel client, without Python or Wine:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\install-shell-tools.ps1 -Inventory C:\private\peers.json
uu-shell lab hostname
uu-shell --native lab
```

Private profiles live in `~/.config/uu-ssh/peers/`; rollback copies live in
`~/.local/state/uu-shell-tools/backups/`. Windows uses the same paths below
`%USERPROFILE%`. Keep inventories and backups out of Git. The installers do
not edit SSH service configuration, carriers, desktop binaries, input patches,
login records, keyboard/dictation settings, or clipboard settings.
The Windows installer invocation permits only that PowerShell process to run
the reviewed script; it does not change the machine's execution policy.

The bridge's runtime source digest includes the older shell helpers. A
shortcut-only refresh is not a complete bridge-runtime promotion. Retain the
accepted runtime source and its digest; do not rewrite that digest to conceal
the distinction. Future full guarded upgrades can incorporate these helpers.

## Native UU limits observed on 3 October 2026

An eight-device LazyTunnel matrix produced correct hostnames on all 64 routes,
including eight self routes. Six Windows-source checks initially exceeded the
ten-second connection deadline and passed with a thirty-second deadline.
This is point-in-time evidence, not an uptime or reboot guarantee.

After deployment, a fresh `uu-shell` sweep also passed all 64 directed hostname
checks without retry. Linux/macOS/Tiny11 routes commonly completed within
0.8–4.3 seconds; routes into the physical Windows host took about 10–13 seconds,
and routes originating there took 15.6–24.9 seconds. Reachability is verified;
the Windows session-start delay remains a performance limitation. Each source
also preserved `exit 7`. Editing a legacy UU mapping with `uu-ssh add` preserves
an existing fleet default and native shell choice unless explicitly changed.

The account's local UU list had seven other devices online and nine offline.
Fresh native terminal checks were deliberately separate:

- The current Mac release accepted a fresh Windows-under-Wine CLI connection,
  returned its actual hostname and user, and exited the test shell.
- Two older Mac installations returned `invalid open response`.
- Two native Windows installations and one Ubuntu bridge rejected terminal
  startup with `Client version too low`, before their shells opened.
- Another Windows device returned `invalid open response`; it was not enrolled
  in LazyTunnel and was not treated as a working SSH endpoint.
- A later Mac connection also encountered Streamer error 9012. The successful
  earlier shell does not establish uninterrupted vendor availability.

Both Ubuntu native PTY adapters independently returned their Linux hostnames
and exact Chinese text. That verifies the installed shell adapter, not vendor
controller compatibility. They currently report proxy exit zero even after
`exit 7`; use SSH when a remote command's exit status must be reliable.

The native Mac CLI's `term DEVICE_ID` opens its GUI terminal picker and exits
after acknowledging the request. This is **not** a verified shell in the calling
terminal. The wrapper reports that distinction and rejects Windows-specific
session flags instead of silently ignoring them. No vendor binary, version
check, controller-ownership gate, or healthy desktop was patched to conceal a
failed compatibility test. Offline devices require a reachable powered-on
endpoint before shell acceptance or enrollment can be completed.
