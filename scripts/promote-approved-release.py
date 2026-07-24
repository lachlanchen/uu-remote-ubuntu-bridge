#!/usr/bin/env python3
"""Transactionally promote a fully accepted UU release without losing login state."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pwd
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from gameviewer_patchlib import ManifestError, load_manifest, sha256_file


REQUIRED_ACCEPTANCE_FLAGS = (
    "disposable_prefix",
    "controller_input",
    "reconnect",
    "service_restart",
    "login_preservation",
)
MINIMUM_STABILITY_SECONDS = 270
MAXIMUM_STABILITY_SECONDS = 1800


class PromotionError(RuntimeError):
    """A promotion gate or transaction failed."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PromotionError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise PromotionError(f"expected a JSON object in {path}")
    return value


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(0o600)
    temporary.replace(path)


def version_key(value: str) -> tuple[int, ...]:
    if not re.fullmatch(r"\d+(?:\.\d+){2,3}", value):
        raise PromotionError(f"unsupported UU version: {value}")
    parts = tuple(int(part) for part in value.split("."))
    return parts + (0,) * (4 - len(parts))


def relative_repository_path(value: str, field: str) -> Path:
    path = Path(value)
    if (
        path.is_absolute()
        or not path.parts
        or ".." in path.parts
        or path == Path(".")
    ):
        raise PromotionError(f"{field} must be a repository-relative path")
    return path


def validate_acceptance(raw: dict[str, Any]) -> dict[str, Any]:
    acceptance = raw.get("acceptance")
    if not isinstance(acceptance, dict) or acceptance.get("schema_version") != 1:
        raise PromotionError("approved manifest has no versioned acceptance record")
    missing = [
        field
        for field in REQUIRED_ACCEPTANCE_FLAGS
        if acceptance.get(field) is not True
    ]
    if missing:
        raise PromotionError(
            "release acceptance is incomplete: " + ", ".join(sorted(missing))
        )
    stability = acceptance.get("stability_seconds")
    if (
        not isinstance(stability, int)
        or isinstance(stability, bool)
        or stability < MINIMUM_STABILITY_SECONDS
        or stability > MAXIMUM_STABILITY_SECONDS
    ):
        raise PromotionError(
            "release acceptance stability must be between "
            f"{MINIMUM_STABILITY_SECONDS} and {MAXIMUM_STABILITY_SECONDS} seconds"
        )
    evidence = acceptance.get("evidence")
    if not isinstance(evidence, str) or not evidence.strip():
        raise PromotionError("release acceptance needs a non-empty evidence reference")
    relative_repository_path(evidence, "acceptance.evidence")
    for field in ("accepted_at", "accepted_by"):
        value = acceptance.get(field)
        if not isinstance(value, str) or not value.strip():
            raise PromotionError(f"release acceptance needs {field}")
    installer = raw.get("installer")
    server = raw.get("server")
    if not isinstance(installer, dict) or not isinstance(server, dict):
        raise PromotionError("release manifest is missing installer or server metadata")
    if acceptance.get("installer_sha256") != installer.get("sha256"):
        raise PromotionError("acceptance is not bound to this installer hash")
    if acceptance.get("patched_server_sha256") != server.get("patched_sha256"):
        raise PromotionError("acceptance is not bound to this patched server hash")
    return dict(acceptance)


def directory_state(path: Path) -> dict[str, int | str | bool]:
    if not path.is_dir():
        return {"exists": False, "files": 0, "bytes": 0, "digest": ""}
    digest = hashlib.sha256()
    files = 0
    size = 0
    for item in sorted(path.rglob("*"), key=lambda candidate: str(candidate)):
        try:
            if not item.is_file() or item.is_symlink():
                continue
            relative = item.relative_to(path).as_posix()
            stat_result = item.stat()
            digest.update(relative.encode("utf-8", errors="surrogateescape"))
            digest.update(b"\0")
            digest.update(str(stat_result.st_size).encode("ascii"))
            digest.update(b"\0")
            with item.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            files += 1
            size += stat_result.st_size
        except OSError:
            return {
                "exists": True,
                "files": files,
                "bytes": size,
                "digest": "",
            }
    return {
        "exists": True,
        "files": files,
        "bytes": size,
        "digest": digest.hexdigest(),
    }


