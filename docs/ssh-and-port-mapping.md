# SSH and port mapping between Ubuntu bridge hosts

## What works, and what it is not

UU's **Port mapping / 端口映射** can forward a local TCP port to an SSH
server on a remote Ubuntu bridge host. In the 2026-09-05 live test, a
UU 4.39.2.1561 controller under Wine mapped local `127.0.0.1:22709` to
`127.0.0.1:22` on a UU 4.34.0.8979 Ubuntu peer. Native OpenSSH then authenticated
with a dedicated Ed25519 key and returned the peer's Linux hostname and user.
No extra Wine socket patch, virtual NIC, router change, or SSH daemon change
was needed on either tested host.

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
process. This topology is based on standard OpenSSH forwarding; simultaneous
two-host acceptance was deferred when the live peer required takeover.

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
SSH banner but authentication failure: check the destination's authorized
public key and user. Changed host key: verify the destination identity, never
automatically erase known-host entries. Do not restart XRDP or change keyboard
layouts to fix a TCP mapping.

References: [OpenSSH forwarding options](https://man.openbsd.org/ssh),
[SSH aliases, Includes, and host-key identity](https://man.openbsd.org/ssh_config),
and live testing of the installed [official UU Remote](https://uuyc.163.com/)
client. The vendor behaviors above are observed, version-specific results,
not a claimed vendor API contract.
