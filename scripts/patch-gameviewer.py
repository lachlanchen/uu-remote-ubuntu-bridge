#!/usr/bin/env python3
"""Version-locked, reversible patcher for UU Remote 4.33.0.8907."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


ORIGINAL_SHA256 = "be1c6c108e6e4d0d5cc15dcd22650dc5fde34c7e7b9f19eee72aba0160ea3494"
PATCHED_SHA256 = "30cad61560213c7a66244c6f79c9017cc9dfa81996d7faa15a0e8bf330aa0948"


@dataclass(frozen=True)
class Patch:
    name: str
    offset: int
    original: bytes
    replacement: bytes


PATCHES = (
    Patch(
        "constructor virtual-input default",
        0x22F713,
        bytes.fromhex("c786e0010000000100008886e4010000"),
        bytes.fromhex("c786e0010000000000008886e4010000"),
    ),
    Patch(
        "constructor virtual-input setting",
        0x22F901,
        bytes.fromhex("e8c910e0ff0fb608888d38010000488d"),
        bytes.fromhex("e8c910e0ff31c990888d38010000488d"),
    ),
    Patch(
        "read_user_setting virtual-input result",
        0x1DBAAE,
        bytes.fromhex("e866f5e5ff83fb020f94c08807488d0506843601"),
        bytes.fromhex("e866f5e5ff83fb0231c0908807488d0506843601"),
    ),
    Patch(
        "runtime virtual-input setter",
        0x1DBCB2,
        bytes.fromhex("e862f3e5ff408837488d"),
        bytes.fromhex("e862f3e5ffc60700488d"),
    ),
)


class PatchError(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def classify(data: bytes) -> str:
    digest = sha256(data)
    if digest == ORIGINAL_SHA256:
        return "original"
    if digest == PATCHED_SHA256:
        return "patched"
    return f"unknown ({digest})"


def verify_signatures(data: bytes, patched: bool) -> None:
    for item in PATCHES:
        expected = item.replacement if patched else item.original
        first = data.find(expected)
        second = data.find(expected, first + 1) if first >= 0 else -1
        if first != item.offset or second >= 0:
            found = [offset for offset in (first, second) if offset >= 0]
            rendered = ", ".join(hex(offset) for offset in found) or "none"
            raise PatchError(
                f"{item.name}: expected one signature at {item.offset:#x}; "
                f"found {rendered}"
            )


def make_patched(original: bytes) -> bytes:
    if sha256(original) != ORIGINAL_SHA256:
        raise PatchError("input is not the audited upstream executable")
    verify_signatures(original, patched=False)

    output = bytearray(original)
    for item in PATCHES:
        end = item.offset + len(item.original)
        output[item.offset:end] = item.replacement

    result = bytes(output)
    if sha256(result) != PATCHED_SHA256:
        raise PatchError("patched output hash does not match the audited result")
    verify_signatures(result, patched=True)
    return result


def atomic_write(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, stat.S_IMODE(mode))
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def patch_file(target: Path, backup: Path) -> None:
    data = target.read_bytes()
    state = classify(data)
    if state == "patched":
        verify_signatures(data, patched=True)
        print(f"already patched: {target}")
        return
    if state != "original":
        raise PatchError(f"refusing to patch {state} executable: {target}")

    if backup.exists():
        backup_data = backup.read_bytes()
        if sha256(backup_data) != ORIGINAL_SHA256:
            raise PatchError(f"existing backup is not the audited original: {backup}")
    else:
        shutil.copy2(target, backup)

    atomic_write(target, make_patched(data), target.stat().st_mode)
    print(f"patched: {target}")
    print(f"backup:  {backup}")


def restore_file(target: Path, backup: Path) -> None:
    if not backup.exists():
        raise PatchError(f"backup does not exist: {backup}")
    data = backup.read_bytes()
    if sha256(data) != ORIGINAL_SHA256:
        raise PatchError(f"backup is not the audited original: {backup}")
    mode = target.stat().st_mode if target.exists() else backup.stat().st_mode
    atomic_write(target, data, mode)
    print(f"restored: {target}")


def verify_file(target: Path) -> None:
    data = target.read_bytes()
    state = classify(data)
    if state == "original":
        verify_signatures(data, patched=False)
    elif state == "patched":
        verify_signatures(data, patched=True)
    else:
        raise PatchError(f"unsupported executable: {state}")
    print(f"{state}: {target}")
    print(f"sha256: {sha256(data)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("patch", "verify", "status", "restore"))
    parser.add_argument("target", type=Path)
    parser.add_argument(
        "--backup",
        type=Path,
        help="backup path (default: TARGET.uu-original)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target = args.target.expanduser().resolve()
    backup = (
        args.backup.expanduser().resolve()
        if args.backup
        else target.with_name(f"{target.name}.uu-original")
    )
    try:
        if args.command == "patch":
            patch_file(target, backup)
        elif args.command == "restore":
            restore_file(target, backup)
        elif args.command == "status":
            print(classify(target.read_bytes()))
        else:
            verify_file(target)
    except (OSError, PatchError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
