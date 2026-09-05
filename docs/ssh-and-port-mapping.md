# SSH and port mapping between Ubuntu bridge hosts

## What works, and what it is not

### Current operating direction (2026-09-05, later test)

The working mapping was subsequently reversed: the workstation originates
UU Port Mapping **to the peer**, rather than the peer targeting the workstation
where the user normally attaches a UU viewer. The peer's device card showed
no other controller, so its existing mapping opened without takeover. The
operator reused both existing alias ports and the confirmed-dead return pane:

```text
workstation:127.0.0.1:22709 -- UU mapping --> peer:127.0.0.1:22
workstation: one SSH -R   --> peer:127.0.0.1:22022 --> workstation:22
```

There is still only one native UU mapping and one non-retrying return forward.
Neither host needs a Windows/Mac intermediary, new account, desktop restart,
keyboard patch, or alias change. Both native SSH identities, UTF-8, requested
exit statuses and independent SCP round trips passed. The peer measured 15
fresh command successes over 68 seconds (472–974 ms); the workstation measured
six bidirectional rounds over roughly 107 seconds without a failed round.

This is now the accepted operating direction for a viewer targeting the
workstation, not a guarantee of arbitrary multi-controller coexistence. On
2026-09-05 the user completed the real-use check while the intended UU desktop
remained usable: `ssh-uu-lachlanserver` from 7090 reached LACHLANSERVER, and
`ssh uu-7090` inside that shell returned to OptiPlex-7090. Both directions
therefore coexisted with the actual viewer in this retained session.

The **under control** state shown on 7090 is expected: LACHLANSERVER's mapping
is the controller carrying `22709 -> 7090:22`. It is not evidence that a hidden
desktop viewer is watching 7090. Minimize the status window if desired, but do
not press **Disconnect** while this route is needed. Disconnecting the carrier
removes both that mapping and the dependent `22022` SSH return path; an already
open shell may survive briefly until TCP notices, then closes. Taking over the
mapping's target from another controller can likewise displace the carrier.

Short/new-channel stalls also remain a disclosed limitation. Initial checks
and an eager nested bulk-stdin test sometimes timed out while the listener and
return process remained alive; later ordinary commands recovered without
reconnecting UU. A nested 237594-byte binary transfer started after an explicit
inner-shell readiness marker passed byte-exactly in 1.46 seconds. That comparison
does not establish the vendor's internal cause or fix every streaming case.
A temporary, isolated OpenSSH multiplexing experiment passed 10 reused commands
in 54–160 ms each; no production sharing setting was deployed, and its bounded
master was stopped without touching the owned return connection.

### Earlier opposite direction and takeover failure

In the earlier controlled test on 2026-09-05, direct two-Ubuntu SSH and file transfer
worked in both directions, without Windows or Mac. A subsequent user-confirmed
UU desktop takeover disconnected the same mapping and its return forward.
RDP/VNC and the logged-in Ubuntu applications stayed intact. Thus direct
transport is verified; simultaneous independent UU desktop control is **not
supported by that tested ownership behavior at the mapping target**. See the
acceptance record below; do not generalize it to both mapping directions.

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

For durable agent-to-agent handoffs over these SSH aliases, use
[`uu-link`: private inbox, outbox, and delivery receipts](agent-link.md).
It requires no extra daemon and never executes message contents.

### Mapping hosted by an existing SSH-reachable controller

The mapping listener does not have to run on the computer where the shell is
opened. A tested three-host topology used a native Mac controller that was
already reachable through a separately pinned SSH alias:

```text
Ubuntu A -- strict SSH --> Mac controller:127.0.0.1:22022
                              |
                              +-- native UU Port Mapping --> Ubuntu B:127.0.0.1:22
```

Configure that route explicitly; it is never inferred or used as a fallback:

```bash
uu-ssh add lab --port 22022 --user YOUR_REMOTE_USER \
  --via-ssh-host trusted-mac --shell-transport ssh
uu-ssh check lab
uu-shell lab
```

