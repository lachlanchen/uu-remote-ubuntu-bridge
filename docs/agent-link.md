# Private agent messages over SSH

`uu-link` supplies a small durable communication channel between cooperating
agents on the two Linux hosts. It uses the existing `uu-ssh` aliases and native
OpenSSH, not the Wine terminal screen or simulated typing. No new port,
background service, password store, bridge restart, or GUI takeover is needed.

## Install without changing a working desktop

On **both** hosts, from this repository:

```bash
install -d -m 0755 "$HOME/.local/bin"
install -m 0755 scripts/uu-link "$HOME/.local/bin/uu-link"
```

The normal installer also installs the helper, and the upgrade rollback list
includes it. Uninstall removes the helper but **keeps private message history**.
Installing this one script does not deploy unrelated source changes or update
the installed desktop-runtime digest. Python 3 and OpenSSH are required.

First configure and verify each host's alias using
[the SSH guide](ssh-and-port-mapping.md). Confirm the host-key fingerprints
through the peer before trusting them. `uu-link` requires known host keys and
public-key authentication; it does not prompt for passwords or enroll hosts.

## Send, inspect, reply

Here `lab` is a configured peer on the workstation; `workstation` is the
reverse alias configured on the lab host. Use your actual peer names.

```bash
# Workstation: one message, one bounded delivery attempt.
printf '%s\n' 'Ready for your test. 中文 / 日本語 / "quotes"' | uu-link send lab

# Lab: list message IDs, then read a specific message.
uu-link inbox
uu-link read MESSAGE_UUID

# Lab: send a correlated reply to the workstation.
printf '%s\n' 'Accepted; my test is complete.' |
  uu-link send workstation --reply-to MESSAGE_UUID

# Workstation: check replies and its delivery receipts.
uu-link inbox
uu-link outbox
```

You can send a UTF-8 Markdown handoff directly:

```bash
uu-link send lab --file /path/to/private-handoff.md
```

The maximum message text is 64 KiB of UTF-8. Chinese, Japanese, emoji, quotes,
and newlines are preserved. Output uses JSON escapes for terminal safety;
`\u4e2d\u6587` is the stored Chinese text, not an encoding failure. Message
contents are **never executed**, pasted into a GUI, or submitted to an agent.
An agent must explicitly inspect the inbox; sending does not awaken a stopped
Codex session or imply that another agent has read or accepted the request.

## Disconnects and safe retries

Every outgoing message is saved locally **before** SSH starts. The first
output reports its UUID even if transport subsequently fails. A successful
receipt confirms that the peer durably stored the exact message ID and
SHA-256 digest—not that the peer completed the requested task.

```bash
uu-link outbox
uu-link retry MESSAGE_UUID

# Prepare a message while offline without attempting any connection.
printf '%s\n' 'Next action after recovery...' | uu-link send lab --queue-only
```

Each attempt times out after at most 20 seconds. Retry keeps the original ID.
If the receiver stored a message but the acknowledgement was lost, resending
stores only one copy and returns the same receipt. A conflicting payload with
the same ID is rejected. If a local receipt already exists, retry simply shows
that prior receipt; it is not a fresh connectivity check. There is deliberately
no automatic reconnect loop and no hidden UU terminal/mapping operation.

Messages and receipts live under `~/.local/state/uu-link/`:

- `inbox/`: received immutable envelopes;
- `outbox/`: original outgoing envelopes with destination peer;
- `receipts/`: exact delivery confirmations.

Directories are owner-only (`0700`), files are `0600`, writes are atomic and
flushed to disk before acknowledgement, and symlink targets are refused.
UUIDs allow concurrent senders and duplicate retry protection without a long-
running lock server. Do not commit these folders or raw private messages.
Review their size occasionally; there is no automatic pruning or deletion.

## Coordination contract

Each message should state its host, task, owned action, stop conditions, and
evidence needed for acceptance. Sender names are descriptive metadata, not a
per-agent cryptographic identity: trust comes from the SSH account/key and
pinned host key. Any process already authorized as that Unix user can submit
messages. This is not a security boundary between mutually untrusted agents.

For two active operators, agree which host owns native UU mapping recovery,
which owns the single reverse SSH forward, and which owns desktop testing.
Never recover both directions simultaneously or accept a takeover implicitly.
Use a shared private Markdown file (for example Nutstore) as a fallback when
the UU mapping itself is down. The inbox survives reboot, but availability
still depends on the [underlying vendor transport](ssh-and-port-mapping.md).

## Validation

```bash
python3 -m unittest discover -s tests -p 'test_uu_link.py' -v
```

The isolated tests cover UTF-8/multiline fidelity, simultaneous retry
deduplication, timeouts with retained outbox, strict/fixed SSH invocation,
receipt validation, collision refusal, size validation, and symlink guards.
Live two-host deployment and round-trip acceptance must be recorded separately;
unit tests alone do not establish network reachability.
