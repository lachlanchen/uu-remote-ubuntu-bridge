# SSH and port mapping between Ubuntu bridge hosts

## What works, and what it is not

UU's **Port mapping / 端口映射** can forward a local TCP port to an SSH
server on a remote Ubuntu bridge host. In the 2026-09-05 live test, a
UU 4.39.2.1561 controller under Wine mapped local `127.0.0.1:22709` to
`127.0.0.1:22` on a UU 4.34.0.8979 Ubuntu peer. Native OpenSSH then authenticated
with a dedicated Ed25519 key and returned the peer's Linux hostname and user.
No extra Wine socket patch, virtual NIC, router change, or SSH daemon change
was needed on either tested host.

After the peer's own agent upgraded it to the audited 4.39.2.1561 build,
**both SSH directions were independently verified** using one native UU
mapping and one reverse SSH forward. Each host returned the other's actual
Linux hostname and user using its own dedicated key. This is live-session
acceptance, not a claim of uninterrupted or reboot-persistent transport.

This is **one forwarded service, not a virtual LAN**. It does not make remote
LAN addresses, broadcast discovery, ping, or every other port reachable. SSH
works normally over that TCP stream, including `scp`, `rsync`, and additional
SSH forwards. Native UU Terminal is a separate feature; see
[the Ubuntu terminal guide](native-ubuntu-terminal.md).

### Important: control ownership and availability

The live mapping later became unavailable. Reopening the panel displayed a
takeover prompt because the peer was already being controlled. We canceled
instead of displacing that controller. The observations establish that this
workflow cannot be treated as an independent, guaranteed always-on VPN; they
do not establish what initially removed the listener.

- Stop if UU asks to take over another user's active connection. Coordinate
  with the peer before proceeding; do not automate accepting that prompt.
- Keep the UU controller and enabled mapping running. Closing/restarting UU,
  a route failure, or control-ownership changes can interrupt SSH.
- Saved aliases, keys, and mapping configuration are not proof that a live
  mapping automatically reconnects after reboot. Check the listener and SSH.
- The installed `uuyc-cli.exe --help` had terminal commands but no public
  mapping-management subcommand. This helper deliberately does not edit UU's
  private database or fabricate a vendor CLI flag.
- UU desktop connectivity and SSH-mapping availability are distinct checks.

### Recover an existing mapping without restarting the desktop

On the tested 4.39.2 pair, a native terminal session-list query initialized the
vendor connection and reopened the controller's already-saved SSH mapping:

```bash
# Requires add --device-id; this lists sessions, not a new terminal shell.
timeout 15 uu-ssh terminal lab --list-sessions
ss -ltn '( sport = :22709 )'
uu-ssh check lab
```

The query returned `No active sessions.`; a wineserver-owned loopback listener
then appeared and real SSH succeeded. This happened twice without accepting a
GUI takeover, changing the peer's desktop, or restarting either bridge. It
**does not create a missing mapping**. A query failure, ownership prompt, or
absent listener still requires diagnosis; do not automatically accept takeover.

One restored mapping subsequently disappeared despite unchanged local UU
service/server PIDs and an active reverse SSH process. Its disappearance also
closed the SSH return path. Therefore a successful query does not prove the
connection will stay open: the vendor lifecycle still matters. Current `.slog`
files are binary, so a growing file is not a decoded disconnect explanation.
Do not attribute a precise cause without peer timestamps or readable evidence.

After the second recovery, the peer completed **30/30 bidirectional SSH
rounds, zero failures, over 348 seconds**. The same owned reverse SSH process
survived throughout, with no error in its retained pane. A separate 237568-byte
known UTF-8 fixture (English, Chinese, Japanese, quotes, and newlines) also
returned byte-exactly through both paths. These establish usable current
transport, not a reboot test. No real desktop controller was attached during
the peer's final input check, so desktop-control coexistence still requires
that actual client acceptance.

Longer observation caught another mapping loss after those passing rounds:
the retained SSH pane exited 255 with `Connection to 127.0.0.1 closed by
remote host.` A subsequent attempt to open one native terminal failed during
setup with vendor `Streamer error: 9012` (exit 6), before a shell appeared.
Device inventory still said online. No meaning for that undocumented code
has been established; do not equate “online” with an available control slot.
Likewise `uu-agent status` describes outgoing controller connections, not
proof that no inbound desktop controller is attached. These observations
supersede any interpretation of the 30-round pass as an all-day reliability
guarantee.

