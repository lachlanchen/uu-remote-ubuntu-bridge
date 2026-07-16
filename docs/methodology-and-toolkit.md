# Methodology and Toolkit

This document records how the Ubuntu control bridge was solved and which parts
of the process generalize to other compatibility problems.

## Start from observable behavior

The initial Wine installation produced useful video but not a usable Linux
host. The investigation separated symptoms instead of treating "UU under
Wine" as one failure:

| Plane | Symptom | Independent proof |
| --- | --- | --- |
| Account/signaling | Device could be offline | UU client/server logs and account bootstrap IPC |
| Capture | Black or stale video | Xvfb screenshots and relay-window inspection |
| Input policy | First click disconnected | UU virtual-switch and driver-state logs |
| Input execution | `SendInput` returned error 5 | Minimal Windows probe and injected-call logging |
| Lifecycle | Server died near four minutes | Stable PID timing, health logs, and Wine stderr |
| RDP authentication | NLA looped | FreeRDP/WinPR SSPI logs and controlled rebuilds |

This decomposition prevented one successful hop from being mistaken for an
end-to-end solution.

## Establish a known-good reference

The same UU release was inspected on Windows 11 through existing authorized
RDP and SSH access. Read-only PowerShell queries and UU logs established that
Windows had a signed root HID device, a keyboard collection, and the kernel
input switch enabled. Wine had duplicate synthetic HID descriptions, no UU
keyboard, and no usable `gvinput.sys` driver.

That comparison changed the question from "how do we emulate a kernel driver"
to "does UU already have a user-mode fallback?" The answer was yes.

## Build narrow probes

Small throwaway Windows programs answered one question at a time:

- Can a normal Wine process call `SendInput` into SDL FreeRDP?
- Can it set focus and move the pointer?
- Does the same call fail only from GameViewerServer's service token?
- Can a Windows window render reliably under Xvfb software graphics?

The probes were removed after their results were incorporated into source,
tests, and documentation. Keeping experimental binaries out of Git avoids
confusing evidence with product code.

## Trace logs before changing bytes

`rg` reduced large UU, Wine, GNOME, and FreeRDP logs to state transitions and
error codes. Relevant messages were correlated with process IDs and elapsed
time. This identified three separate causes:

1. UU selected an unavailable kernel-input path.
2. Wine denied `SendInput` from the service-created token.
3. Wine aborted an unimplemented event-log call after the health path was
   already stabilized.

Each cause received one bounded compatibility mechanism. No broad API bypass
was added.

## Reverse-engineer with multiple coordinate systems

PE analysis requires keeping these coordinates distinct:

- file offset, used by `xxd` and the patch manifest
- RVA, relative to the PE image base
- VA, printed by `objdump`
- section raw offset and virtual address, which can differ by alignment

The audit tool parses PE section headers and converts file offsets to VAs. This
re-audit caught an old hand-written VA range that omitted `.text` alignment.

The binary workflow was:

1. `strings -a -t x` for semantic landmarks.
2. `objdump -h` for file/RVA section mapping.
3. `objdump -d -M intel` for targeted control flow.
4. `xxd -g 1` for exact pre-patch bytes.
5. `sha256sum` for complete original and patched identity.
6. Longer unique signatures around each instruction edit.

The four edits were not selected by byte pattern alone; their meaning was
established from cross-references, object-field writes, logs, and Windows
behavior.

## Adapt at API boundaries

The final bridge uses small adapters at stable interfaces:

- an IAT hook selects the existing `SendInput` call boundary
- a bounded named-pipe broker changes only the Wine token context
- a one-function event-log hook returns a documented Windows error
- an SSPI shim normalizes private WinPR handle representation
- SDL FreeRDP provides a normal capturable Windows window
- GNOME Remote Desktop owns GNOME session capture and input

This is more maintainable than emulating UU's kernel driver or inventing a new
desktop input stack.

## Make lifecycle behavior explicit

The upstream health monitor interpreted Wine behavior as a hang, while Wine's
event-log stub aborted the server independently. Replacing only one appeared
to help but did not cross the four-minute boundary. A timed same-PID test made
the remaining failure visible.

Systemd now owns the complete relay lifecycle, and an inner supervisor handles
UU replacing its server process. The verifier checks both static identities
and live process behavior.

## Tool inventory

| Tool | Purpose in this work |
| --- | --- |
| `rg` | Fast source, string, and multi-log correlation |
| `strings` | Semantic landmarks with file offsets |
| `xxd` | Exact byte capture around patch sites |
| MinGW `objdump` | PE sections, imports, and Intel disassembly |
| `sha256sum` | Full artifact identity and fail-closed allowlists |
| Python `struct` | Independent PE section and VA mapping |
| MinGW GCC/binutils | Build injected DLLs and Windows helpers |
| Wine/WineGCC | Run UU and provide the fake Winlogon process shape |
| Xvfb/Openbox | Private, deterministic Windows capture desktop |
| `xdotool`/`xauth` | Window focus checks and protected X11 access |
| SDL FreeRDP/WinPR | Windows RDP relay into the live GNOME session |
| GNOME Remote Desktop | Supported GNOME capture and input endpoint |
| `grdctl`/`gsettings` | Configure and inspect GNOME RDP |
| `secret-tool` | Keep the relay password in GNOME Keyring |
| `systemd-creds`/TPM2 | Bind unattended keyring unlock to this machine |
| Secret Service D-Bus | Unlock the login collection without a GUI prompt |
| `crudini` | Make reversible, scoped GDM INI changes |
| systemd user units | Restart and supervise the live bridge |
| systemd transient sandbox | Stage an installer with host/network isolation |
| `7z` | Non-executing installer extraction attempt |
| Windows OpenSSH/PowerShell | Read-only known-good reference inspection |
| Git/`gh` | Version, publish, and preserve the reproducible record |

## Source and artifact map

| Artifact | Responsibility |
| --- | --- |
| `patches/*.json` | Approved release identities and byte edits |
| `gameviewer_patchlib.py` | Shared validation, matching, and patch primitives |
| `patch-gameviewer.py` | Patch/verify/status/restore CLI |
| `stage-uu-release.sh` | Private staging without touching the live prefix |
| `audit-gameviewer.py` | PE report, candidate discovery, and approval gate |
| `uu_input_bridge.c` | `SendInput` and event-log IAT hooks |
| `uu_input_broker.c` | Bounded normal-token input execution |
| `uu_injector.c` | Controlled DLL injection into the UU server |
| `winpr_sspi_shim.c` | FreeRDP NLA compatibility |
| `uu-remote-bridge` | X/RDP/UU orchestration and supervision |
| `configure-unattended.sh` | GDM, TPM credential, unit, and rollback setup |
| `uu-keyring-unlock.py` | Bounded login-keyring unlock over session D-Bus |
| `install.sh` | Idempotent dependency-to-service deployment |
| `verify.sh` | Static, process, input, and stability evidence |

Compiled binaries, staged installers, prefixes, logs, screenshots, and audit
disassembly remain under ignored paths or user runtime state.

## Reusable engineering habits

1. Reproduce before modifying.
2. Split the path into independently testable hops.
3. Compare with a known-good implementation.
4. Use minimal probes to answer binary questions.
5. Prefer supported boundaries over deep emulation.
6. Make every binary assumption a hash plus a semantic record.
7. Fail closed on ambiguity.
8. Preserve byte-identical rollback artifacts.
9. Test elapsed-time and restart behavior, not just startup.
10. Convert discoveries into code, tests, and operational documentation.
11. Test implicit login dependencies, not only the final application process.

These habits are the reusable result. The current four byte edits are only one
version-specific application of them.
