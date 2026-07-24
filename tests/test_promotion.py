from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

SPEC = importlib.util.spec_from_file_location(
    "promote_approved_release",
    SCRIPTS_DIR / "promote-approved-release.py",
)
assert SPEC is not None and SPEC.loader is not None
promotion_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(promotion_module)

Promotion = promotion_module.Promotion
PromotionError = promotion_module.PromotionError
login_state = promotion_module.login_state
login_state_is_preserved = promotion_module.login_state_is_preserved
validate_acceptance = promotion_module.validate_acceptance


class FixturePromotion(Promotion):
    def __init__(self, *args, damage_login: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.damage_login = damage_login
        self.stop_count = 0
        self.start_count = 0
        self.verify_count = 0

    def service_state(self, unit: str, *, user: bool) -> dict[str, str]:
        if unit == "uu-remote-bridge.service" and user:
            return {
                "ActiveState": "active",
                "SubState": "running",
                "MainPID": "100",
            }
        if unit == "xrdp.service" and not user:
            return {
                "ActiveState": "active",
                "SubState": "running",
                "MainPID": "200",
            }
        raise AssertionError(f"unexpected service query: {unit}, user={user}")

    def current_runtime_check(self) -> None:
        return None

    def stop_live_uu(self) -> None:
        self.stop_count += 1

    def start_live_uu(self) -> None:
        self.start_count += 1

    def run_installer(self) -> None:
        target = self.prefix / "compat/release-manifest.json"
        shutil.copyfile(self.manifest_path, target)
        if self.damage_login:
            registry = self.prefix / "user.reg"
            registry.write_text("login state removed\n", encoding="utf-8")

    def verify_runtime(self, stability_seconds: int) -> None:
        self.verify_count += 1
        self.asserted_stability = stability_seconds


class PromotionTests(unittest.TestCase):
    def make_fixture(
        self, root: Path, *, damage_login: bool = False
    ) -> tuple[FixturePromotion, Path]:
        repository = root / "repository"
        scripts = repository / "scripts"
        patches = repository / "patches"
        docs = repository / "docs"
        scripts.mkdir(parents=True)
        patches.mkdir()
        docs.mkdir()
        for relative in ("install.sh", "scripts/stop-wine-prefix", "scripts/verify.sh"):
            path = repository / relative
            path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            path.chmod(0o755)

        installer = root / "accepted-installer.exe"
        installer.write_bytes(b"accepted installer fixture")
        installer_hash = hashlib.sha256(installer.read_bytes()).hexdigest()
        raw = json.loads(
            (REPO_DIR / "patches/uu-remote-4.33.0.8907.json").read_text(
                encoding="utf-8"
            )
        )
        raw["version"] = "4.34.0.8979"
        raw["installer"]["filename"] = installer.name
        raw["installer"]["sha256"] = installer_hash
        raw["acceptance"] = {
            "schema_version": 1,
            "disposable_prefix": True,
            "controller_input": True,
            "reconnect": True,
            "service_restart": True,
            "login_preservation": True,
            "stability_seconds": 270,
            "installer_sha256": installer_hash,
            "patched_server_sha256": raw["server"]["patched_sha256"],
            "evidence": "docs/acceptance.md",
            "accepted_at": "2026-07-24T12:00:00+00:00",
            "accepted_by": "maintainer fixture",
        }
        manifest = patches / "uu-remote-4.34.0.8979.json"
        manifest.write_text(
            json.dumps(raw, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (docs / "acceptance.md").write_text(
            "# Acceptance fixture\n", encoding="utf-8"
        )
        subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
        subprocess.run(["git", "add", "."], cwd=repository, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=UU Test",
                "-c",
                "user.email=uu-test@example.invalid",
                "commit",
                "-qm",
                "fixture",
            ],
            cwd=repository,
            check=True,
        )
        source_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        prefix = root / "prefix"
        (prefix / "compat").mkdir(parents=True)
        (prefix / "compat/release-manifest.json").write_text(
            '{"version":"4.33.0.8907"}\n', encoding="utf-8"
        )
        username = promotion_module.pwd.getpwuid(
            promotion_module.os.getuid()
        ).pw_name
        user_cache = (
            prefix
            / "drive_c/users"
            / username
            / "AppData/Local/GameViewer"
        )
        shared = prefix / "drive_c/ProgramData/Netease/GameViewer"
        user_cache.mkdir(parents=True)
        shared.mkdir(parents=True)
        (user_cache / "account.bin").write_bytes(b"existing account")
        (shared / "user_info.ini").write_bytes(b"existing shared account")
        (prefix / "user.reg").write_text(
            "\n".join(
                (
                    "WINE REGISTRY Version 2",
                    "",
                    "[Software\\\\Netease\\\\GameViewer\\\\login\\\\userPhone] 1",
                    '"token"="existing-login"',
                    "",
                )
            ),
            encoding="utf-8",
        )
        state_dir = root / "state"
        state_dir.mkdir()
        work_dir = state_dir / "tasks/fixture/promotion"
        instance = FixturePromotion(
            repository,
            manifest,
            installer,
            work_dir,
            state_dir,
            source_commit,
            prefix,
            damage_login=damage_login,
        )
        return instance, prefix

    def test_acceptance_is_bound_to_exact_installer_and_server_hashes(self) -> None:
        raw = json.loads(
            (REPO_DIR / "patches/uu-remote-4.33.0.8907.json").read_text(
                encoding="utf-8"
            )
        )
        raw["acceptance"] = {
            "schema_version": 1,
            **{
                field: True
                for field in promotion_module.REQUIRED_ACCEPTANCE_FLAGS
            },
            "stability_seconds": 270,
            "installer_sha256": raw["installer"]["sha256"],
            "patched_server_sha256": raw["server"]["patched_sha256"],
            "evidence": "docs/accepted.md",
            "accepted_at": "2026-07-24T12:00:00+00:00",
            "accepted_by": "maintainer",
        }
        self.assertEqual(270, validate_acceptance(raw)["stability_seconds"])

        changed = copy.deepcopy(raw)
        changed["acceptance"]["installer_sha256"] = "0" * 64
        with self.assertRaisesRegex(PromotionError, "installer hash"):
            validate_acceptance(changed)

        changed = copy.deepcopy(raw)
        changed["acceptance"]["controller_input"] = False
        with self.assertRaisesRegex(PromotionError, "controller_input"):
            validate_acceptance(changed)

    def test_login_state_comparison_is_exact_and_private(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            promotion, prefix = self.make_fixture(Path(temporary))
            before = login_state(prefix, promotion.username)
            after = login_state(prefix, promotion.username)
            self.assertTrue(login_state_is_preserved(before, after))
            account = (
                prefix
                / "drive_c/users"
                / promotion.username
                / "AppData/Local/GameViewer/account.bin"
            )
            account.write_bytes(b"changed account")
            self.assertFalse(
                login_state_is_preserved(
                    before, login_state(prefix, promotion.username)
                )
            )
            self.assertNotIn("existing-login", json.dumps(before))

    def test_successful_promotion_keeps_login_and_never_manages_xrdp(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            promotion, prefix = self.make_fixture(Path(temporary))
            result = promotion.apply()
            self.assertEqual("promoted", result["status"])
            self.assertTrue(result["login_preserved"])
            self.assertTrue(result["xrdp_unchanged"])
            self.assertEqual(1, promotion.stop_count)
            self.assertEqual(1, promotion.start_count)
            self.assertEqual(1, promotion.verify_count)
            self.assertEqual(270, promotion.asserted_stability)
            self.assertFalse(promotion.marker.exists())
            self.assertTrue(promotion.snapshot_prefix.is_dir())
            installed = json.loads(
                (prefix / "compat/release-manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual("4.34.0.8979", installed["version"])

    def test_login_damage_rolls_back_complete_prefix_and_stops_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            promotion, prefix = self.make_fixture(
                Path(temporary), damage_login=True
            )
            with self.assertRaisesRegex(PromotionError, "login/account"):
                promotion.apply()
            restored = json.loads(
                (prefix / "compat/release-manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual("4.33.0.8907", restored["version"])
            self.assertFalse(promotion.marker.exists())
            result = json.loads(
                promotion.result_path.read_text(encoding="utf-8")
            )
            self.assertEqual("failed", result["status"])
            self.assertTrue(result["rollback"]["rolled_back"])
            self.assertEqual(2, promotion.stop_count)
            self.assertEqual(1, promotion.start_count)

    def test_source_contains_no_xrdp_mutation_command(self) -> None:
        source = (SCRIPTS_DIR / "promote-approved-release.py").read_text(
            encoding="utf-8"
        )
        for action in ("start", "stop", "restart", "reload"):
            self.assertNotIn(f'{action}", "xrdp.service', source)


if __name__ == "__main__":
    unittest.main()
