# Community fork review — 5 October 2026

Seven public forks and all their published branches were reviewed against
upstream `1aeed96243afe947a77d4e3419c92271c3389c93`. The result is one narrow
registry-plan fix, with regression coverage, and invitations to contribute
separate compatibility changes. Ubuntu 22.04 and 26.04 remain community port
work, not newly accepted upstream platforms.

This was a source review in a separate worktree. No fork installer or runtime
was executed. The running accepted bridge, desktop, keyboard routes, clipboard,
account state, service configuration, release manifests and existing tags were
left alone. In particular, `uu-4.42.1.2835-accepted-20261001` remains unchanged.
A repository change is not a deployment to an installed bridge.

## Inventory and decisions

Commit counts are not a measure of unmerged functionality: some contributions
were already merged through a different history. The pinned source below,
existing PRs and actual file differences were checked together.

| Fork | Reviewed branch / commit | Finding and decision |
| --- | --- | --- |
| [misakano7545](https://github.com/misakano7545/uu-remote-ubuntu-bridge) | `main` / `1aeed96243af` | Identical to the reviewed upstream head; nothing to integrate. |
| [cnsunfishegg](https://github.com/cnsunfishegg/uu-remote-ubuntu-bridge/tree/60ea913a215a16db99c3096dbec615eb2032f916) | `main` / `60ea913a215a` | Experimental 26.04 port, packaging, controller lifecycle, input and audio changes. Adopt only the independently reproduced empty-plan fix; request separate portability and controller PRs. |
| [bysanhz](https://github.com/bysanhz/uu-remote-ubuntu-bridge/tree/971a5ad69f2c326e5a98f8c70e6e13bc55a81d71) | `main` / `971a5ad69f2c`; `compat/ubuntu-22.04` / `4a64e3786f8b` | Useful 22.04 dependency/CLI detection and reproducible build ideas. Request a rebased compatibility PR. Keep experimental 4.41 native-input acceptance separate. |
| [hasakiikiiPRO](https://github.com/hasakiikiiPRO/uu-remote-ubuntu-bridge/tree/cd999123211b57d1f8475bb347d47210f30e214d) | `main` and `fix/gnome-wayland-remote-and-resolution` / `cd999123211b` | Controller window and canvas adjustments are coupled to relay visibility and geometry. Request isolated controller tests before adopting. |
| [yuechuuu](https://github.com/yuechuuu/uu-remote-ubuntu-bridge/tree/d213a1c8f105ce46bf40c590add4320a3fcfa766) | `main` and `fix/refresh-freerdp-runtime` / `d213a1c8f105c` | FreeRDP contribution already handled by merged [PR #10](https://github.com/lachlanchen/uu-remote-ubuntu-bridge/pull/10). The SSPI shim matches current upstream; no need to merge this older runtime branch again. |
| [JessieKaa](https://github.com/JessieKaa/uu-remote-ubuntu-bridge/tree/5b494aa61506933e5d38608903cf448067366d35) | `main` / `5b494aa61506` | A detailed Mint/Cinnamon controller-only guide. Useful as a separately labelled guide; it is not evidence for hosting a remotely controlled Linux desktop. |
| [robbie194](https://github.com/robbie194/uu-remote-ubuntu-bridge) | `main` / `551388db3e28`; `fix/uu-cursor-navigation` / `3066fe7ad898`; `fix/wine-to-x11-clipboard-pr` / `9f90ae82845c`; `fix/gnome-x11-capture-recovery` / `90116fe8d9cd` | Cursor and clipboard are already in merged [PR #9](https://github.com/lachlanchen/uu-remote-ubuntu-bridge/pull/9) and [PR #11](https://github.com/lachlanchen/uu-remote-ubuntu-bridge/pull/11). Capture recovery is a separate, substantial host policy change; defer it. The capture branch also contains the empty-plan fix. |

## Integrated fix: an empty registry plan must have no lines

`inspect-wine-device-registry.py plan` previously printed a newline when its
list of deletion keys was empty. `clean-wine-device-registry` reads those lines
with Bash `mapfile`, so it received one empty key instead of zero keys.

A relevant case is a prefix with `winebth` still enabled (`Start=3`) but no
audited stale device keys. The cleaner still needs to disable that service,
then reaches the deletion loop. The erroneous empty entry would attempt
`wine reg delete "" /f` and could abort cleanup. A prefix already clean with
`Start=4` normally exits the cleaner early, but its plan must obey the same
zero-target contract.

The inspector now prints only when there are deletion keys. The selection of
audited keys, refusal of unrelated ROOT devices, backups and service management
are unchanged. The idea is credited to
[cnsunfishegg's `7c8d627`](https://github.com/cnsunfishegg/uu-remote-ubuntu-bridge/commit/7c8d6275f8ccb52195d308828094e73d0aa4b987)
and is also present in
[robbie194's capture branch](https://github.com/robbie194/uu-remote-ubuntu-bridge/tree/90116fe8d9cdaf6e558880a295ff00102de5d489).
Only this small change was adapted; neither branch was cherry-picked wholesale.

The regression uses temporary registry files with both `Start=3` and `Start=4`,
feeds the actual inspector output into Bash `mapfile`, requires zero entries
and zero output bytes, and verifies the source registry is unchanged. Both
cases failed before the fix (one empty entry) and pass afterward. The existing
nonempty-plan and unrelated-device refusal tests still pass. No live Wine
prefix is cleaned by these tests.

Local validation after the fix:

- `python3 -m unittest discover -s tests -v`: 182 tests ran successfully, with
  two opt-in live tests skipped (isolated X11 and live systemd recovery).
- All 12 documentation tests passed after the review was added; local links
  resolve. Python compilation, cleaner shell syntax and `git diff --check`
  passed.
- The production bridge stayed active with the same process and restart count.
  No end-to-end 22.04/26.04 test or production cleanup was attempted.

## Ubuntu 26.04: promising work, distinct acceptance still needed

The fork's
[port notes](https://github.com/cnsunfishegg/uu-remote-ubuntu-bridge/blob/60ea913a215a16db99c3096dbec615eb2032f916/docs/ubuntu-26-04-port.md)
explicitly mark controller support experimental. They distinguish a private
libei 1.2.1 backport for the 24.04/GNOME 46 baseline from the system libei
library for their 26.04/GNOME 50 target. They also reject an inherited backport
configuration after an OS upgrade. Keeping an older private library out of
a newer daemon is a useful portability boundary; upstream must validate the
actual package ABI and runtime library mappings before accepting that port.

The fork also supplies packaging and controller lifecycle fixtures. Its
[live lifecycle record](https://github.com/cnsunfishegg/uu-remote-ubuntu-bridge/blob/60ea913a215a16db99c3096dbec615eb2032f916/docs/controller-lifecycle-check-2026-09-23.md)
describes Ubuntu 26.04 **X11 with Quickshell**, not complete GNOME 50 Wayland
acceptance. Remote typing, long sessions and multi-monitor acceptance are
outside that record. The reviewed CI still runs on Ubuntu 24.04. Passing
source/package checks is valuable, but does not establish the promised host
and controller combinations.

Ask for two independently reviewable contributions:

1. OS/dependency selection, including the current `check-host.sh` preflight,
   migration refusal, installer, runtime, verifier and tests. Keep 24.04
   behavior intact; expose any unaccepted new platform as experimental.
2. Controller lifecycle and packaging improvements with isolated fixtures.
   Keep host capture, incoming control, binary approval and input defaults
   separate from outgoing controller UI changes.

Broker-first physical input, keycode selection, audio defaults and experimental
manifest approval should each have their own evidence. They are not harmless
consequences of supporting another Ubuntu release. Existing Chinese dictation,
phone text, JIS/US symbols, modifiers and clipboard behavior must be preserved.

## Ubuntu 22.04 and release/build work

The [22.04 compatibility branch](https://github.com/bysanhz/uu-remote-ubuntu-bridge/tree/4a64e3786f8bea0a7b3203fee63bba6c4dcc6363)
selects `freerdp2-x11` or `freerdp3-x11`, detects available `grdctl` commands,
and checks whether GNOME Remote Desktop links libei before building a backport.
Its locale-independent `readelf` check and CI matrix are useful. It predates
the current early host preflight, so merging the older installer alone would
not produce a coherent supported path. Request a small rebase covering all
entry points and actual GNOME 42 control/reconnect evidence.

The fork's main branch additionally introduces pinned source builds, manifest
discovery and a 4.41 native-input candidate. Its
[4.41 static review](https://github.com/bysanhz/uu-remote-ubuntu-bridge/blob/971a5ad69f2c326e5a98f8c70e6e13bc55a81d71/docs/releases/4.41.2.2602-static-review.md)
records a disposable-prefix cold start without a connected controller. That
does not replace the existing 4.42 acceptance records. Build improvements
should preserve user proxy settings and avoid force-resetting a user's cached
source checkout. Manifest discovery must reuse strict manifest validation;
matching an installer hash alone is not runtime acceptance.

## Geometry and capture changes

The hasakiikiiPRO branch changes window selection, hides the incoming relay
while showing the local console, and forces controller window geometry. Those
operations could affect a simultaneously shared desktop. An upstream PR needs
an explicit host/controller boundary and tests for popup focus, incoming
capture, full-frame display and pointer coordinates before adoption.

The [robbie194 capture report](https://github.com/robbie194/uu-remote-ubuntu-bridge/blob/90116fe8d9cdaf6e558880a295ff00102de5d489/docs/gnome-shell-capture-crash-20260802.md)
is useful diagnostic evidence: on that host, GNOME Shell's MIT-SHM failure
preceded the relay disconnect. The report also records recurrence despite
identity geometry and explicitly does not establish a complete root-cause fix.
Its recovery code adds geometry checks, idle inhibition and a full Shell unit
override. This can contain one failure class but changes desktop lifecycle and
future vendor-unit inheritance. It must be separately opt-in, owned and
reversible, with no restart or settings change to another active desktop.

## Contribution and acceptance checklist

- Rebase a focused PR onto current upstream, retain attribution, and state the
  exact OS, desktop/session type, Wine, UU and controller versions tested.
- Add a failing regression or isolated fixture; retain existing 24.04 tests.
  Do not replace the accepted release or bypass strict binary hashes.
- Separate source/package checks from live remote-control evidence. Use a
  test machine for fresh installation, reconnect and unattended reboot.
- For input-affecting changes, exercise rapid physical keys, JIS and US
  symbols/modifiers, phone text, Chinese and English dictation, multiline
  revision without losing earlier text, and bidirectional clipboard.
- For controller/capture changes, verify mouse coordinates at different
  resolutions and that existing RDP/VNC/UU access keeps the intended desktop.
- Check terminal exit status and the selected transport separately; native UU
  terminal limitations are documented in [the feature matrix](features.md).
- Publish only sanitized version/test summaries. Keep account state, device
  IDs, credentials, raw clipboard/input logs and runtime profiles private.

Source tests can establish the registry fix's contract. They cannot certify
every remote device or a new OS release. See [host compatibility](compatibility.md)
for the supported baseline and [feature evidence](features.md) for current
runtime claims.
