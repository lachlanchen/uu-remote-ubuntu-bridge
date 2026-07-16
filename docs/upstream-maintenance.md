# Maintaining the Bridge Across UU Updates

This is the repeatable "how to fish" workflow for a new UU release. It
automates collection, comparison, patch packaging, and verification while
keeping the semantic decision in human review.

Do not make the patcher accept an unknown hash just to get past an update. A
compiler can preserve similar bytes while changing object layout, branch
meaning, or calling conventions. Candidate discovery is evidence, not proof.

## Safety invariants

Every runnable release manifest must prove all of these facts:

1. The unmodified server has one exact SHA-256 and size.
2. Every complete original signature occurs once at its declared file offset.
3. Original and replacement signatures have equal lengths.
4. Patch regions do not overlap.
5. The complete patched result has a precomputed SHA-256.
6. The manifest is explicitly marked `approved` after disassembly review.
7. Installer and health-monitor hashes are recorded for the same release.

`patch-gameviewer.py` enforces these invariants and rejects draft manifests.
The installer copies its selected manifest into the Wine prefix so verify and
uninstall use the exact same release definition.

## 1. Preserve the current baseline

Start from a clean repository and a healthy bridge:

```bash
git status -sb
scripts/verify.sh --quick
python3 -m unittest discover -s tests -v
```

Never edit the existing approved manifest for a different upstream binary.
Add a new file under `patches/` so old installations remain recoverable.

## 2. Acquire and stage the new release

Download the installer from NetEase's official endpoint and retain its full
hash. Try archive extraction first; this never executes vendor code:

```bash
scripts/stage-uu-release.sh \
  --installer ~/Downloads/UU-Remote/uuyc_NEW.exe
```

Some UU installer wrappers do not expose their payload to `7z`. In that case,
use the explicit sandbox fallback:

```bash
scripts/stage-uu-release.sh \
  --installer ~/Downloads/UU-Remote/uuyc_NEW.exe \
  --sandbox-install
```

The fallback asks for `sudo` before starting a transient system service. That
service runs Wine as the desktop UID with:

- a read-only host filesystem
- the real home hidden by `ProtectHome=tmpfs`
- only the installer mounted read-only and the staging directory writable
- `PrivateNetwork=yes`, `IPAddressDeny=any`, and no Internet socket families
- private temporary files and devices
- no-new-privileges and kernel/control-group protections

The disposable prefix is deleted after the two analysis binaries are copied.
Use `--keep-workdir` only when the installation layout itself needs review.
For stronger isolation, stage an unknown installer in a separate VM and pass
the extracted binaries directly to the audit tool.

All staged files stay under ignored `build/upstream/`; never commit them.

## 3. Generate an audit, not a patch

Use the latest approved release as a behavioral baseline:

```bash
scripts/audit-gameviewer.py inspect \
  --server build/upstream/NEW/GameViewerServer.exe \
  --healthd build/upstream/NEW/GameViewerHealthd.exe \
  --installer ~/Downloads/UU-Remote/uuyc_NEW.exe \
  --baseline patches/uu-remote-4.33.0.8907.json \
  --version NEW_VERSION
```

The generated private audit directory contains:

- `REPORT.md`: identity, landmarks, candidates, and review checklist
- `audit.json`: machine-readable PE sections, offsets, VAs, and candidates
- `draft-manifest.json`: deliberately non-runnable proposed release data
- `objdump-headers.txt`: PE imports and headers
- `strings.txt`: offset-annotated static strings
- `disassembly/*.txt`: small candidate windows in Intel syntax

The candidate finder masks only bytes changed by the old patch and anchors on
the longest unchanged context. It reports zero, one, or many matches. It never
writes to the executable and never marks a candidate reviewed.

## 4. Re-establish semantics

For every target, repeat the reasoning instead of trusting the old offset:

1. Compare the new release on a real Windows host.
2. Record input-driver state, virtual-switch logs, process lifecycle, and
   relevant imports without copying account/device metadata.
3. Find the new semantic string and its code cross-references.
4. Inspect the complete containing function, callers, and writes to the target
   object field.