After a drop, check both listeners, confirm the previous reverse process has
exited, and restart **only the one owned forward** after the UU mapping works
again. Do not run a second native mapping on its return port, restart RDP,
weaken SSH authentication, or add an unbounded reconnect/takeover loop.

## Set up the SSH alias

The normal bridge installer now installs `uu-ssh`. To add only this helper to
an already healthy bridge, without rebuilding/restarting its runtime:

```bash
install -d -m 0755 "$HOME/.local/bin"
install -m 0755 scripts/uu-ssh "$HOME/.local/bin/uu-ssh"
```

Run on the **controller**, not the destination:

```bash
uu-ssh add lab --port 22709 --user YOUR_REMOTE_USER --device-id UU_DEVICE_ID
uu-ssh key
```

`--device-id` is optional and enables the `terminal` shortcut. `add` creates
an alias and a key; **it does not create or activate the UU mapping**.

In the controller's UU panel, select the destination, then **Port mapping**:

| Field | Example |
| --- | --- |
| Name | `SSH-lab` |
| Local port | `22709` |
| Target address | `127.0.0.1` |
| Target port | `22` |
| Protocol | TCP |

The target loopback belongs to the **remote host**. The local loopback belongs
to the **controller**. This was verified on the two tested bridge profiles;
a custom network namespace would require its own reachability check.

Confirm the peer's SSH host fingerprint through a trusted independent channel
before accepting first-use trust. Then authorize only the public key:

```bash
ssh-copy-id -i "$HOME/.ssh/id_ed25519_uu_bridge.pub" uu-lab
uu-ssh check lab
ssh uu-lab
```

The peer needs a running SSH server. Inspect `ssh.socket`, `ssh.service`, and
the port-22 listener before installing or enabling anything; socket activation
can make `ssh.service` initially appear inactive while SSH still works.

## Everyday commands

```bash
uu-ssh list
uu-ssh check lab
uu-ssh lab
ssh uu-lab 'hostname; uptime'
scp ./report.md uu-lab:Documents/
rsync -av --progress ./notes/ uu-lab:Documents/notes/
uu-ssh terminal lab --new-session
```

`terminal` invokes the existing `uu-agent term` path. On an Ubuntu destination
with the native terminal patch, the vendor's default **PowerShell** entry
opens the real Ubuntu login shell. An old peer without the installed terminal
proxy/broker needs its own controlled bridge update first. Port mapping to
its already-running native SSH server can work independently of that patch.

For normal OpenSSH options, use `ssh` directly, e.g. `ssh -v uu-lab` or
`ssh -L 18080:127.0.0.1:8080 uu-lab`. No `.bashrc` reload is necessary.

## Both directions through one UU mapping

Two independently created UU mappings are possible to configure, but
simultaneous controller ownership must be tested rather than assumed. A
simpler option is **one UU mapping plus one reverse SSH forward**:

```text
A:127.0.0.1:22709 -- UU mapping --> B:127.0.0.1:22
B:127.0.0.1:22999 -- reverse SSH over that connection --> A:127.0.0.1:22
```

On A, after `uu-ssh check lab` succeeds:

```bash
uu-ssh reverse lab --listen-port 22999
```

Leave this command running in one terminal, or a deliberately named tmux
session. Ctrl+C closes only this tunnel. It does not start an auto-restart
service or change either desktop. The helper uses `ExitOnForwardFailure=yes`
and `BatchMode=yes`, so an occupied port or missing authentication fails.

On B, create B's **own** key and return alias:

```bash
uu-ssh add server --port 22999 --user YOUR_USER_ON_A
uu-ssh key
```

Authorize B's public key in A's `~/.ssh/authorized_keys`, verify A's host
fingerprint, and test on B:

```bash
ss -ltn '( sport = :22999 )'
ssh uu-server 'hostname; id -un'
uu-ssh check server
```

Require a loopback-only listener. SSH daemon policy must allow remote
forwarding; a non-default `GatewayPorts yes` can force a wider bind despite
the client's requested address. Do not weaken server policy automatically.
The reverse direction remains dependent on the original UU mapping and SSH
process. This topology was verified in both directions on the two live hosts
after restoring the saved native mapping. Both agents independently checked
host identity, key authentication, and loopback-only listeners. The initial
takeover blocker was not bypassed by forcing a second control session.

For an intentionally persistent *current login session*, a named tmux pane
can own the forward (this is not boot autostart):

