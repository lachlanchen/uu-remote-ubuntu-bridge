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