def registry_login_digest(path: Path) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return ""
    selected: list[str] = []
    collecting = False
    for line in lines:
        if line.startswith("["):
            header = line.split("]", 1)[0] + "]" if "]" in line else line
            normalized = header.lower()
            collecting = (
                "\\\\netease\\\\gameviewer\\\\login\\\\" in normalized
                or normalized.endswith("\\\\netease\\\\gameviewer\\\\login]")
            )
            if collecting:
                selected.append(header)
            continue
        if collecting:
            if not line:
                collecting = False
            else:
                selected.append(line)
    if not selected:
        return ""
    return hashlib.sha256("\n".join(selected).encode("utf-8")).hexdigest()


def login_state(prefix: Path, username: str) -> dict[str, Any]:
    return {
        "registry_login_digest": registry_login_digest(prefix / "user.reg"),
        "user_cache": directory_state(
            prefix
            / "drive_c/users"
            / username
            / "AppData/Local/GameViewer"
        ),
        "shared_state": directory_state(
            prefix / "drive_c/ProgramData/Netease/GameViewer"
        ),
    }


def login_state_is_usable(value: dict[str, Any]) -> bool:
    if not value.get("registry_login_digest"):
        return False
    return any(
        isinstance(value.get(field), dict)
        and value[field].get("exists") is True
        and int(value[field].get("files", 0)) > 0
        and bool(value[field].get("digest"))
        for field in ("user_cache", "shared_state")
    )


def login_state_is_preserved(before: dict[str, Any], after: dict[str, Any]) -> bool:
    if not login_state_is_usable(before) or not login_state_is_usable(after):
        return False
    if before.get("registry_login_digest") != after.get("registry_login_digest"):
        return False
    for field in ("user_cache", "shared_state"):
        prior = before.get(field)
        current = after.get(field)
        if not isinstance(prior, dict) or not isinstance(current, dict):
            return False
        if prior.get("exists") is True and (
            current.get("exists") is not True
            or prior.get("files") != current.get("files")
            or prior.get("bytes") != current.get("bytes")
            or prior.get("digest") != current.get("digest")
        ):
            return False
    return True