```bash
tmux new-session -d -s uu-ssh-lab-return uu-ssh reverse lab --listen-port 22999
tmux set-option -w -t uu-ssh-lab-return:0 remain-on-exit on
tmux capture-pane -p -t uu-ssh-lab-return:0.0 -S -20
```

`remain-on-exit` retains the pane's exit message if transport fails; it does
not retry anything. Inspect it and check port ownership before recovering.
Never blindly respawn a live pane or kill someone else's similarly named
session. Record the owning host, exact session/pane, ports, and command in the
private handoff so the peer does not launch a competing return tunnel.

For truly independent unattended networking, use an approved VPN or existing
reverse-tunnel gateway separately. This change installs neither.

## Files, safety, and removal

The helper uses only Python's standard library and OpenSSH. It writes:

- `~/.ssh/id_ed25519_uu_bridge{,.pub}`: dedicated per-computer keypair, reused;
- `~/.ssh/uu-bridge/NAME.conf`: scoped `uu-NAME` alias;
- a managed Include at the beginning of `~/.ssh/config`, followed by `Host *`
  to restore global scope for the original config;
- a private timestamped SSH-config backup when that file changes;
- `~/.config/uu-ssh/peers/NAME.json`: local port, username, optional device ID.

The helper serializes alias setup, writes config files atomically with mode
`0600`, refuses unmanaged fragments and unrelated preexisting aliases, and
does not disable host-key checking or enable agent forwarding. Repeated
setup preserves keys and unrelated configuration. Updating a saved peer's
port is explicit; `add` does not delete host-key trust when the peer changes.

Never copy a private key or password into Nutstore or a public repository.
Only exchange public keys. UU authorization protects the mapping, while SSH
adds its own host verification and user authentication. Other local users
may reach a loopback port, so loopback alone is not authentication.

Uninstalling the bridge removes the helper executable but deliberately keeps
SSH keys, trust, and per-peer configuration. To retire a peer, disable its
UU rule, remove its managed alias/metadata after review, and revoke that
computer's public key on the destination if it should no longer have access.
Do not overwrite all of `authorized_keys` or delete a shared key blindly.

## Validation and troubleshooting

```bash
python3 -m unittest discover -s tests -p test_uu_ssh.py -v
ssh -G uu-lab
ss -ltn '( sport = :22709 )'
uu-ssh check lab
```

The tests cover actual OpenSSH config parsing, preservation of unrelated
global settings, idempotence, key reuse, alias conflicts, invalid input,
symlink rejection, and clear diagnostics for a missing mapping. They do not
pretend to emulate vendor NAT traversal or account/control permissions.

Connection refused: inspect the mapping before changing passwords or SSH.
If a peer device ID is saved, `uu-ssh check` prints the optional one-shot
terminal-status query above for a refused connection. It **never executes it
automatically**, starts a service, or accepts takeover. An unrelated non-SSH
listener does not receive that recovery hint.
SSH banner but authentication failure: check the destination's authorized
public key and user. Changed host key: verify the destination identity, never
automatically erase known-host entries. Do not restart XRDP or change keyboard
layouts to fix a TCP mapping.

### Visible desktop but clicks or keys fail

Treat input separately from SSH. On the RDP-relay peer, mouse events logged
`route=rdp focus=timeout result=0 error=21` while its operator deliberately
foregrounded UU's management window to configure port mapping. The broker
refused to inject into the wrong window. After the management-focus lease
was released, both X11's active window and Wine's `GetForegroundWindow()`
identified `Ubuntu-Desktop-Relay` again.

Check the timestamp: an old focus error is not evidence of a new failure.
Verify X11 **and** Win32 foreground state where applicable; X11 focus alone
does not establish Wine focus. Keep the peer's proven RDP or direct-X11
profile, and release only management focus owned by the diagnostic session.
Do not inject test clicks into someone's active application. Isolated mouse,
symbol, Chinese, emoji, and long-text tests can validate the patched route,
but only a real UU client test confirms delivery from the user's device.

The recorded case had foreground state restored and isolated tests passing;
real-client click/typing confirmation was still pending. Do not call input
accepted based solely on log silence or the bridge verifier's historical
controller-input check.

References: [OpenSSH forwarding options](https://man.openbsd.org/ssh),
[SSH aliases, Includes, and host-key identity](https://man.openbsd.org/ssh_config),
and live testing of the installed [official UU Remote](https://uuyc.163.com/)
client. The vendor behaviors above are observed, version-specific results,
not a claimed vendor API contract.
