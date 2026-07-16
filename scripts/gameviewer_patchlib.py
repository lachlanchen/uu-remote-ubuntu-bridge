#!/usr/bin/env python3
"""Shared, fail-closed primitives for UU release manifests and binary patches."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REPO_DIR = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST_DIR = REPO_DIR / "patches"


class ManifestError(RuntimeError):
    """A release manifest is malformed, ambiguous, or not approved."""


@dataclass(frozen=True)
class Patch:
    patch_id: str
    description: str
    rationale: str
    file_offset: int
    original: bytes
    replacement: bytes


@dataclass(frozen=True)
class ReleaseManifest:
    path: Path
    raw: Mapping[str, Any]
    version: str
    architecture: str
    review_status: str
    installer_filename: str
    installer_url: str
    installer_sha256: str
    server_filename: str
    server_size: int
    original_sha256: str
    patched_sha256: str
    healthd_filename: str
    healthd_original_sha256: str
    patches: tuple[Patch, ...]
    landmarks: tuple[str, ...]
    imports: tuple[str, ...]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ManifestError(f"{field} must be an object")
    return value


def _string(mapping: Mapping[str, Any], field: str, prefix: str = "") -> str:
    value = mapping.get(field)
    label = f"{prefix}.{field}" if prefix else field
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{label} must be a non-empty string")
    return value


def _sha256(mapping: Mapping[str, Any], field: str, prefix: str) -> str:
    value = _string(mapping, field, prefix).lower()
    if not SHA256_RE.fullmatch(value):
        raise ManifestError(f"{prefix}.{field} must be 64 lowercase hex digits")
    return value


def _offset(value: Any, field: str) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        result = value
    elif isinstance(value, str):
        try:
            result = int(value, 0)
        except ValueError as error:
            raise ManifestError(f"{field} is not an integer offset") from error
    else:
        raise ManifestError(f"{field} is not an integer offset")
    if result < 0:
        raise ManifestError(f"{field} cannot be negative")
    return result


def _hex_bytes(value: Any, field: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise ManifestError(f"{field} must be a non-empty hexadecimal string")
    try:
        result = bytes.fromhex(value)
    except ValueError as error:
        raise ManifestError(f"{field} contains invalid hexadecimal bytes") from error
    if not result:
        raise ManifestError(f"{field} cannot be empty")
    return result


def _string_list(raw: Mapping[str, Any], field: str) -> tuple[str, ...]:
    value = raw.get(field, [])
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise ManifestError(f"{field} must be a list of non-empty strings")
    if len(value) != len(set(value)):
        raise ManifestError(f"{field} contains duplicates")
    return tuple(value)


def manifest_from_dict(
    raw_value: Any,
    path: Path,
    *,
    require_approved: bool = True,
) -> ReleaseManifest:
    raw = _mapping(raw_value, "manifest")
    if raw.get("schema_version") != 1:
        raise ManifestError("schema_version must be 1")

    review_status = _string(raw, "review_status")
    if require_approved and review_status != "approved":
        raise ManifestError(
            f"{path}: manifest status is {review_status!r}, not 'approved'"
        )

    version = _string(raw, "version")
    architecture = _string(raw, "architecture")
    if architecture != "x86_64":
        raise ManifestError(f"{path}: unsupported architecture {architecture!r}")

    installer = _mapping(raw.get("installer"), "installer")
    server = _mapping(raw.get("server"), "server")
    healthd = _mapping(raw.get("health_monitor"), "health_monitor")
    server_size = server.get("size")
    if not isinstance(server_size, int) or isinstance(server_size, bool) or server_size <= 0:
        raise ManifestError("server.size must be a positive integer")

    patch_values = server.get("patches")
    if not isinstance(patch_values, list) or not patch_values:
        raise ManifestError("server.patches must be a non-empty list")

    patches: list[Patch] = []
    patch_ids: set[str] = set()
    for index, value in enumerate(patch_values):
        item = _mapping(value, f"server.patches[{index}]")
        prefix = f"server.patches[{index}]"
        patch_id = _string(item, "id", prefix)
        if patch_id in patch_ids:
            raise ManifestError(f"duplicate patch id: {patch_id}")
        patch_ids.add(patch_id)
        original = _hex_bytes(item.get("original"), f"{prefix}.original")
        replacement = _hex_bytes(item.get("replacement"), f"{prefix}.replacement")
        if len(original) != len(replacement):
            raise ManifestError(f"{patch_id}: original and replacement lengths differ")
        if original == replacement:
            raise ManifestError(f"{patch_id}: replacement does not change any byte")
        patches.append(
            Patch(
                patch_id=patch_id,
                description=_string(item, "description", prefix),
                rationale=_string(item, "rationale", prefix),
                file_offset=_offset(item.get("file_offset"), f"{prefix}.file_offset"),
                original=original,
                replacement=replacement,
            )
        )

    ordered = sorted(patches, key=lambda item: item.file_offset)
    for left, right in zip(ordered, ordered[1:]):
        if left.file_offset + len(left.original) > right.file_offset:
            raise ManifestError(f"patches overlap: {left.patch_id} and {right.patch_id}")

    original_digest = _sha256(server, "original_sha256", "server")
    patched_digest = _sha256(server, "patched_sha256", "server")
    if original_digest == patched_digest:
        raise ManifestError("server original and patched hashes are identical")

    return ReleaseManifest(
        path=path,
        raw=raw,
        version=version,
        architecture=architecture,
        review_status=review_status,
        installer_filename=_string(installer, "filename", "installer"),
        installer_url=_string(installer, "url", "installer"),
        installer_sha256=_sha256(installer, "sha256", "installer"),
        server_filename=_string(server, "filename", "server"),
        server_size=server_size,
        original_sha256=original_digest,
        patched_sha256=patched_digest,
        healthd_filename=_string(healthd, "filename", "health_monitor"),
        healthd_original_sha256=_sha256(
            healthd, "original_sha256", "health_monitor"
        ),
        patches=tuple(patches),
        landmarks=_string_list(raw, "landmarks"),
        imports=_string_list(raw, "imports"),
    )


def load_manifest(path: Path, *, require_approved: bool = True) -> ReleaseManifest:
    resolved = path.expanduser().resolve()
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ManifestError(f"could not read manifest {resolved}: {error}") from error
    return manifest_from_dict(raw, resolved, require_approved=require_approved)


def load_manifests(paths: Sequence[Path] | None = None) -> tuple[ReleaseManifest, ...]:
    selected = (
        [path.expanduser().resolve() for path in paths]
        if paths
        else sorted(DEFAULT_MANIFEST_DIR.glob("*.json"))
    )
    if not selected:
        raise ManifestError("no approved release manifests were found")

    manifests = tuple(load_manifest(path) for path in selected)
    versions: set[str] = set()
    digests: set[str] = set()
    for manifest in manifests:
        if manifest.version in versions:
            raise ManifestError(f"duplicate release version: {manifest.version}")
        versions.add(manifest.version)
        for digest in (manifest.original_sha256, manifest.patched_sha256):
            if digest in digests:
                raise ManifestError(f"duplicate server hash across manifests: {digest}")
            digests.add(digest)
    return manifests


def classify(
    data: bytes, manifests: Iterable[ReleaseManifest]
) -> tuple[str, ReleaseManifest | None]:
    digest = sha256(data)
    for manifest in manifests:
        if digest == manifest.original_sha256:
            return "original", manifest
        if digest == manifest.patched_sha256:
            return "patched", manifest
    return "unknown", None


def verify_signatures(data: bytes, manifest: ReleaseManifest, *, patched: bool) -> None:
    if len(data) != manifest.server_size:
        raise ManifestError(
            f"{manifest.version}: expected {manifest.server_size} bytes; got {len(data)}"
        )
    for item in manifest.patches:
        expected = item.replacement if patched else item.original
        first = data.find(expected)
        second = data.find(expected, first + 1) if first >= 0 else -1
        if first != item.file_offset or second >= 0:
            found = [offset for offset in (first, second) if offset >= 0]
            rendered = ", ".join(hex(offset) for offset in found) or "none"
            raise ManifestError(
                f"{item.patch_id}: expected one signature at "
                f"{item.file_offset:#x}; found {rendered}"
            )


def render_patched(original: bytes, manifest: ReleaseManifest) -> bytes:
    if sha256(original) != manifest.original_sha256:
        raise ManifestError("input hash does not match the manifest's original hash")
    verify_signatures(original, manifest, patched=False)

    output = bytearray(original)
    for item in manifest.patches:
        end = item.file_offset + len(item.original)
        output[item.file_offset:end] = item.replacement

    result = bytes(output)
    verify_signatures(result, manifest, patched=True)
    return result


def make_patched(original: bytes, manifest: ReleaseManifest) -> bytes:
    result = render_patched(original, manifest)
    if sha256(result) != manifest.patched_sha256:
        raise ManifestError("patched output hash does not match the approved manifest")
    return result


def changed_byte_ranges(patch: Patch) -> tuple[tuple[int, int], ...]:
    changed = [
        index
        for index, (before, after) in enumerate(zip(patch.original, patch.replacement))
        if before != after
    ]
    ranges: list[tuple[int, int]] = []
    for index in changed:
        if not ranges or index != ranges[-1][1]:
            ranges.append((index, index + 1))
        else:
            ranges[-1] = (ranges[-1][0], index + 1)
    return tuple(ranges)


def masked_candidates(data: bytes, patch: Patch) -> tuple[int, ...]:
    fixed = [
        index
        for index, (before, after) in enumerate(zip(patch.original, patch.replacement))
        if before == after
    ]
    if not fixed:
        return ()

    runs: list[tuple[int, int]] = []
    for index in fixed:
        if not runs or index != runs[-1][1]:
            runs.append((index, index + 1))
        else:
            runs[-1] = (runs[-1][0], index + 1)
    anchor_start, anchor_end = max(runs, key=lambda value: value[1] - value[0])
    anchor = patch.original[anchor_start:anchor_end]

    candidates: list[int] = []
    search_from = 0
    while True:
        anchor_position = data.find(anchor, search_from)
        if anchor_position < 0:
            break
        start = anchor_position - anchor_start
        end = start + len(patch.original)
        if start >= 0 and end <= len(data) and all(
            data[start + index] == patch.original[index] for index in fixed
        ):
            candidates.append(start)
        search_from = anchor_position + 1
    return tuple(dict.fromkeys(candidates))


def manifest_value(manifest: ReleaseManifest, dotted_path: str) -> Any:
    value: Any = manifest.raw
    for component in dotted_path.split("."):
        if not isinstance(value, dict) or component not in value:
            raise ManifestError(f"manifest field does not exist: {dotted_path}")
        value = value[component]
    if isinstance(value, (dict, list)):
        raise ManifestError(f"manifest field is not scalar: {dotted_path}")
    return value


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
