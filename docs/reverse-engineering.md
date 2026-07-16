# Reverse-engineering record

This document records the reproducible analysis behind the 4.33.0.8907
compatibility patch. Addresses and bytes must not be reused for another UU
release without a new audit.

The machine-readable source of truth is
`patches/uu-remote-4.33.0.8907.json`. For a new version, follow
`docs/upstream-maintenance.md`; the generic patcher refuses unknown hashes and
unapproved draft manifests.

## Audited files

```text
UU installer 4.33.0.8907
5e3cfe8cfdc6552c1fc26f1ad2c94df133ca20dc3c45c23155358c32ac9bf53e

GameViewerServer.exe, upstream
be1c6c108e6e4d0d5cc15dcd22650dc5fde34c7e7b9f19eee72aba0160ea3494

GameViewerServer.exe, patched
30cad61560213c7a66244c6f79c9017cc9dfa81996d7faa15a0e8bf330aa0948

GameViewerHealthd.exe, upstream
ba4cdef465b3714940b154d6d40d7cfca4d65c3d639a6254bb0fb7be69bd19e6
```

The upstream executables were retained with the suffix `.uu-original` before
any modification.

## Windows reference behavior

The same UU release was inspected on a real Windows 11 host. A healthy host
reported a signed root HID device, a HID keyboard collection, and:

```text
virtual switch state:1
input_device_count:1 keyboard_device_count:1
input_driver_installed:1
```

Wine enumerated more than 100 duplicate synthetic HID/mouse descriptions,
reported no keyboard device, and could not install `gvinput.sys`:

```text
input_device_count:127 keyboard_device_count:0
input_driver_installed:0
```

The goal was therefore to select UU's existing user-mode input path, not to
emulate or weaken a Windows kernel driver.

## String and cross-reference search

GNU binutils were used directly on the PE file:

```bash
server='GameViewerServer.exe.uu-original'

strings -a -t x "$server" | \
  rg 'virtual switch state:|set_virtual_mouse_switch|read setting read_user_setting:'

x86_64-w64-mingw32-objdump -h "$server"
x86_64-w64-mingw32-objdump -d -M intel "$server" > server.objdump
rg -n '14154e2f0|set_virtual_mouse_switch' server.objdump
```

Relevant string file offsets were:

```text
01543b10 read setting read_user_setting:...
01543b40 set_virtual_mouse_switch function label
01543b90 set_virtual_mouse_switch log text
0154d2f0 virtual switch state
```

`.rdata` begins at file offset `0x1531000` and virtual address
`0x141532000`, so the last string maps to VA `0x14154e2f0`. Its code
cross-reference is at VA `0x1402305cd`.

Targeted disassembly was then kept small enough to inspect:

```bash
x86_64-w64-mingw32-objdump -d -M intel \
  --start-address=0x140230280 --stop-address=0x140230980 "$server"

x86_64-w64-mingw32-objdump -d -M intel \
  --start-address=0x1401dc640 --stop-address=0x1401dc930 "$server"
```

The latter VA range includes file offsets `0x1dbaae` and `0x1dbcb2` after
mapping `.text` raw offset to its aligned RVA. An earlier hand-written range
omitted that section-alignment delta; the manifest offsets and patch bytes were
always file offsets and are unchanged.

## Byte inspection

The exact bytes were captured before patching:

```bash
xxd -g 1 -s 0x22f700 -l 64 "$server"
xxd -g 1 -s 0x22f8f0 -l 48 "$server"
xxd -g 1 -s 0x1dbaa0 -l 48 "$server"
xxd -g 1 -s 0x1dbca0 -l 48 "$server"
```

Relevant output:

```text
0022f710: 00 01 00 c7 86 e0 01 00 00 00 01 00 00 88 86 e4
0022f900: ff e8 c9 10 e0 ff 0f b6 08 88 8d 38 01 00 00 48
001dbab0: f5 e5 ff 83 fb 02 0f 94 c0 88 07 48 8d 05 06 84
001dbcb0: 01 cc e8 62 f3 e5 ff 40 88 37 48 8d 05 7f 82 36
```

At VA `0x140230313`, the constructor contains:

```text
c7 86 e0 01 00 00 00 01 00 00
```

This writes DWORD `0x100` at object offset `0x1e0`, making the byte at
`0x1e1` true. That byte is the startup virtual-input switch.

