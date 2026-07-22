from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR / "scripts"))

from uu_update_manager import Config, Manager, release_version, sanitize_url, version_key


class UpdateManagerTests(unittest.TestCase):
    def config(self, state_dir: Path) -> Config:
        return Config(
            path=state_dir / "config.json",
            repository=REPO_DIR,
            state_dir=state_dir,
            remote="origin",
            branch="main",
            track="track-rdp-broker-v1",
            endpoint="https://example.invalid/latest?private=token",
            codex_model="gpt-5.6-sol",
            codex_reasoning_effort="xhigh",
            codex_timeout_seconds=5400,
            idle_minutes=45,
            auto_reinstall_known_good=True,
            max_download_bytes=1024 * 1024 * 1024,
        )

    def test_release_version_prefers_full_build_identifier(self) -> None:
        self.assertEqual(
            "4.32.200.8919",
            release_version(
                "uuyc_4.32.200.exe",
                "/UURemote_Setup_4.32.200.8919_0716205104_gwqd.exe",
            ),
        )
        self.assertGreater(
            version_key("4.33.0.8907"), version_key("4.32.200.8919")
        )

    def test_ephemeral_download_keys_are_not_persisted(self) -> None:
        self.assertEqual(
            "https://downloads.example.test/uu.exe",
            sanitize_url(
                "https://downloads.example.test/uu.exe?key1=secret&key2=temporary"
            ),
        )

    def test_older_official_endpoint_never_downloads_or_restarts(self) -> None:
        class OlderEndpointManager(Manager):
            def fetch_repository(self) -> None:
                return None

            def approved_releases(self):
                return [
                    {
                        "version": "4.33.0.8907",
                        "installer_sha256": "a" * 64,
                        "manifest": "approved.json",
                    }
                ]

            def installed_release(self):
                return {"version": "4.33.0.8907", "manifest": "installed.json"}

            def probe_endpoint(self):
                return {
                    "checked_at": "test",
                    "version": "4.32.200.8919",
                    "filename": "uuyc_4.32.200.exe",
                    "final_url": "https://example.invalid/old.exe",
                    "etag": "old",
                    "last_modified": "",
                    "content_length": 1,
                }

            def download_release(self, metadata):
                raise AssertionError("an older endpoint must not be downloaded")

        with tempfile.TemporaryDirectory() as temporary:
            manager = OlderEndpointManager(self.config(Path(temporary)))
            manager.check()
            status = json.loads(manager.status_path.read_text(encoding="utf-8"))
            self.assertEqual("current", status["phase"])
            self.assertIn("older", status["message"])
            self.assertFalse(manager.pending_path.exists())

    def test_cached_same_release_hash_avoids_daily_redownload(self) -> None:
        approved_hash = "a" * 64

        class CachedEndpointManager(Manager):
            def fetch_repository(self) -> None:
                return None

            def approved_releases(self):
                return [
                    {
                        "version": "4.33.0.8907",
                        "installer_sha256": approved_hash,
                        "manifest": "approved.json",
                    }
                ]

            def installed_release(self):
                return {"version": "4.33.0.8907", "manifest": "installed.json"}

            def probe_endpoint(self):
                return {
                    "checked_at": "test-2",
                    "version": "4.33.0.8907",
                    "filename": "uuyc_4.33.0.exe",
                    "final_url": "https://example.invalid/current.exe",
                    "etag": "stable-etag",
                    "last_modified": "",
                    "content_length": 1234,
                }

            def download_release(self, metadata):
                raise AssertionError("an unchanged verified ETag must not be downloaded")

        with tempfile.TemporaryDirectory() as temporary:
            manager = CachedEndpointManager(self.config(Path(temporary)))
            manager.write_status(
                "current",
                observed_release={
                    "version": "4.33.0.8907",
                    "etag": "stable-etag",
                    "content_length": 1234,
                    "installer_sha256": approved_hash,
                },
            )
            manager.check()
            status = json.loads(manager.status_path.read_text(encoding="utf-8"))
            self.assertEqual("current", status["phase"])
            self.assertIn("cached full hash", status["message"])

    def test_codex_command_is_resumable_and_keeps_a_workspace_sandbox(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            manager = Manager(self.config(state))
            repair_repo = state / "repair"
            (repair_repo / "scripts").mkdir(parents=True)
            (repair_repo / "scripts/codex-repair-result.schema.json").write_text("{}")
            task = {
                "id": "fixture",
                "repair_repo": str(repair_repo),
                "thread_id": None,
            }
            initial = manager.codex_command(task, resume=False)
            self.assertIn("gpt-5.6-sol", initial)
            self.assertIn('model_reasoning_effort="xhigh"', initial)
            self.assertIn("workspace-write", initial)
            self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", initial)

            task["thread_id"] = "019f89b6-dd9d-7f11-98ef-0e7501fcae3c"
            resumed = manager.codex_command(task, resume=True)
            self.assertEqual(["codex", "exec", "resume"], resumed[:3])
            self.assertIn(task["thread_id"], resumed)

    def test_systemd_timers_survive_boot_without_touching_the_bridge(self) -> None:
        daily = (REPO_DIR / "systemd/uu-remote-update-check.timer").read_text()
        monitor = (REPO_DIR / "systemd/uu-remote-repair-monitor.timer").read_text()
        check_service = (
            REPO_DIR / "systemd/uu-remote-update-check.service"
        ).read_text()
        self.assertIn("Persistent=true", daily)
        self.assertIn("OnBootSec=7min", monitor)
        self.assertIn("OnUnitInactiveSec=15min", monitor)
        self.assertNotIn("restart uu-remote-bridge", check_service)

    def test_installer_exposes_opt_in_automatic_maintenance(self) -> None:
        installer = (REPO_DIR / "install.sh").read_text()
        configurator = (REPO_DIR / "scripts/configure-updater.sh").read_text()
        self.assertIn("--automatic-updates", installer)
        self.assertIn('configure-updater.sh" enable', installer)
        self.assertIn("codex login status 2>&1", configurator)
        self.assertIn("track-direct-x11-v1", configurator)
        self.assertIn("track-rdp-broker-v1", configurator)


if __name__ == "__main__":
    unittest.main()