5. Confirm instruction boundaries and stack/register behavior.
6. Design a same-length replacement with the smallest behavioral change.
7. Capture generous unique original and replacement signatures.

Useful direct commands are:

```bash
strings -a -t x GameViewerServer.exe | \
  rg 'virtual switch state:|set_virtual_mouse_switch|read_user_setting'

x86_64-w64-mingw32-objdump -h GameViewerServer.exe
x86_64-w64-mingw32-objdump -p GameViewerServer.exe | \
  rg -C 3 'SendInput|wevtapi|Evt[A-Z]'

x86_64-w64-mingw32-objdump -d -M intel \
  --start-address=START_VA --stop-address=STOP_VA \
  GameViewerServer.exe

xxd -g 1 -s FILE_OFFSET -l LENGTH GameViewerServer.exe
```

Edit the private draft only after this review. Set each
`candidate_status` from `unreviewed` to `reviewed` and correct its offset,
original bytes, replacement bytes, description, and rationale. A missing or
ambiguous candidate must be resolved manually; do not pick the nearest match.

## 5. Finalize the reviewed manifest

Finalization is an explicit gate. It recomputes the original identity, applies
the reviewed signatures in memory, derives the full patched hash, validates
the approved schema, and still does not modify a binary:

```bash
scripts/audit-gameviewer.py finalize \
  --server build/upstream/NEW/GameViewerServer.exe \
  --draft build/audits/NEW/draft-manifest.json \
  --output patches/uu-remote-NEW_VERSION.json \
  --reviewed-by 'reviewer name' \
  --review-note 'Windows comparison, disassembly report, and test reference' \
  --accept-reviewed-disassembly
```

The tool refuses placeholders, unreviewed candidates, an unexpected server
hash, malformed or overlapping signatures, and an existing output file.

## 6. Test a disposable copy

Never make the first patch attempt against the installed server:

```bash
cp build/upstream/NEW/GameViewerServer.exe build/upstream/NEW/server-test.exe

scripts/patch-gameviewer.py patch \
  build/upstream/NEW/server-test.exe \
  --manifest patches/uu-remote-NEW_VERSION.json

scripts/patch-gameviewer.py verify \
  build/upstream/NEW/server-test.exe \
  --manifest patches/uu-remote-NEW_VERSION.json

scripts/patch-gameviewer.py restore \
  build/upstream/NEW/server-test.exe \
  --manifest patches/uu-remote-NEW_VERSION.json

cmp build/upstream/NEW/server-test.exe \
  build/upstream/NEW/server-test.exe.uu-original
```

Also run the synthetic manifest tests:

```bash
python3 -m unittest discover -s tests -v
```

## 7. Validate the complete bridge

Only after copy testing should the new manifest reach a disposable UU prefix:

```bash
./install.sh \
  --release-manifest patches/uu-remote-NEW_VERSION.json \
  --uu-installer ~/Downloads/UU-Remote/uuyc_NEW.exe
```

Validate all user-visible behavior, not only a successful patch command:

1. UU reports the Ubuntu device online.
2. The real GNOME desktop renders at the intended resolution.
3. Mouse motion, buttons, wheel, and drag work without a forced disconnect.
4. Printable keys, modifiers, shortcuts, and key-up events work.
5. Clipboard behavior matches the configured policy.
6. Disconnect/reconnect and service restart recover automatically.
7. The server PID survives at least 270 seconds.
8. `scripts/verify.sh` passes.
9. `./uninstall.sh --dry-run` validates both rollback backups.
10. `./uninstall.sh` restores byte-identical audited originals.

Keep controller-side proof free of passwords and personal desktop content.

## When the old approach no longer applies

Stop and redesign instead of forcing a manifest when any of these changes:

- the virtual-switch strings or field no longer exist
- UU removes its user-mode `SendInput` path
- input moves to a new process or IPC protocol
- the service token no longer triggers error 5
- event-log imports or health monitoring change
- capture no longer targets an ordinary desktop window
- the new installer requires network access inside staging

The manifest system makes updates cheaper, not automatic. Its purpose is to
make every assumption visible, reproducible, reviewable, and reversible.