## Patch table

All four changes force the normal `SendInput` path and leave the surrounding
control flow intact.

| File offset | Upstream bytes | Replacement | Purpose |
| --- | --- | --- | --- |
| `0x22f719` | `00 01 00 00` | `00 00 00 00` | Constructor default false |
| `0x22f906` | `0f b6 08` | `31 c9 90` | Constructor setting false |
| `0x1dbab6` | `0f 94 c0` | `31 c0 90` | Read setting returns false |
| `0x1dbcb7` | `40 88 37` | `c6 07 00` | Runtime setter stores false |

After patching, the server log changed to:

```text
virtual switch state:0
```

`scripts/patch-gameviewer.py` does not search for three-byte fragments. It
checks longer unique signatures, their expected offsets, the complete input
hash, and the complete output hash. These checks are now loaded from an
approved release manifest so future audited versions can be added without
editing patch-engine code.

## Input-token failure

A separate Windows test executable proved that ordinary `SetCursorPos` and
`SendInput` could traverse Wine, SDL FreeRDP, GNOME RDP, and the live desktop.
The same call from GameViewerServer failed:

```text
count=1 type=0 flags=0x00000001 result=0 error=5
```

Error 5 is `ERROR_ACCESS_DENIED`. GameViewerService creates the server through
`CreateProcessAsUser` after attempting `TokenUIAccess`; Wine rejects that token
for input injection. This is why changing only the virtual-input switch still
caused the controller to disconnect on its first click.

The IAT hook now calls the original function first. On failure it sends the
bounded `INPUT` array to a normal Wine user process. The validated result was:

```text
route=broker result=1 error=0
```

Mouse clicks no longer disconnected UU. Keyboard events typed a shell command
through a Windows UU controller and created `/tmp/uu-broker-ok` on Ubuntu.

## Four-minute process abort

The original health monitor repeatedly logged that the main loop was not
responding under Wine. Replacing it with a sleeping process stopped that false
kill path, but GameViewerServer still exited every four minutes. Wine stderr
showed the direct cause:

```text
wine: Call from ... to unimplemented function
wevtapi.dll.EvtOpenPublisherMetadata, aborting
```

The server imports these event-log functions:

```bash
x86_64-w64-mingw32-objdump -p "$server" | \
  rg -C 3 'wevtapi|Evt[A-Z]'
```

```text
EvtQuery
EvtNext
EvtRender
EvtOpenPublisherMetadata
EvtClose
```

The injected DLL patches only the `EvtOpenPublisherMetadata` IAT slot and
returns null with `ERROR_EVT_PUBLISHER_METADATA_NOT_FOUND` (15002). The caller
already handles that documented API failure. The same server PID then survived
beyond the former four-minute interval.

## FreeRDP and NLA

The Windows SDL FreeRDP client rendered reliably in the same Wine/X display,
but Wine's SSPI handle representation did not satisfy its NLA path. The
solution was:

1. Build `libwinpr3.dll` from pinned FreeRDP 3.30.0 source with MinGW.
2. Enable WinPR's internal MD4, MD5, and RC4 implementations. Wine could not
   reliably load OpenSSL's legacy provider, and NTLM requires MD4.
3. Disable native SSPI so the shim always reaches WinPR's implementation.
4. Supply pinned MSYS2 OpenSSL, cJSON, and uriparser runtime DLLs.
5. Load `winpr-sspi-shim.dll` with FreeRDP's `/sspi-module` option and request
   `none,ntlm` with `/auth-pkg-list`.

The shim calls WinPR's `InitSecurityInterfaceExA/W` and normalizes the private
credential/context handle-name field around `AcquireCredentialsHandle` and
`InitializeSecurityContext`.

## Tools used

The investigation used `rg`, `strings`, `xxd`, `sha256sum`, GNU
`objdump`, MinGW GCC/binutils, `file`, `7z`, Wine task/process tools, UU logs,
GNOME RDP logs, `xdotool`, `scrot`, and a real Windows UU installation as a
behavioral reference. Temporary capture and SendInput test binaries are not
part of the repository.

`scripts/audit-gameviewer.py` now reproduces the PE section mapping, landmark
search, masked-signature candidate scan, and targeted disassembly report. Its
output is a draft only; semantic review remains mandatory.