The generated `uu-lab` alias uses `ProxyJump trusted-mac`, while the destination
still uses its own pinned `HostKeyAlias`, dedicated key, strict host checking,
and public-key-only authentication. `uu-shell` executes that alias because the
profile says `shell=ssh`; old profiles continue to select native Terminal.
Use `--direct` to deliberately remove a previously configured jump host.

This topology has a real third-host dependency: the controller Mac, its SSH
service, UU app, account session, and loopback-only mapping must all remain
available. In the live 2026-09-05 test it returned the exact Linux host/user and
preserved five command exit statuses. The vendor mapping was then kicked by the
server after about 421 seconds. One later GUI Reconnect click internally made
three ICE attempts; none selected a candidate pair and no listener returned.
Those observations prove useful fail-closed access when the mapping is live,
not unattended availability. Do not hide this dependency or claim it is a
direct two-Ubuntu connection.

A native UU host can also forward to another SSH machine on its own LAN. Record
that target explicitly so diagnostics describe the real topology:

```bash
uu-ssh add lab --port 22023 --user YOUR_REMOTE_USER --direct \
  --mapping-target 192.0.2.25 --shell-transport ssh
```

This changes only local alias metadata; it does not create or edit the vendor
rule. Verify that the controlled UU host can reach that target before relying
on it, and pin the final SSH server's host key independently.

In a separate 2026-09-05 acceptance test, a Wine4.39 controller mapped through
an authorized native Windows4.38 host to an Ubuntu SSH server on the Windows
host's LAN. Five fresh shells preserved exact exit statuses, a237638-byte
binary/UTF-8 file made a byte-identical round trip, and one reverse SSH forward
gave the Ubuntu peer an independently verified shell, PTY, UTF-8 stream, exit
status, and file round trip back to the controller. Another18 shell checks
passed over three minutes without losing the mapping. This removes the Mac
dependency from that topology, but the native Windows host and the one UU
mapping session remain runtime dependencies; the observation is not a reboot
or unattended-reconnect claim.

### Important: control ownership and availability

**A passing SSH test is not proof of takeover-safe availability.** A later
real-use report on 2026-09-05 found the Windows-assisted route closed while
the user was taking control of the Windows neighbor. The peer's retained
reverse-SSH pane exited255 at19:19:18 local time, and both its carrier listener
and the workstation's return listener were gone. Native Windows SSH still
worked; its UU GUI/server processes retained their earlier start times.
This locates the failure at the session-dependent carrier rather than proving
a Windows reboot, broken SSH keys, or lost LAN. The exact vendor disconnect
reason was not decoded, so the takeover is a strong correlation, not a
decoded causal result for every historical drop.

The subsequent direct-Ubuntu test did establish an ownership gate in the tested
client/server state. The peer selected the Ubuntu UU endpoint itself, whose
page reported another controller, then clicked **Port Mapping** (not Desktop
or a Terminal warmup). UU explicitly required **Take over device**, explaining
that port mapping was available after takeover. The operator canceled; no
scratch rule editor or listener opened, no profile changed, and relay focus
was restored. This is a concrete compatibility result for this state, not a
claim about every UU version, account tier or platform.

An operator can separately coordinate releasing only the direct UU desktop
connection while retaining RDP/VNC and the logged-in Linux desktop, then test
direct mapping with the control slot free. That is not a simultaneous-control
fix: a later UU takeover can still invalidate the carrier. Never log out,
terminate applications or force takeover merely to obtain a passing SSH test.

#### Slot-free direct test and real desktop takeover

The user subsequently switched to another desktop transport and explicitly
allowed a coordinated test. The peer opened the actual Ubuntu endpoint's
Port Mapping panel. With the old viewer released, there was no takeover prompt;
an existing saved loopback rule connected successfully. Reusing it avoided
creating a duplicate scratch rule:

```text
Ubuntu B:127.0.0.1:22022 -- UU Port Mapping --> Ubuntu A:127.0.0.1:22
Ubuntu B: one SSH -R    --> Ubuntu A:127.0.0.1:22709 --> Ubuntu B:22
```

