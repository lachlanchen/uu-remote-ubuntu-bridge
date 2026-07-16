from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR / "scripts"))

from gameviewer_patchlib import (  # noqa: E402
    ManifestError,
    classify,
    load_manifest,
    make_patched,
    manifest_from_dict,
    manifest_value,
    masked_candidates,
    render_patched,
    sha256,
    verify_signatures,
)


class PatchToolingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.signature = bytes.fromhex("deadbeef11223344cafebabe")
        self.replacement = bytes.fromhex("deadbeef90909044cafebabe")
        self.offset = 64
        self.original = bytes(range(64)) + self.signature + bytes(range(64, 128))
        expected = bytearray(self.original)
        expected[self.offset : self.offset + len(self.signature)] = self.replacement
        self.patched = bytes(expected)
        self.raw = {
            "schema_version": 1,
            "review_status": "approved",
            "product": "Synthetic UU fixture",
            "version": "test-1",
            "architecture": "x86_64",
            "installer": {
                "filename": "fixture.exe",
                "url": "https://example.invalid/fixture.exe",
                "sha256": "1" * 64,
            },
            "server": {
                "filename": "GameViewerServer.exe",
                "size": len(self.original),
                "original_sha256": sha256(self.original),
                "patched_sha256": sha256(self.patched),
                "patches": [
                    {
                        "id": "synthetic-switch",
                        "description": "Exercise a bounded replacement",
                        "rationale": "Unit-test the generic manifest engine",
                        "file_offset": hex(self.offset),
                        "original": self.signature.hex(),
                        "replacement": self.replacement.hex(),
                    }
                ],
            },
            "health_monitor": {
                "filename": "GameViewerHealthd.exe",
                "original_sha256": "2" * 64,
            },
            "landmarks": ["synthetic landmark"],
            "imports": ["USER32.dll!SendInput"],
        }

    def manifest(self):
        return manifest_from_dict(self.raw, Path("synthetic.json"))

    def test_patch_and_verify_round_trip(self) -> None:
        manifest = self.manifest()
        verify_signatures(self.original, manifest, patched=False)
        result = make_patched(self.original, manifest)
        self.assertEqual(self.patched, result)
        verify_signatures(result, manifest, patched=True)

    def test_classification_uses_complete_hashes(self) -> None:
        manifest = self.manifest()
        self.assertEqual(("original", manifest), classify(self.original, [manifest]))
        self.assertEqual(("patched", manifest), classify(self.patched, [manifest]))
        self.assertEqual(("unknown", None), classify(self.original + b"x", [manifest]))

    def test_masked_candidate_finds_shifted_signature(self) -> None:
        manifest = self.manifest()
        shifted = b"prefix" + self.original
        self.assertEqual(
            (self.offset + len(b"prefix"),),
            masked_candidates(shifted, manifest.patches[0]),
        )

    def test_draft_manifest_is_not_runnable(self) -> None:
        draft = copy.deepcopy(self.raw)
        draft["review_status"] = "draft"
        with self.assertRaises(ManifestError):
            manifest_from_dict(draft, Path("draft.json"))
        provisional = manifest_from_dict(
            draft, Path("draft.json"), require_approved=False
        )
        self.assertEqual(self.patched, render_patched(self.original, provisional))

    def test_overlapping_patches_are_rejected(self) -> None:
        overlapping = copy.deepcopy(self.raw)
        duplicate = copy.deepcopy(overlapping["server"]["patches"][0])
        duplicate["id"] = "overlap"
        duplicate["file_offset"] = hex(self.offset + 1)
        overlapping["server"]["patches"].append(duplicate)
        with self.assertRaises(ManifestError):
            manifest_from_dict(overlapping, Path("overlap.json"))

    def test_manifest_field_lookup(self) -> None:
        manifest = self.manifest()
        self.assertEqual("test-1", manifest_value(manifest, "version"))
        self.assertEqual("1" * 64, manifest_value(manifest, "installer.sha256"))
        with self.assertRaises(ManifestError):
            manifest_value(manifest, "server.patches")

    def test_repository_manifest_is_approved(self) -> None:
        manifest = load_manifest(
            REPO_DIR / "patches" / "uu-remote-4.33.0.8907.json"
        )
        self.assertEqual("4.33.0.8907", manifest.version)
        self.assertEqual(4, len(manifest.patches))

    def test_cli_enforces_expected_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            manifest_path = directory / "release.json"
            server_path = directory / "server.exe"
            manifest_path.write_text(json.dumps(self.raw), encoding="utf-8")
            server_path.write_bytes(self.original)
            base_command = [
                sys.executable,
                str(REPO_DIR / "scripts" / "patch-gameviewer.py"),
                "verify",
                str(server_path),
                "--manifest",
                str(manifest_path),
            ]
            accepted = subprocess.run(
                [*base_command, "--expect", "original"],
                check=False,
                capture_output=True,
                text=True,
            )
            rejected = subprocess.run(
                [*base_command, "--expect", "patched"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, accepted.returncode, accepted.stderr)
            self.assertEqual(1, rejected.returncode)
            self.assertIn("expected patched state", rejected.stderr)

    def test_cli_refuses_restore_over_unknown_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            manifest_path = directory / "release.json"
            server_path = directory / "server.exe"
            manifest_path.write_text(json.dumps(self.raw), encoding="utf-8")
            server_path.write_bytes(self.original)
            common = ["--manifest", str(manifest_path)]
            patched = subprocess.run(
                [
                    sys.executable,
                    str(REPO_DIR / "scripts" / "patch-gameviewer.py"),
                    "patch",
                    str(server_path),
                    *common,
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, patched.returncode, patched.stderr)
            server_path.write_bytes(b"unknown replacement")
            restored = subprocess.run(
                [
                    sys.executable,
                    str(REPO_DIR / "scripts" / "patch-gameviewer.py"),
                    "restore",
                    str(server_path),
                    *common,
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(1, restored.returncode)
            self.assertIn("unsupported executable", restored.stderr)
            self.assertEqual(b"unknown replacement", server_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
