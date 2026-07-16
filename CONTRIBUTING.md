# Contributing

This project modifies version-locked behavior in proprietary software. Treat a
new hash as a new reverse-engineering review, not a routine dependency bump.

## Normal source changes

Run before committing:

```bash
while IFS= read -r file; do bash -n "$file" || exit; done < <(
  find . -type f -name '*.sh' -print
)
python3 -m unittest discover -s tests -v
scripts/build-compat.sh
scripts/verify.sh --quick
./uninstall.sh --dry-run
git diff --check
```

Do not commit anything ignored under `build/` or anything from the Wine
prefix. Search the staged diff for passwords, tokens, device IDs, hostnames,
IP addresses, screenshots, and raw UU logs.

## New UU releases

Follow [Maintaining the bridge across UU updates](docs/upstream-maintenance.md).
A release contribution must include:

- a new approved manifest under `patches/`
- the installer, server, patched-server, and health-monitor SHA-256 values
- semantic rationale for every same-length edit
- updated reverse-engineering notes and changed imports/landmarks
- proof of disposable patch/verify/restore
- mouse, keyboard, reconnect, restart, and 270-second runtime results
- verified uninstall restoration

Do not include NetEase binaries, disassembly dumps, Wine state, or account
metadata. Keep private audit output under `build/audits/`.

## Patch quality

- Keep hooks narrow and return real API result/error shapes.
- Bound every cross-process request before reading payload data.
- Do not log key codes, Unicode data, pointer coordinates, or clipboard data.
- Avoid weakening authentication, TLS verification, manifest approval, or
  complete-hash checks.
- Preserve user-level operation and reversible removal.