Both sides verified the pinned native SSH identities and their own key-only
authentication. Five fresh shells preserved UTF-8 and requested exit statuses
`0, 7, 0, 17, 0`. The workstation independently checked a byte-exact
237610-byte binary/Unicode round trip, an actual SCP upload/download, and a
nested return command through the peer's `uu-shell` alias. The mapping panel
remained open behind the restored desktop relay; one owned reverse forward
replaced the previously dead Windows-assisted forward. No new Wine/network
patch, account, duplicate service, or desktop restart was necessary.

The user then actually took control of Ubuntu A through direct UU. By19:59:46
local time, the workstation observed its return listener absent. The peer
independently saw its carrier listener absent, the retained reverse SSH exit
after a remote close, and the Ubuntu device page reporting another controller.
The user confirmed the takeover. This controlled event demonstrates the
coexistence failure in this setup, without attributing every historical drop
to the same cause. Neither bridge nor either Linux desktop was restarted.

Keep these outcomes separate:

- **Direct two-host transport:** verified; the Windows intermediary is removed.
- **Both shell directions:** verified while the one mapping remains connected.
- **RDP/VNC desktop plus mapping:** remained usable during the test.
- **Independent direct-UU viewer plus mapping to the same device:** failed
  the actual takeover test. General/Security settings exposed no concurrent
  ownership switch in the inspected client.
- **Unattended/reboot reconnection:** not established by this test.

When a viewer takes over, preserve it. Do not reclaim control from a health
check, restart XRDP/GNOME, or mask the loss with another forwarding loop.
After the user explicitly releases that viewer, one coordinated mapping-panel
reconnect followed by replacement of the confirmed-dead owned return forward
can restore the verified route. Restoration is not a simultaneous-control fix.
An independent network or a genuinely isolated second UU device would require
a separate design and authorization; copying login/device state into another
prefix is not an established or safe concurrency solution.

Removing the Windows neighbor is a separate requirement from surviving UU
desktop takeovers. A direct Ubuntu-to-Ubuntu UU mapping can remove that third
machine yet still depend on UU control ownership and vendor session lifetime.
Do not relabel it an always-on private network after a few successful shells.
Test an actual mapping with strict host identity, file and exit-code checks,
then separately confirm user-observed desktop coexistence. Cancel takeover
prompts instead of forcing the test to pass.

For takeover-independent SSH, use a separately approved native network path
between the Ubuntu hosts. No such existing path was found in this incident:
private-LAN probes timed out and neither host had global IPv6 or an installed
private overlay. A new overlay, router forward or cloud relay is a user choice,
not an automatic fallback inside `ssh`, `uu-shell`, or a reconnect loop.

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
- A jump-host profile skips the meaningless local socket probe and lets one
  bounded strict OpenSSH check cover the jump and mapped destination. Failure
  does not trigger a GUI reconnect, password prompt, retry, or alternate route.

SSH itself does not acquire UU desktop-control ownership. A single native UU
mapping plus one SSH return forward avoids a **second UU control connection**,
but does not guarantee that the first mapping can coexist with an active
inbound UU viewer. Keep `ssh`, `uu-ssh check`, `uu-ssh reverse`, and `uu-link`
as consumers of an already-open mapping: none may silently run a vendor
Terminal command, take over, or reconnect a desktop. They should fail/queue
when the mapping closes. Activating the underlying UU connection is a separate
coordinated action. Network bandwidth is still shared; this separation is
about session ownership, not a claim of zero resource contention.

### Historical one-shot recovery, not a default reconnect recipe

The current `uu-ssh check` deliberately does **not** suggest this warm-up.
Even listing native terminal sessions can initialize a vendor connection;
that is not a read-only transport probe and its ownership effects are not
guaranteed. Only use a bounded test below in a coordinated troubleshooting
window, never as an automatic health check or while another agent owns recovery.

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

