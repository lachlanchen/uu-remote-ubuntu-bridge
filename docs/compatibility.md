# Host compatibility

Check before installing (no sudo, packages, service changes, or account data):

```bash
./install.sh --check-host
```

This checks CPU and OS only. A successful check is not proof that GNOME,
remote input, account sign-in, or controller connectivity works.

| Host | Status |
| --- | --- |
| Ubuntu 24.04, x86-64, logged-in GNOME 46 | Supported baseline; complete runtime acceptance is still required |
| Ubuntu 24.04, ARM64/aarch64, Oracle Ampere/Neoverse VPS | Unsupported; installer exits before changing the host |
| SSH-only/headless server with no logged-in GNOME desktop | No desktop for this bridge to share |
| Another desktop, distribution, or architecture | Not covered by the validated installation path |

## Community ports under review

The [5 October 2026 fork review](fork-review-20261005.md) covers all seven
public forks, including 22.04 compatibility and a 26.04 preview. These are
source-review findings, not an expansion of the accepted installation path.

| Community work | Evidence boundary |
| --- | --- |
| Ubuntu 22.04 — bysanhz | Dependency and GNOME CLI compatibility changes; a focused rebase and live host acceptance are still needed |
| Ubuntu 26.04 — cnsunfishegg | Experimental port and packaging; documented X11/Quickshell controller checks do not establish GNOME 50 Wayland or full input/reboot acceptance |

The existing 24.04 preflight and accepted runtime remain unchanged. Consult the
review for pinned fork sources, already merged contributions and scoped PR
requests before trying a community port on a separate test machine.

## ARM VPS (issue #12)

The reported Oracle VPS uses an aarch64 Neoverse-N1 CPU. The Ubuntu version and
GNOME version alone do not make it compatible. The approved UU Windows
executables, compatibility DLLs, and pinned Windows FreeRDP client are x86-64.
Installing ARM Wine or an x86-64 cross-compiler does not execute those binaries
on an ARM CPU. An x86 VM requires CPU emulation on this host, not merely a
different virtual-machine image.

Box64/FEX or full-system x86 emulation would be a separate experimental port,
not a supported install switch. It would need evidence for Wine services, DLL
injection, video, audio-null negotiation, GNOME capture, mouse, physical keys,
IME/dictation, clipboard, terminal, reconnect, and cold-start behavior. No such
ARM end-to-end result is currently established here. Removing the architecture
guard would only defer the failure until after packages or services changed.

Use an x86-64 Ubuntu host for this bridge, or use a desktop-sharing service
built for ARM with authenticated SSH/VPN access. Keep any VNC/RDP listener
private; a public cloud desktop must not expose an unauthenticated listener.
Do not upload account state, binaries, or raw logs to a compatibility issue.
