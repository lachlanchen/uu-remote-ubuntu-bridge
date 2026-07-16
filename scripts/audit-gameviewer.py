#!/usr/bin/env python3
"""Build evidence and a non-runnable draft manifest for a new UU release."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import struct
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from gameviewer_patchlib import (
    ManifestError,
    Patch,
    REPO_DIR,
    atomic_write,
    changed_byte_ranges,
    load_manifest,
    make_patched,
    manifest_from_dict,
    masked_candidates,
    render_patched,
    sha256,
    sha256_file,
)


PLACEHOLDER = "REPLACE_AFTER_REVIEW"


class AuditError(RuntimeError):
    pass


@dataclass(frozen=True)
class PESection:
    name: str
    virtual_address: int
    virtual_size: int
    raw_offset: int
    raw_size: int


@dataclass(frozen=True)
class PEInfo:
    machine: str
    image_base: int
    timestamp: str
    sections: tuple[PESection, ...]


def parse_pe(data: bytes) -> PEInfo:
    if len(data) < 0x100 or data[:2] != b"MZ":
        raise AuditError("server is not an MZ executable")
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if pe_offset + 24 > len(data) or data[pe_offset : pe_offset + 4] != b"PE\0\0":
        raise AuditError("server has no valid PE header")

    coff_offset = pe_offset + 4
    machine, section_count, timestamp, _, _, optional_size, _ = struct.unpack_from(
        "<HHIIIHH", data, coff_offset
    )
    if machine != 0x8664:
        raise AuditError(f"expected AMD64 PE machine 0x8664; got {machine:#x}")

    optional_offset = coff_offset + 20
    if optional_offset + optional_size > len(data):
        raise AuditError("truncated PE optional header")
    magic = struct.unpack_from("<H", data, optional_offset)[0]
    if magic != 0x20B:
        raise AuditError(f"expected PE32+ optional header; got {magic:#x}")
    image_base = struct.unpack_from("<Q", data, optional_offset + 24)[0]

    sections: list[PESection] = []
    section_offset = optional_offset + optional_size
    for index in range(section_count):
        offset = section_offset + index * 40
        if offset + 40 > len(data):
            raise AuditError("truncated PE section table")
        raw_name = data[offset : offset + 8].split(b"\0", 1)[0]
        name = raw_name.decode("ascii", errors="replace")
        virtual_size, virtual_address, raw_size, raw_offset = struct.unpack_from(
            "<IIII", data, offset + 8
        )
        sections.append(
            PESection(name, virtual_address, virtual_size, raw_offset, raw_size)
        )

    rendered_timestamp = datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
    return PEInfo("AMD64", image_base, rendered_timestamp, tuple(sections))


def file_offset_to_va(info: PEInfo, file_offset: int) -> int | None:
    for section in info.sections:
        if section.raw_offset <= file_offset < section.raw_offset + section.raw_size:
            return (
                info.image_base
                + section.virtual_address
                + file_offset
                - section.raw_offset
            )
    return None


def all_occurrences(data: bytes, needle: bytes) -> tuple[int, ...]:
    positions: list[int] = []
    start = 0
    while True:
        position = data.find(needle, start)
        if position < 0:
            return tuple(positions)
        positions.append(position)
        start = position + 1


def proposed_replacement(data: bytes, position: int, baseline: Patch) -> bytes:
    result = bytearray(data[position : position + len(baseline.original)])
    for start, end in changed_byte_ranges(baseline):
        result[start:end] = baseline.replacement[start:end]
    return bytes(result)


def scalar_hash(path: Path | None) -> str:
    return sha256_file(path) if path is not None else PLACEHOLDER


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)


def write_json(path: Path, value: Any) -> None:
    write_text(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def run_tool(arguments: list[str], output: Path) -> str:
    executable = shutil.which(arguments[0])
    if executable is None:
        return f"tool unavailable: {arguments[0]}"
    result = subprocess.run(
        [executable, *arguments[1:]],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
    )
    write_text(output, result.stdout)
    return f"exit={result.returncode} output={output.name}"


def disassemble_candidates(
    server: Path,
    output_dir: Path,
    pe: PEInfo,
    patch_id: str,
    positions: Iterable[int],
    signature_length: int,
) -> list[str]:
    objdump = shutil.which("x86_64-w64-mingw32-objdump")
    if objdump is None:
        return ["x86_64-w64-mingw32-objdump unavailable"]

    rendered: list[str] = []
    disassembly_dir = output_dir / "disassembly"
    disassembly_dir.mkdir(exist_ok=True)
    disassembly_dir.chmod(0o700)
    for index, position in enumerate(list(positions)[:8], start=1):
        address = file_offset_to_va(pe, position)
        if address is None:
            rendered.append(f"{position:#x}: not mapped to a PE section")
            continue
        start = max(pe.image_base, address - 96)
        stop = address + signature_length + 96
        destination = disassembly_dir / f"{patch_id}-{index}.txt"
        result = subprocess.run(
            [
                objdump,
                "-d",
                "-M",
                "intel",
                f"--start-address={start:#x}",
                f"--stop-address={stop:#x}",
                str(server),
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
        )
        write_text(destination, result.stdout)
        rendered.append(
            f"{position:#x} / VA {address:#x}: {destination.relative_to(output_dir)}"
        )
    return rendered


def inspect_release(args: argparse.Namespace) -> None:
    server = args.server.expanduser().resolve()
    installer = args.installer.expanduser().resolve() if args.installer else None
    healthd = args.healthd.expanduser().resolve() if args.healthd else None
    for label, path in (("server", server), ("installer", installer), ("healthd", healthd)):
        if path is not None and not path.is_file():
            raise AuditError(f"{label} file does not exist: {path}")
    baseline = load_manifest(args.baseline)
    data = server.read_bytes()
    digest = sha256(data)
    pe = parse_pe(data)

    output = (
        args.output.expanduser().resolve()
        if args.output
        else Path.cwd() / "build" / "audits" / f"{args.version}-{digest[:12]}"
    )
    if output.exists():
        if not output.is_dir() or any(output.iterdir()):
            raise AuditError(f"output path is not an empty directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    output.chmod(0o700)

    patch_results: list[dict[str, Any]] = []
    draft_patches: list[dict[str, Any]] = []
    disassembly_notes: dict[str, list[str]] = {}
    for patch in baseline.patches:
        exact_original = all_occurrences(data, patch.original)
        exact_replacement = all_occurrences(data, patch.replacement)
        candidates = masked_candidates(data, patch)
        selected = candidates[0] if len(candidates) == 1 else None
        patch_results.append(
            {
                "id": patch.patch_id,
                "baseline_offset": f"{patch.file_offset:#x}",
                "exact_original_offsets": [f"{value:#x}" for value in exact_original],
                "exact_replacement_offsets": [
                    f"{value:#x}" for value in exact_replacement
                ],
                "masked_candidate_offsets": [f"{value:#x}" for value in candidates],
                "selected_candidate": f"{selected:#x}" if selected is not None else None,
            }
        )
        disassembly_notes[patch.patch_id] = disassemble_candidates(
            server, output, pe, patch.patch_id, candidates, len(patch.original)
        )

        draft_item: dict[str, Any] = {
            "id": patch.patch_id,
            "description": patch.description,
            "rationale": patch.rationale,
            "candidate_status": "unreviewed",
            "candidate_offsets": [f"{value:#x}" for value in candidates],
        }
        if selected is not None:
            current = data[selected : selected + len(patch.original)]
            draft_item.update(
                {
                    "file_offset": f"{selected:#x}",
                    "original": current.hex(),
                    "replacement": proposed_replacement(
                        data, selected, patch
                    ).hex(),
                }
            )
        else:
            draft_item.update(
                {
                    "file_offset": None,
                    "original": None,
                    "replacement": None,
                }
            )
        draft_patches.append(draft_item)

    landmark_results: list[dict[str, Any]] = []
    for landmark in baseline.landmarks:
        offsets = all_occurrences(data, landmark.encode("utf-8"))
        landmark_results.append(
            {
                "text": landmark,
                "file_offsets": [f"{value:#x}" for value in offsets],
                "virtual_addresses": [
                    f"{address:#x}"
                    for value in offsets
                    if (address := file_offset_to_va(pe, value)) is not None
                ],
            }
        )

    draft = {
        "schema_version": 1,
        "review_status": "draft",
        "product": baseline.raw.get("product", "NetEase UU Remote"),
        "version": args.version,
        "architecture": baseline.architecture,
        "installer": {
            "filename": installer.name if installer else PLACEHOLDER,
            "url": baseline.installer_url,
            "sha256": scalar_hash(installer),
        },
        "server": {
            "filename": server.name,
            "size": len(data),
            "original_sha256": digest,
            "patched_sha256": "0" * 64,
            "patches": draft_patches,
        },
        "health_monitor": {
            "filename": healthd.name if healthd else baseline.healthd_filename,
            "original_sha256": scalar_hash(healthd),
        },
        "landmarks": list(baseline.landmarks),
        "imports": list(baseline.imports),
        "audit": {
            "baseline_version": baseline.version,
            "baseline_manifest": str(baseline.path),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "warning": "Candidate bytes are unreviewed and must not be applied.",
        },
    }

    summary = {
        "server": str(server),
        "server_sha256": digest,
        "server_size": len(data),
        "version_under_review": args.version,
        "baseline_version": baseline.version,
        "pe": {
            "machine": pe.machine,
            "image_base": f"{pe.image_base:#x}",
            "timestamp": pe.timestamp,
            "sections": [asdict(section) for section in pe.sections],
        },
        "landmarks": landmark_results,
        "patch_candidates": patch_results,
    }
    write_json(output / "audit.json", summary)
    write_json(output / "draft-manifest.json", draft)

    tool_notes = [
        run_tool(
            ["x86_64-w64-mingw32-objdump", "-p", str(server)],
            output / "objdump-headers.txt",
        ),
        run_tool(["strings", "-a", "-t", "x", str(server)], output / "strings.txt"),
    ]

    lines = [
        f"# UU {args.version} upstream audit",
        "",
        "> This report contains candidates, not an approved patch. Do not apply",
        "> draft bytes until each target has been reviewed in disassembly and tested",
        "> on a disposable copy of the executable.",
        "",
        "## Identity",
        "",
        f"- Server: `{server}`",
        f"- SHA-256: `{digest}`",
        f"- Size: `{len(data)}` bytes",
        f"- PE machine: `{pe.machine}`",
        f"- Image base: `{pe.image_base:#x}`",
        f"- Baseline: `{baseline.version}`",
        "",
        "## Semantic landmarks",
        "",
    ]
    for item in landmark_results:
        offsets = ", ".join(item["file_offsets"]) or "not found"
        lines.append(f"- `{item['text']}`: {offsets}")
    lines.extend(["", "## Patch candidates", ""])
    for result in patch_results:
        candidates = ", ".join(result["masked_candidate_offsets"]) or "none"
        lines.extend(
            [
                f"### `{result['id']}`",
                "",
                f"- Baseline offset: `{result['baseline_offset']}`",
                f"- Masked candidates: {candidates}",
                f"- Exact original matches: "
                f"{', '.join(result['exact_original_offsets']) or 'none'}",
                f"- Exact patched matches: "
                f"{', '.join(result['exact_replacement_offsets']) or 'none'}",
                "- Disassembly:",
            ]
        )
        lines.extend(f"  - {note}" for note in disassembly_notes[result["id"]])
        lines.append("")
    lines.extend(
        [
            "## Tool output",
            "",
            *(f"- {note}" for note in tool_notes),
            "",
            "## Required human review",
            "",
            "1. Compare Windows reference behavior and the new UU logs.",
            "2. Re-find each semantic string cross-reference in the new binary.",
            "3. Inspect complete function control flow around every candidate.",
            "4. Edit `draft-manifest.json`; set a patch's `candidate_status` to",
            "   `reviewed` only after its replacement is semantically justified.",
            "5. Supply the installer and health-monitor hashes if they were omitted.",
            "6. Finalize the manifest, patch only a disposable copy, and run the",
            "   full controller, restart, and 270-second stability tests.",
            "",
            "Finalize only after that review:",
            "",
            "```bash",
            "scripts/audit-gameviewer.py finalize \\",
            f"  --server {shlex.quote(str(server))} \\",
            f"  --draft {shlex.quote(str(output / 'draft-manifest.json'))} \\",
            f"  --output {shlex.quote(str(REPO_DIR / 'patches' / 'uu-remote-VERSION.json'))} \\",
            "  --reviewed-by NAME --review-note 'semantic review and test reference' \\",
            "  --accept-reviewed-disassembly",
            "```",
            "",
        ]
    )
    write_text(output / "REPORT.md", "\n".join(lines))
    print(f"audit report: {output / 'REPORT.md'}")
    print(f"draft manifest: {output / 'draft-manifest.json'}")
    print("status: DRAFT ONLY; no binary was modified")


def has_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return PLACEHOLDER in value
    if isinstance(value, list):
        return any(has_placeholder(item) for item in value)
    if isinstance(value, dict):
        return any(has_placeholder(item) for item in value.values())
    return False


def finalize_manifest(args: argparse.Namespace) -> None:
    if not args.accept_reviewed_disassembly:
        raise AuditError("--accept-reviewed-disassembly is required")
    server = args.server.expanduser().resolve()
    draft_path = args.draft.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if output.exists():
        raise AuditError(f"refusing to overwrite existing manifest: {output}")

    try:
        raw = json.loads(draft_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AuditError(f"could not read draft manifest: {error}") from error
    if not isinstance(raw, dict) or raw.get("review_status") != "draft":
        raise AuditError("input must be a draft manifest")
    if has_placeholder(raw):
        raise AuditError("draft still contains REPLACE_AFTER_REVIEW placeholders")

    server_section = raw.get("server")
    if not isinstance(server_section, dict):
        raise AuditError("draft server section is missing")
    patch_values = server_section.get("patches")
    if not isinstance(patch_values, list) or not patch_values:
        raise AuditError("draft has no patches")
    for item in patch_values:
        if not isinstance(item, dict) or item.get("candidate_status") != "reviewed":
            patch_id = item.get("id", "unknown") if isinstance(item, dict) else "unknown"
            raise AuditError(f"patch has not been reviewed: {patch_id}")
        item.pop("candidate_offsets", None)
        item.pop("candidate_status", None)

    data = server.read_bytes()
    if server_section.get("original_sha256") != sha256(data):
        raise AuditError("server hash no longer matches the draft")
    server_section["size"] = len(data)
    server_section["patched_sha256"] = "0" * 64
    provisional = manifest_from_dict(raw, draft_path, require_approved=False)
    patched = render_patched(data, provisional)
    server_section["patched_sha256"] = sha256(patched)
    raw["review_status"] = "approved"
    raw["review"] = {
        "reviewed_by": args.reviewed_by,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "evidence": args.review_note,
        "source_audit": draft_path.name,
        "source_audit_sha256": sha256_file(draft_path),
    }
    raw.pop("audit", None)

    approved = manifest_from_dict(raw, output, require_approved=True)
    make_patched(data, approved)
    payload = (json.dumps(raw, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    atomic_write(output, payload, 0o644)
    print(f"approved manifest: {output}")
    print(f"patched preview sha256: {approved.patched_sha256}")
    print("No binary was modified. Patch and test a disposable copy next.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser(
        "inspect", help="generate candidates and a draft manifest"
    )
    inspect_parser.add_argument("--server", type=Path, required=True)
    inspect_parser.add_argument("--baseline", type=Path, required=True)
    inspect_parser.add_argument("--version", required=True)
    inspect_parser.add_argument("--installer", type=Path)
    inspect_parser.add_argument("--healthd", type=Path)
    inspect_parser.add_argument("--output", type=Path)

    finalize_parser = subparsers.add_parser(
        "finalize", help="turn a manually reviewed draft into an approved manifest"
    )
    finalize_parser.add_argument("--server", type=Path, required=True)
    finalize_parser.add_argument("--draft", type=Path, required=True)
    finalize_parser.add_argument("--output", type=Path, required=True)
    finalize_parser.add_argument("--reviewed-by", required=True)
    finalize_parser.add_argument("--review-note", required=True)
    finalize_parser.add_argument(
        "--accept-reviewed-disassembly",
        action="store_true",
        help="confirm every patch was reviewed in the new disassembly",
    )
    return parser.parse_args()


def main() -> int:
    os.umask(0o077)
    args = parse_args()
    try:
        if args.command == "inspect":
            inspect_release(args)
        else:
            finalize_manifest(args)
    except (AuditError, ManifestError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