The user subsequently reported that some UU connections may have been closed
manually. Those drops therefore do not prove a spontaneous vendor timeout or
bridge defect. The actual saved Port Mapping panel was inspected: the rule
was still enabled, its header said connection failed, and one Retry Connection
click explicitly required taking over an already-controlled device. Cancel
preserved that controller. This establishes the current ownership conflict,
not the trigger of every historical drop. A minimized window still existing
is not proof that its mapping connection remains active.

Prefer a real mapping-panel connection over relying on a terminal-status query
as an undocumented warm-up. If the selected destination is already controlled,
coordinate with its owner; a direct-only alternative is to reverse the native
mapping direction and create one SSH return forward. Test that topology rather
than assuming it bypasses ownership policy. Never silently replace the user's
preferred direct transport with a cloud relay.

After a drop, check both listeners, confirm the previous reverse process has
exited, and restart **only the one owned forward** after the UU mapping works
again. Do not run a second native mapping on its return port, restart RDP,
weaken SSH authentication, or add an unbounded reconnect/takeover loop.

## Set up the SSH alias

### Inspect the existing mapping panel without fighting relay focus

The bridge deliberately restores its desktop relay focus once per second.
Use the existing console focus lease for a brief management operation, not a
service stop or a loop that fights the supervisor:

```bash
uu-remote-console focus-client
# Inspect the existing UU Port Mapping window on the private display.
# If it requests takeover of another controller, cancel.
uu-remote-console release-client
```

Always release the lease, including after errors. For automation use an EXIT
trap around the inspection, and capture the original active window ID for an
additional restore fallback. The helper discovers the bridge display; do not
guess a display number or type into the user's project terminal. These commands
do not create a noVNC server or another desktop. Keep the actual mapping window
open behind the restored relay while testing its lifetime; do not equate Close
with Minimize or assume either preserves the connection without a live test.

The updated helper filters out transient UU toasts and restores either the
SDL/FreeRDP `Ubuntu-Desktop-Relay` or the existing loopback RealVNC relay.
Older versions searched only for the SDL title, so `release-client` could
return nonzero on the native VNC profile even though it removed the lease.
Three isolated mocked-X-command tests cover both relays and lease cleanup
when the relay is missing; they never activate the real desktop.

An existing installation can update only this helper without restarting UU:

```bash
# From the reviewed repo checkout; retain a private copy of the old helper first.
install -m 0755 scripts/uu-remote-console "$HOME/.local/bin/uu-remote-console"
```

### Configure the native SSH alias

The normal bridge installer now installs `uu-ssh`. To add only this helper to
an already healthy bridge, without rebuilding/restarting its runtime:

```bash
install -d -m 0755 "$HOME/.local/bin"
install -m 0755 scripts/uu-ssh "$HOME/.local/bin/uu-ssh"
```

Run on the **controller**, not the destination:

```bash
uu-ssh add lab --port 22709 --user YOUR_REMOTE_USER \
  --device-id UU_DEVICE_ID --shell-transport ssh
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
uu-shell lab
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
  It also records the explicit shell transport, optional SSH controller hop,
  and remote-side mapping target used in diagnostics.

The helper serializes alias setup, writes config files atomically with mode
`0600`, refuses unmanaged fragments and unrelated preexisting aliases, and
requires strict host-key checking plus public-key-only authentication. It
also disables password prompts, agent forwarding, connection multiplexing, and
multi-attempt TCP connection loops for these aliases. Repeated
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
`uu-ssh check` never starts a vendor connection, regardless of whether the
peer has a saved device ID. It reports the mapping and says to preserve active
desktops/cancel takeover; the earlier suggestion to query Terminal sessions
was removed because it can initialize UU transport. Each socket stage has a
five-second timeout and the key-only SSH command has a separate 15-second
timeout, strict host checking, no agent forwarding, and no configured forwards.
Only that diagnostic process is terminated on its timeout. No retries, bridge
restart, or cloud fallback are performed.
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
