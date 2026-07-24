from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR / "scripts"))

from uu_update_manager import (
    Config,
    Manager,
    codex_budget_from_rate_limits,
    release_version,
    sanitize_url,
    version_key,
)


class UpdateManagerTests(unittest.TestCase):
    def config(self, state_dir: Path) -> Config:
        return Config(
            path=state_dir / "config.json",
            repository=REPO_DIR,
            state_dir=state_dir,
            remote="origin",
            branch="main",
            track="track-rdp-broker-20260724",
            endpoint="https://example.invalid/latest?private=token",
            codex_executable=Path("/opt/codex/bin/codex"),
            codex_model="codex-auto-review",
            codex_reasoning_effort="medium",
            codex_timeout_seconds=5400,
            codex_max_used_percent=20,
            idle_minutes=45,
            auto_reinstall_known_good=True,
            max_download_bytes=1024 * 1024 * 1024,
        )

    def test_codex_budget_ignores_credits_and_enforces_usage_cap(self) -> None:
        payload = {
            "rateLimitsByLimitId": {
                "codex": {
                    "primary": {"usedPercent": 21, "resetsAt": 2000000000},
                    "secondary": {"usedPercent": 10, "resetsAt": 1999990000},
                }
            },
            "credits": {"hasCredits": True, "balance": "9999"},
        }
        budget = codex_budget_from_rate_limits(payload, 20)
        self.assertFalse(budget["allowed"])
        self.assertFalse(budget["credits_considered"])
        self.assertEqual(21, budget["observed_used_percent"])

        payload["rateLimitsByLimitId"]["codex"]["primary"]["usedPercent"] = 20
        self.assertTrue(codex_budget_from_rate_limits(payload, 20)["allowed"])

    def test_monitor_defers_without_launching_codex_above_cap(self) -> None:
        class DeferredManager(Manager):
            def run_codex(self, task):
                raise AssertionError("Codex must not run above the configured cap")

        with tempfile.TemporaryDirectory() as temporary, patch(
            "uu_update_manager.codex_rate_limits",
            return_value={
                "rateLimitsByLimitId": {
                    "codex": {"primary": {"usedPercent": 25}}
                },
                "credits": {"hasCredits": True, "balance": "9999"},
            },
        ), patch(
            "uu_update_manager.workspace_sandbox_probe",
            return_value={"available": True, "returncode": 0, "detail": ""},
        ):
            manager = DeferredManager(self.config(Path(temporary)))
            manager.save_task({"id": "deferred", "attempts": 0})
            manager.monitor()
            task = json.loads(manager.pending_path.read_text(encoding="utf-8"))
            self.assertEqual("codex-budget-deferred", task["phase"])
            self.assertEqual(0, task["attempts"])
            self.assertFalse(task["codex_budget"]["credits_considered"])

    def test_model_change_starts_a_new_thread_with_existing_context(self) -> None:
        class ModelChangeManager(Manager):
            def run_codex(self, task):
                self.assertion = task
                return 0, {}

        with tempfile.TemporaryDirectory() as temporary, patch(
            "uu_update_manager.codex_rate_limits",
            return_value={
                "rateLimitsByLimitId": {"codex": {"primary": {"usedPercent": 1}}}
            },
        ), patch(
            "uu_update_manager.workspace_sandbox_probe",
            return_value={"available": True, "returncode": 0, "detail": ""},
        ):
            manager = ModelChangeManager(self.config(Path(temporary)))
            manager.save_task(
                {
                    "id": "model-change",
                    "attempts": 0,
                    "thread_id": "old-thread",
                    "codex_model": "gpt-5.6-sol",
                    "codex_reasoning_effort": "xhigh",
                }
            )
            manager.monitor()
            self.assertIsNone(manager.assertion["thread_id"])
            self.assertEqual(
                "codex-auto-review", manager.assertion["codex_model"]
            )

    def test_monitor_defers_before_codex_when_workspace_sandbox_is_unavailable(
        self,
    ) -> None:
        class DeferredManager(Manager):
            def run_codex(self, task):
                raise AssertionError("Codex must not run without workspace-write")

        with tempfile.TemporaryDirectory() as temporary, patch(
            "uu_update_manager.workspace_sandbox_probe",
            return_value={
                "available": False,
                "returncode": 1,
                "detail": "No permissions to create new namespace",
            },
        ), patch(
            "uu_update_manager.codex_rate_limits",
            side_effect=AssertionError("budget query must follow sandbox preflight"),
        ):
            manager = DeferredManager(self.config(Path(temporary)))
            manager.save_task({"id": "sandbox-deferred", "attempts": 0})
            manager.monitor()
            task = json.loads(manager.pending_path.read_text(encoding="utf-8"))
            self.assertEqual("codex-sandbox-deferred", task["phase"])
            self.assertEqual(0, task["attempts"])
            self.assertIn("namespace", task["workspace_sandbox"]["detail"])

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
                    "last_modified": "",
                    "content_length": 1234,
                    "installer_sha256": approved_hash,
                },
            )
            manager.check()
            status = json.loads(manager.status_path.read_text(encoding="utf-8"))
            self.assertEqual("current", status["phase"])
            self.assertIn("cached full hash", status["message"])

    def test_download_cache_is_bound_to_release_metadata_and_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manager = Manager(self.config(Path(temporary)))
            manager.downloads_dir.mkdir(parents=True)
            installer = manager.downloads_dir / "uu-4.33.0.8907.exe"
            installer.write_bytes(b"approved fixture")
            installer_hash = hashlib.sha256(installer.read_bytes()).hexdigest()
            metadata = {
                "version": "4.33.0.8907",
                "etag": "verified-etag",
                "last_modified": "Wed, 22 Jul 2026 12:00:00 GMT",
                "content_length": installer.stat().st_size,
            }
            manager.record_download(metadata, installer, installer_hash)
            self.assertEqual((installer, installer_hash), manager.cached_download(metadata))

            changed = dict(metadata, etag="replacement-etag")
            self.assertIsNone(manager.cached_download(changed))

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
            self.assertEqual("/opt/codex/bin/codex", initial[0])
            self.assertIn("codex-auto-review", initial)
            self.assertIn('model_reasoning_effort="medium"', initial)
            self.assertIn("workspace-write", initial)
            self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", initial)

            task["thread_id"] = "019f89b6-dd9d-7f11-98ef-0e7501fcae3c"
            resumed = manager.codex_command(task, resume=True)
            self.assertEqual(
                ["/opt/codex/bin/codex", "exec", "resume"], resumed[:3]
            )
            self.assertIn(task["thread_id"], resumed)

    def test_retry_requeues_a_blocked_task_without_deleting_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manager = Manager(self.config(root))
            task_dir = manager.tasks_dir / "blocked-fixture"
            task_dir.mkdir(parents=True)
            evidence = task_dir / "codex-events.jsonl"
            evidence.write_text('{"type":"fixture"}\n', encoding="utf-8")
            task = {
                "schema_version": 1,
                "id": "blocked-fixture",
                "phase": "blocked",
                "attempts": 1,
                "thread_id": "old-thread",
                "result": {"status": "blocked"},
                "verification": {"tests_passed": True},
                "completed_at": "2026-07-24T00:00:00+00:00",
            }
            (task_dir / "task.json").write_text(json.dumps(task), encoding="utf-8")
            manager.write_status("blocked", active_task=task["id"])

            manager.retry_task()

            queued = json.loads(manager.pending_path.read_text(encoding="utf-8"))
            self.assertEqual("queued", queued["phase"])
            self.assertIsNone(queued["thread_id"])
            self.assertEqual(1, queued["attempts"])
            self.assertEqual(1, queued["retry_count"])
            self.assertNotIn("result", queued)
            self.assertNotIn("verification", queued)
            self.assertEqual('{"type":"fixture"}\n', evidence.read_text())

    def test_ready_for_review_is_never_eligible_for_live_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manager = Manager(self.config(root))
            task_dir = manager.tasks_dir / "review-fixture"
            task_dir.mkdir(parents=True)
            task = {"id": "review-fixture"}
            with patch.object(
                manager,
                "verify_repair",
                return_value={
                    "changed": True,
                    "tests_passed": True,
                    "safety_violations": [],
                },
            ):
                manager.finish_task(task, {"status": "ready_for_review"})
            retained = json.loads(
                (task_dir / "task.json").read_text(encoding="utf-8")
            )
            self.assertEqual("ready-for-review", retained["phase"])
            self.assertFalse(retained["live_promotion"]["eligible"])

    def test_config_requires_and_preserves_absolute_codex_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "updater.json"
            config_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "repository": str(REPO_DIR),
                        "state_dir": str(root / "state"),
                        "remote": "origin",
                        "branch": "main",
                        "track": "track-direct-x11-20260724",
                        "endpoint": "https://example.invalid/latest",
                        "codex_executable": "/bin/true",
                        "codex_model": "codex-auto-review",
                        "codex_reasoning_effort": "medium",
                    }
                ),
                encoding="utf-8",
            )
            config = Config.read(config_path)
            self.assertEqual(Path("/bin/true"), config.codex_executable)
            self.assertEqual("codex-auto-review", config.codex_model)
            self.assertEqual("medium", config.codex_reasoning_effort)

            raw = json.loads(config_path.read_text(encoding="utf-8"))
            raw.pop("codex_executable")
            config_path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(
                Exception, "absolute executable Codex path"
            ):
                Config.read(config_path)

    def test_repair_context_snapshots_complete_operational_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manager = Manager(self.config(root / "state"))
            repair_repo = root / "repair"
            repair_repo.mkdir()
            task = {
                "id": "upstream-release-fixture",
                "kind": "upstream-release",
                "created_at": "2026-07-24T00:00:00+00:00",
                "base_commit": "fixture-base",
                "details": {"version": "4.34.0.8979"},
            }
            context = manager.write_context(task, repair_repo)
            handoff = context.parent / "OPERATIONAL-HANDOFF.md"
            self.assertTrue(handoff.is_file())
            self.assertIn("The Two Validated Host Profiles", handoff.read_text())
            self.assertIn("OPERATIONAL-HANDOFF.md", context.read_text())
            self.assertIn("mobile-keyboard-parity-handoff.md", context.read_text())

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
        self.assertIn('"$codex_executable" login status 2>&1', configurator)
        self.assertIn('"codex_executable": codex_executable', configurator)
        self.assertIn("--codex PATH", configurator)
        self.assertIn("model='codex-auto-review'", configurator)
        self.assertIn("reasoning_effort='medium'", configurator)
        self.assertIn('scripts/uu-remote"', configurator)
        self.assertIn("track-direct-x11-20260724", configurator)
        self.assertIn("track-rdp-broker-20260724", configurator)

    def test_health_detects_restart_storm_and_wrong_rdp_listener(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            environment = home / ".config/uu-remote-bridge/environment"
            manifest = (
                home
                / ".local/share/wineprefixes/uu-remote/compat/release-manifest.json"
            )
            environment.parent.mkdir(parents=True)
            environment.write_text("UURB_RDP_PORT=3391\n", encoding="utf-8")
            manifest.parent.mkdir(parents=True)
            manifest.write_text("{}\n", encoding="utf-8")
            responses = [
                subprocess.CompletedProcess(
                    [], 0, "ActiveState=active\nNRestarts=64\n", ""
                ),
                subprocess.CompletedProcess([], 0, "101\n", ""),
                subprocess.CompletedProcess([], 0, "102\n", ""),
                subprocess.CompletedProcess([], 0, "103\n", ""),
                subprocess.CompletedProcess(
                    [], 0, 'LISTEN 0 10 *:3391 *:* users:(("gnome-remote-de",pid=99,fd=15))\n', ""
                ),
            ]

            with patch.object(Path, "home", return_value=home), patch(
                "uu_update_manager.command_output", side_effect=responses
            ):
                health = Manager(self.config(root / "state")).health()

            self.assertFalse(health["healthy"])
            self.assertIn("bridge-restart-storm", health["issues"])
            self.assertIn("rdp-listener-owner-mismatch", health["issues"])
            self.assertEqual(64, health["restart_count"])
            self.assertEqual(3391, health["rdp_port"])


if __name__ == "__main__":
    unittest.main()