def command(
    arguments: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 1800,
    log: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    if log is None:
        return subprocess.run(
            arguments,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    log.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with log.open("a", encoding="utf-8") as stream:
        result = subprocess.run(
            arguments,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=stream,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            check=False,
        )
    log.chmod(0o600)
    return result


def command_error(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stderr or result.stdout or "command failed").strip()[-1000:]


def parse_properties(value: str) -> dict[str, str]:
    return {
        key: item
        for line in value.splitlines()
        if "=" in line
        for key, item in (line.split("=", 1),)
    }


def path_is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


class Promotion:
    def __init__(
        self,
        repository: Path,
        manifest_path: Path,
        installer: Path,
        work_dir: Path,
        state_dir: Path,
        source_commit: str,
        prefix: Path | None = None,
    ) -> None:
        self.repository = repository.expanduser().resolve()
        self.manifest_path = manifest_path.expanduser().resolve()
        self.installer = installer.expanduser().resolve()
        self.work_dir = work_dir.expanduser().resolve()
        self.state_dir = state_dir.expanduser().resolve()
        self.source_commit = source_commit
        self.prefix = (
            prefix.expanduser().resolve()
            if prefix is not None
            else (Path.home() / ".local/share/wineprefixes/uu-remote").resolve()
        )
        self.snapshot_prefix = self.work_dir / "snapshot-prefix"
        self.partial_snapshot = self.work_dir / "snapshot-prefix.partial"
        self.marker = self.state_dir / "promotion-in-progress.json"
        self.result_path = self.work_dir / "result.json"
        self.log_path = self.work_dir / "promotion.log"
        self.stop_prefix = self.repository / "scripts/stop-wine-prefix"
        self.username = pwd.getpwuid(os.getuid()).pw_name
        self.systemctl_user = [
            "/usr/bin/env",
            f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{os.getuid()}/bus",
            "/usr/bin/systemctl",
            "--user",
        ]

    def service_state(self, unit: str, *, user: bool) -> dict[str, str]:
        base = self.systemctl_user if user else ["/usr/bin/systemctl"]
        result = command(
            [
                *base,
                "show",
                unit,
                "--property=ActiveState",
                "--property=SubState",
                "--property=MainPID",
            ],
            timeout=20,
        )
        if result.returncode != 0:
            raise PromotionError(f"cannot query {unit}: {command_error(result)}")
        properties = parse_properties(result.stdout)
        if "ActiveState" not in properties:
            raise PromotionError(f"{unit} returned no service state")
        return properties

    def verify_checkout(self, acceptance: dict[str, Any]) -> None:
        if not re.fullmatch(r"[0-9a-f]{40,64}", self.source_commit):
            raise PromotionError("promotion source commit is invalid")
        head = command(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repository,
            timeout=30,
        )
        if head.returncode != 0 or head.stdout.strip() != self.source_commit:
            raise PromotionError("promotion checkout is not at the pinned source commit")
        if not path_is_within(self.manifest_path, self.repository):
            raise PromotionError("release manifest is outside the promotion checkout")
        relative_manifest = self.manifest_path.relative_to(self.repository)
        rendered = command(
            ["git", "show", f"HEAD:{relative_manifest.as_posix()}"],
            cwd=self.repository,
            timeout=30,
        )
        if (
            rendered.returncode != 0
            or rendered.stdout.encode("utf-8") != self.manifest_path.read_bytes()
        ):
            raise PromotionError("release manifest differs from the pinned commit")
        evidence = relative_repository_path(
            str(acceptance["evidence"]), "acceptance.evidence"
        )
        evidence_check = command(
            ["git", "cat-file", "-e", f"HEAD:{evidence.as_posix()}"],
            cwd=self.repository,
            timeout=30,
        )
        if evidence_check.returncode != 0:
            raise PromotionError("acceptance evidence is absent from the pinned commit")

    def current_runtime_check(self) -> None:
        installed_manifest = self.prefix / "compat/release-manifest.json"
        installed = load_manifest(installed_manifest)
        uu_bin = (
            self.prefix
            / "drive_c/Program Files/Netease/GameViewer/bin"
        )
        server = uu_bin / installed.server_filename
        result = command(
            [
                sys.executable,
                str(self.repository / "scripts/patch-gameviewer.py"),
                "verify",
                str(server),
                "--manifest",
                str(installed_manifest),
                "--expect",
                "patched",
            ],
            cwd=self.repository,
            timeout=180,
        )
        if result.returncode != 0:
            raise PromotionError(
                "current installed UU binary is not the audited patched build: "
                + command_error(result)
            )
        healthd_backup = (
            uu_bin / f"{installed.healthd_filename}.uu-original"
        )
        if (
            not healthd_backup.is_file()
            or sha256_file(healthd_backup)
            != installed.healthd_original_sha256
        ):
            raise PromotionError(
                "current health-monitor rollback backup is not audited"
            )
        for pattern, label in (
            (r"GameViewerServer\.exe", "UU server"),
            (r"sdl-freerdp\.exe", "desktop relay"),
        ):
            process = command(
                ["/usr/bin/pgrep", "-u", str(os.getuid()), "-f", pattern],
                timeout=20,
            )
            if process.returncode != 0 or not process.stdout.strip():
                raise PromotionError(f"current {label} is not running")

    def prefix_size(self) -> int:
        size = 0
        try:
            for item in self.prefix.rglob("*"):
                if item.is_file() and not item.is_symlink():
                    size += item.stat().st_size
        except OSError as error:
            raise PromotionError(f"cannot size the existing Wine prefix: {error}") from error
        return size

    def preflight(self) -> dict[str, Any]:
        if not self.prefix.is_dir():
            raise PromotionError(f"existing UU prefix is unavailable: {self.prefix}")
        if path_is_within(self.work_dir, self.prefix) or path_is_within(
            self.prefix, self.work_dir
        ):
            raise PromotionError("promotion work directory and Wine prefix overlap")
        manifest = load_manifest(self.manifest_path)
        acceptance = validate_acceptance(dict(manifest.raw))
        self.verify_checkout(acceptance)
        if not self.installer.is_file():
            raise PromotionError(f"approved installer is unavailable: {self.installer}")
        if sha256_file(self.installer) != manifest.installer_sha256:
            raise PromotionError("installer hash does not match the approved manifest")
        installed_path = self.prefix / "compat/release-manifest.json"
        installed = load_json(installed_path)
        installed_version = str(installed.get("version", ""))
        if version_key(manifest.version) <= version_key(installed_version):
            raise PromotionError(
                f"target {manifest.version} is not newer than installed "
                f"{installed_version}"
            )
        before_login = login_state(self.prefix, self.username)
        if not login_state_is_usable(before_login):
            raise PromotionError(
                "existing UU login state cannot be verified; refusing an update "
                "that could require re-login"
            )
        for required in (
            self.repository / "install.sh",
            self.stop_prefix,
            self.repository / "scripts/verify.sh",
        ):
            if not required.is_file():
                raise PromotionError(f"promotion checkout is missing {required.name}")
        if self.prefix.parent.stat().st_dev != self.state_dir.stat().st_dev:
            raise PromotionError(
                "promotion state and Wine prefix must share a filesystem for "
                "atomic rollback"
            )
        bridge = self.service_state("uu-remote-bridge.service", user=True)
        if bridge.get("ActiveState") != "active":
            raise PromotionError("UU bridge is not healthy and active before promotion")
        xrdp = self.service_state("xrdp.service", user=False)
        self.current_runtime_check()
        prefix_bytes = self.prefix_size()
        free_bytes = shutil.disk_usage(self.state_dir).free
        required_bytes = prefix_bytes + 1024 * 1024 * 1024
        if free_bytes < required_bytes:
            raise PromotionError(
                "insufficient free space for a complete login-preserving prefix "
                "snapshot"
            )
        return {
            "version": manifest.version,
            "installed_version": installed_version,
            "installer_sha256": manifest.installer_sha256,
            "manifest_sha256": sha256_file(self.manifest_path),
            "acceptance": acceptance,
            "login_state": before_login,
            "bridge_state": bridge,
            "xrdp_state": xrdp,
            "required_snapshot_bytes": required_bytes,
            "free_bytes": free_bytes,
        }

    def write_marker(self, phase: str, preflight: dict[str, Any]) -> None:
        atomic_json(
            self.marker,
            {
                "schema_version": 1,
                "phase": phase,
                "created_at": int(time.time()),
                "repository": str(self.repository),
                "source_commit": self.source_commit,
                "work_dir": str(self.work_dir),
                "prefix": str(self.prefix),
                "snapshot_prefix": str(self.snapshot_prefix),
                "target_version": preflight["version"],
                "bridge_was_active": (
                    preflight["bridge_state"].get("ActiveState") == "active"
                ),
            },
        )

    def stop_live_uu(self) -> None:
        stopped = command(
            [*self.systemctl_user, "stop", "uu-remote-bridge.service"],
            timeout=90,
        )
        if stopped.returncode != 0:
            raise PromotionError(
                "could not stop the UU bridge cleanly: " + command_error(stopped)
            )
        prefix_stopped = command(
            [str(self.stop_prefix), str(self.prefix)],
            cwd=self.repository,
            timeout=30,
        )
        if prefix_stopped.returncode != 0:
            raise PromotionError(
                "could not stop the UU Wine prefix: " + command_error(prefix_stopped)
            )

    def start_live_uu(self) -> None:
        result = command(
            [*self.systemctl_user, "start", "uu-remote-bridge.service"],
            timeout=90,
        )
        if result.returncode != 0:
            raise PromotionError(
                "could not start the UU bridge: " + command_error(result)
            )

    def snapshot(self, preflight: dict[str, Any]) -> dict[str, Any]:
        if self.snapshot_prefix.exists() or self.partial_snapshot.exists():
            raise PromotionError("promotion snapshot destination already exists")
        stopped_login = login_state(self.prefix, self.username)
        if not login_state_is_usable(stopped_login):
            raise PromotionError("UU login state became unverifiable after a clean stop")
        copied = command(
            [
                "/bin/cp",
                "-a",
                "--reflink=auto",
                "--sparse=always",
                str(self.prefix),
                str(self.partial_snapshot),
            ],
            timeout=1800,
            log=self.log_path,
        )
        if copied.returncode != 0 or not self.partial_snapshot.is_dir():
            raise PromotionError("failed to snapshot the complete UU Wine prefix")
        self.partial_snapshot.replace(self.snapshot_prefix)
        atomic_json(
            self.work_dir / "snapshot.json",
            {
                "schema_version": 1,
                "created_at": int(time.time()),
                "prefix": str(self.prefix),
                "snapshot_prefix": str(self.snapshot_prefix),
                "installed_version": preflight["installed_version"],
                "login_state": stopped_login,
            },
        )
        return stopped_login

    def run_installer(self) -> None:
        environment = dict(os.environ)
        environment["WINEPREFIX"] = str(self.prefix)
        installed = command(
            [
                str(self.repository / "install.sh"),
                "--skip-packages",
                "--skip-account-login",
                "--no-start",
                "--prefix-only",
                "--upgrade-existing",
                "--release-manifest",
                str(self.manifest_path),
                "--uu-installer",
                str(self.installer),
            ],
            cwd=self.repository,
            env=environment,
            timeout=3600,
            log=self.log_path,
        )
        if installed.returncode != 0:
            raise PromotionError("approved UU installer or patch preparation failed")

    def verify_runtime(self, stability_seconds: int) -> None:
        environment = dict(os.environ)
        environment["WINEPREFIX"] = str(self.prefix)
        verify = self.repository / "scripts/verify.sh"
        first = command(
            [str(verify), "--quick"],
            cwd=self.repository,
            env=environment,
            timeout=180,
        )
        if first.returncode != 0:
            raise PromotionError(
                "new UU runtime failed initial verification: " + command_error(first)
            )
        time.sleep(stability_seconds)
        second = command(
            [str(verify), "--quick"],
            cwd=self.repository,
            env=environment,
            timeout=180,
        )
        if second.returncode != 0:
            raise PromotionError(
                "new UU runtime failed the stability verification: "
                + command_error(second)
            )

    def recover(self) -> dict[str, Any]:
        marker = load_json(self.marker)
        if marker.get("schema_version") != 1:
            raise PromotionError("promotion recovery marker has an unknown schema")
        expected = {
            "work_dir": str(self.work_dir),
            "prefix": str(self.prefix),
            "snapshot_prefix": str(self.snapshot_prefix),
        }
        for field, value in expected.items():
            if marker.get(field) != value:
                raise PromotionError(f"promotion recovery marker has unsafe {field}")
        bridge_was_active = marker.get("bridge_was_active") is True
        snapshot_restored = False
        failed_prefix: Path | None = None
        if self.snapshot_prefix.is_dir():
            self.stop_live_uu()
            failed_prefix = self.work_dir / f"failed-prefix-{int(time.time())}"
            if self.prefix.exists():
                self.prefix.replace(failed_prefix)
            self.snapshot_prefix.replace(self.prefix)
            snapshot_restored = True
        if bridge_was_active:
            self.start_live_uu()
        self.marker.unlink(missing_ok=True)
        return {
            "rolled_back": snapshot_restored,
            "original_prefix_resumed": not snapshot_restored,
            "failed_prefix": (
                str(failed_prefix)
                if failed_prefix is not None and failed_prefix.exists()
                else None
            ),
        }

    def apply(self) -> dict[str, Any]:
        if self.marker.exists():
            raise PromotionError(
                "another promotion marker exists; recover it before starting"
            )
        preflight = self.preflight()
        self.work_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
        self.write_marker("preparing", preflight)
        try:
            self.stop_live_uu()
            stopped_login = self.snapshot(preflight)
            self.write_marker("snapshot-ready", preflight)
            self.run_installer()
            after_login = login_state(self.prefix, self.username)
            if not login_state_is_preserved(stopped_login, after_login):
                raise PromotionError("UU login/account state was not preserved exactly")
            installed_manifest = self.prefix / "compat/release-manifest.json"
            if sha256_file(installed_manifest) != preflight["manifest_sha256"]:
                raise PromotionError("installed manifest is not the accepted target")
            self.write_marker("verifying", preflight)
            self.start_live_uu()
            self.verify_runtime(int(preflight["acceptance"]["stability_seconds"]))
            after_xrdp = self.service_state("xrdp.service", user=False)
            if (
                after_xrdp.get("ActiveState")
                != preflight["xrdp_state"].get("ActiveState")
            ):
                raise PromotionError("XRDP active state changed during UU-only promotion")
            self.marker.unlink(missing_ok=True)
            result = {
                "status": "promoted",
                "version": preflight["version"],
                "login_preserved": True,
                "xrdp_unchanged": True,
                "xrdp_pid_changed_independently": (
                    after_xrdp.get("MainPID")
                    != preflight["xrdp_state"].get("MainPID")
                ),
                "rollback_snapshot": str(self.snapshot_prefix),
            }
            atomic_json(self.result_path, result)
            return result
        except Exception as error:
            rollback: dict[str, Any] | None = None
            try:
                if self.marker.exists():
                    rollback = self.recover()
            except Exception as rollback_error:
                rollback = {"rolled_back": False, "error": str(rollback_error)}
            result = {
                "status": "failed",
                "error": str(error),
                "rollback": rollback,
            }
            self.work_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            atomic_json(self.result_path, result)
            raise PromotionError(str(error)) from error


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "apply", "recover", "rollback"))
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--installer", type=Path)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--source-commit", default="")
    parser.add_argument("--prefix", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command in ("check", "apply") and (
        args.manifest is None
        or args.installer is None
        or not args.source_commit
    ):
        print(
            "promotion check/apply requires --manifest, --installer, and "
            "--source-commit",
            file=sys.stderr,
        )
        return 2
    promotion = Promotion(
        args.repository,
        args.manifest or Path("/nonexistent"),
        args.installer or Path("/nonexistent"),
        args.work_dir,
        args.state_dir,
        args.source_commit,
        args.prefix,
    )
    try:
        if args.command in ("recover", "rollback"):
            result = promotion.recover()
        elif args.command == "check":
            result = promotion.preflight()
        else:
            result = promotion.apply()
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ManifestError, PromotionError, subprocess.SubprocessError) as error:
        print(f"promotion error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
