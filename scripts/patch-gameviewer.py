#!/usr/bin/env python3
"""Apply, verify, query, or restore approved UU release manifests."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Sequence

from gameviewer_patchlib import (
    ManifestError,
    ReleaseManifest,
    atomic_write,
    classify,
    load_manifests,
    make_patched,
    manifest_value,
    sha256,
    verify_signatures,
)


class PatchError(RuntimeError):
    pass


def selected_manifests(paths: Sequence[Path] | None) -> tuple[ReleaseManifest, ...]:
    return load_manifests(paths)


def classify_or_error(
    data: bytes, manifests: Sequence[ReleaseManifest], target: Path
) -> tuple[str, ReleaseManifest]:
    state, manifest = classify(data, manifests)
    if manifest is None:
        raise PatchError(
            f"unsupported executable ({sha256(data)}): {target}; "
            "run scripts/audit-gameviewer.py inspect for a new release"
        )
    return state, manifest


def patch_file(
    target: Path, backup: Path, manifests: Sequence[ReleaseManifest]
) -> None:
    data = target.read_bytes()
    state, manifest = classify_or_error(data, manifests, target)
    if state == "patched":
        verify_signatures(data, manifest, patched=True)
        print(f"already patched ({manifest.version}): {target}")
        return

    verify_signatures(data, manifest, patched=False)
    if backup.exists():
        backup_data = backup.read_bytes()
        backup_state, backup_manifest = classify_or_error(
            backup_data, manifests, backup
        )
        if backup_state != "original" or backup_manifest != manifest:
            raise PatchError(f"existing backup is not the matching original: {backup}")
        verify_signatures(backup_data, backup_manifest, patched=False)
    else:
        shutil.copy2(target, backup)
        copied_state, copied_manifest = classify_or_error(
            backup.read_bytes(), manifests, backup
        )
        if copied_state != "original" or copied_manifest != manifest:
            raise PatchError(f"new backup verification failed: {backup}")

    atomic_write(target, make_patched(data, manifest), target.stat().st_mode)
    print(f"patched ({manifest.version}): {target}")
    print(f"backup: {backup}")


def restore_file(
    target: Path, backup: Path, manifests: Sequence[ReleaseManifest]
) -> None:
    if not backup.exists():
        raise PatchError(f"backup does not exist: {backup}")
    data = backup.read_bytes()
    state, manifest = classify_or_error(data, manifests, backup)
    if state != "original":
        raise PatchError(f"backup is not an approved original: {backup}")
    verify_signatures(data, manifest, patched=False)
    if target.exists():
        target_state, target_manifest = classify_or_error(
            target.read_bytes(), manifests, target
        )
        if target_manifest != manifest or target_state not in ("original", "patched"):
            raise PatchError(f"target does not match the backup release: {target}")
        mode = target.stat().st_mode
    else:
        mode = backup.stat().st_mode
    atomic_write(target, data, mode)
    print(f"restored ({manifest.version}): {target}")


def verify_file(
    target: Path,
    manifests: Sequence[ReleaseManifest],
    expected: str,
) -> None:
    data = target.read_bytes()
    state, manifest = classify_or_error(data, manifests, target)
    if expected != "either" and state != expected:
        raise PatchError(f"expected {expected} state; found {state}: {target}")
    verify_signatures(data, manifest, patched=state == "patched")
    print(f"{state} ({manifest.version}): {target}")
    print(f"sha256: {sha256(data)}")


def status_file(target: Path, manifests: Sequence[ReleaseManifest]) -> None:
    data = target.read_bytes()
    state, manifest = classify(data, manifests)
    if manifest is None:
        print(f"unknown ({sha256(data)})")
    else:
        print(f"{state} ({manifest.version})")


def add_manifest_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--manifest",
        type=Path,
        action="append",
        help="approved release manifest; repeat to allow multiple versions",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("patch", "verify", "status", "restore"):
        child = subparsers.add_parser(command)
        child.add_argument("target", type=Path)
        add_manifest_option(child)
        if command in ("patch", "restore"):
            child.add_argument(
                "--backup",
                type=Path,
                help="backup path (default: TARGET.uu-original)",
            )
        if command == "verify":
            child.add_argument(
                "--expect",
                choices=("original", "patched", "either"),
                default="either",
                help="required binary state (default: either)",
            )

    manifests_parser = subparsers.add_parser(
        "manifests", help="list approved manifests"
    )
    add_manifest_option(manifests_parser)

    field_parser = subparsers.add_parser(
        "field", help="print one scalar manifest field"
    )
    field_parser.add_argument("field")
    field_parser.add_argument("--manifest", type=Path, required=True)
    return parser.parse_args()


def resolve_target(path: Path) -> Path:
    return path.expanduser().resolve()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "field":
            manifests = selected_manifests([args.manifest])
            print(manifest_value(manifests[0], args.field))
            return 0

        manifests = selected_manifests(args.manifest)
        if args.command == "manifests":
            for manifest in manifests:
                print(
                    f"{manifest.version}\t{manifest.architecture}\t"
                    f"{manifest.path}"
                )
            return 0

        target = resolve_target(args.target)
        backup = (
            resolve_target(args.backup)
            if getattr(args, "backup", None)
            else target.with_name(f"{target.name}.uu-original")
        )
        if args.command == "patch":
            patch_file(target, backup, manifests)
        elif args.command == "restore":
            restore_file(target, backup, manifests)
        elif args.command == "status":
            status_file(target, manifests)
        else:
            verify_file(target, manifests, args.expect)
    except (OSError, ManifestError, PatchError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
