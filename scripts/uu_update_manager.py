#!/usr/bin/env python3
"""Low-disruption UU update checks and resumable Codex repair orchestration."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import selectors
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


DEFAULT_ENDPOINT = "https://api.nrd.nie.163.com/api/v1/release/dl/1?channel=gwqd"
VERSION_RE = re.compile(r"(?<!\d)(\d+(?:\.\d+){2,3})(?!\d)")
TASK_ID_RE = re.compile(r"[^A-Za-z0-9._-]+")
TERMINAL_PHASES = {"blocked", "no-change", "ready-for-review"}


class UpdateError(RuntimeError):
    """An expected updater failure with an operator-readable message."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


def load_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.is_file():
        if default is not None:
            return dict(default)
        raise UpdateError(f"missing JSON file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise UpdateError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise UpdateError(f"expected a JSON object in {path}")
    return value


def sanitize_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def version_key(value: str) -> tuple[int, ...]:
    if not re.fullmatch(r"\d+(?:\.\d+){2,3}", value):
        raise UpdateError(f"unsupported UU version format: {value}")
    parts = tuple(int(part) for part in value.split("."))
    return parts + (0,) * (4 - len(parts))


def release_version(*values: str) -> str:
    matches: list[str] = []
    for value in values:
        matches.extend(VERSION_RE.findall(value or ""))
    if not matches:
        raise UpdateError("the official response did not contain a release version")
    return max(matches, key=lambda item: (len(item.split(".")), version_key(item)))


def disposition_filename(value: str) -> str:
    match = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", value, re.I)
    if not match:
        return ""
    return urllib.parse.unquote(match.group(1).strip())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def task_name(value: str) -> str:
    cleaned = TASK_ID_RE.sub("-", value).strip("-.")
    return cleaned[:96] or "task"


def command_output(
    command: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 60,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "no output"
        raise UpdateError(f"command failed ({' '.join(command)}): {detail[-1200:]}")
    return result


def codex_budget_from_rate_limits(
    payload: dict[str, Any], max_used_percent: int
) -> dict[str, Any]:
    limits = payload.get("rateLimitsByLimitId")
    selected: dict[str, Any] | None = None
    if isinstance(limits, dict):
        candidate = limits.get("codex")
        if isinstance(candidate, dict):
            selected = candidate
    if selected is None and isinstance(payload.get("rateLimits"), dict):
        selected = payload["rateLimits"]
    if selected is None:
        raise UpdateError("Codex did not report an included-usage rate limit")

    observed: list[float] = []
    resets: list[int] = []
    for key in ("primary", "secondary"):
        window = selected.get(key)
        if not isinstance(window, dict):
            continue
        value = window.get("usedPercent")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            observed.append(float(value))
        reset_at = window.get("resetsAt")
        if isinstance(reset_at, (int, float)) and not isinstance(reset_at, bool):
            resets.append(int(reset_at))
    if not observed:
        raise UpdateError("Codex did not report included-usage percentages")

    reached = selected.get("rateLimitReachedType") is not None
    spend_reached = selected.get("spendControlReached") is True
    highest = max(observed)
    return {
        "verified": True,
        "allowed": highest <= max_used_percent and not reached and not spend_reached,
        "limit_percent": max_used_percent,
        "observed_used_percent": highest,
        "resets_at": max(resets) if resets else None,
        "credits_considered": False,
    }


def codex_rate_limits(timeout: int = 15) -> dict[str, Any]:
    try:
        process = subprocess.Popen(
            ["codex", "app-server", "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
    except OSError as error:
        raise UpdateError(f"cannot start Codex rate-limit service: {error}") from error
    assert process.stdin is not None
    assert process.stdout is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout
    try:
        initialize = {
            "id": 1,
            "method": "initialize",
            "params": {
                "clientInfo": {
                    "name": "uu-remote-update-manager",
                    "version": "1",
                }
            },
        }
        process.stdin.write(json.dumps(initialize) + "\n")
        process.stdin.flush()
        initialized = False
        requested = False
        while time.monotonic() < deadline:
            remaining = max(0.1, deadline - time.monotonic())
            if not selector.select(remaining):
                continue
            line = process.stdout.readline()
            if not line:
                break
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if message.get("id") == 1 and "result" in message and not initialized:
                process.stdin.write(json.dumps({"method": "initialized"}) + "\n")
                request = {"id": 2, "method": "account/rateLimits/read"}
                process.stdin.write(json.dumps(request) + "\n")
                process.stdin.flush()
                initialized = True
                requested = True
            elif message.get("id") == 2:
                result = message.get("result")
                if isinstance(result, dict):
                    return result
                raise UpdateError("Codex returned an invalid rate-limit response")
        detail = "request timed out" if requested else "initialization failed"
        raise UpdateError(f"Codex rate-limit {detail}")
    except (OSError, BrokenPipeError) as error:
        raise UpdateError(f"cannot query Codex rate limits: {error}") from error
    finally:
        selector.close()
        with contextlib.suppress(OSError):
            process.stdin.close()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)


@dataclass(frozen=True)
class Config:
    path: Path
    repository: Path
    state_dir: Path
    remote: str
    branch: str
    track: str
    endpoint: str
    codex_model: str
    codex_reasoning_effort: str
    codex_timeout_seconds: int
    codex_max_used_percent: int
    idle_minutes: int
    auto_reinstall_known_good: bool
    max_download_bytes: int

    @classmethod
    def read(cls, path: Path) -> "Config":
        raw = load_json(path)
        if raw.get("schema_version") != 1:
            raise UpdateError(f"unsupported updater configuration in {path}")
        repository = Path(str(raw.get("repository", ""))).expanduser().resolve()
        if not (repository / ".git").exists():
            raise UpdateError(f"configured repository is unavailable: {repository}")
        state_default = Path(
            os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))
        ) / "uu-remote-updater"
        state_dir = Path(str(raw.get("state_dir", state_default))).expanduser().resolve()
        model = str(raw.get("codex_model", "")).strip()
        effort = str(raw.get("codex_reasoning_effort", "")).strip()
        if not model or not effort:
            raise UpdateError("the updater needs a Codex model and reasoning effort")
        max_used_percent = int(raw.get("codex_max_used_percent", 20))
        if not 0 <= max_used_percent <= 100:
            raise UpdateError("codex_max_used_percent must be between 0 and 100")
        return cls(
            path=path,
            repository=repository,
            state_dir=state_dir,
            remote=str(raw.get("remote", "origin")),
            branch=str(raw.get("branch", "main")),
            track=str(raw.get("track", "track-rdp-broker-20260724")),
            endpoint=str(raw.get("endpoint", DEFAULT_ENDPOINT)),
            codex_model=model,
            codex_reasoning_effort=effort,
            codex_timeout_seconds=max(300, int(raw.get("codex_timeout_seconds", 5400))),
            codex_max_used_percent=max_used_percent,
            idle_minutes=max(5, int(raw.get("idle_minutes", 45))),
            auto_reinstall_known_good=bool(raw.get("auto_reinstall_known_good", True)),
            max_download_bytes=max(
                1024 * 1024,
                int(raw.get("max_download_bytes", 1024 * 1024 * 1024)),
            ),
        )


class Manager:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.state_dir = config.state_dir
        self.status_path = self.state_dir / "status.json"
        self.pending_path = self.state_dir / "pending.json"
        self.tasks_dir = self.state_dir / "tasks"
        self.downloads_dir = self.state_dir / "downloads"
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.state_dir, 0o700)

    @contextlib.contextmanager
    def lock(self) -> Iterator[None]:
        path = self.state_dir / "maintenance.lock"
        with path.open("a+", encoding="utf-8") as stream:
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise UpdateError("another UU maintenance action is already running") from error
            yield

    def write_status(self, phase: str, **extra: Any) -> None:
        current = load_json(self.status_path, default={})
        current.update(
            {
                "schema_version": 1,
                "updated_at": utc_now(),
                "phase": phase,
                "track": self.config.track,
                "codex_model": self.config.codex_model,
                "codex_reasoning_effort": self.config.codex_reasoning_effort,
                "maintenance_idle_minutes": self.config.idle_minutes,
            }
        )
        current.update(extra)
        atomic_json(self.status_path, current)

    def fetch_repository(self) -> None:
        result = command_output(
            [
                "git",
                "fetch",
                "--quiet",
                "--prune",
                "--tags",
                self.config.remote,
                self.config.branch,
            ],
            cwd=self.config.repository,
            timeout=180,
        )
        if result.returncode != 0:
            raise UpdateError(f"repository fetch failed: {result.stderr.strip()[-1200:]}")

    def approved_releases(self) -> list[dict[str, Any]]:
        releases: list[dict[str, Any]] = []
        reference = f"refs/remotes/{self.config.remote}/{self.config.branch}"
        listing = command_output(
            ["git", "ls-tree", "-r", "--name-only", reference, "--", "patches"],
            cwd=self.config.repository,
            timeout=30,
            check=True,
        )
        paths = [
            item
            for item in listing.stdout.splitlines()
            if re.fullmatch(r"patches/uu-remote-[^/]+\.json", item)
        ]
        for relative in sorted(paths):
            try:
                rendered = command_output(
                    ["git", "show", f"{reference}:{relative}"],
                    cwd=self.config.repository,
                    timeout=30,
                    check=True,
                ).stdout
                raw = json.loads(rendered)
                if not isinstance(raw, dict):
                    continue
                if raw.get("review_status") != "approved":
                    continue
                installer = raw.get("installer")
                if not isinstance(installer, dict):
                    continue
                version = str(raw["version"])
                version_key(version)
                releases.append(
                    {
                        "version": version,
                        "installer_sha256": str(installer["sha256"]),
                        "manifest": f"{reference}:{relative}",
                    }
                )
            except (json.JSONDecodeError, KeyError, TypeError, ValueError, UpdateError):
                continue
        return sorted(releases, key=lambda item: version_key(str(item["version"])))

    def installed_release(self) -> dict[str, str]:
        manifest = (
            Path.home()
            / ".local/share/wineprefixes/uu-remote/compat/release-manifest.json"
        )
        if not manifest.is_file():
            return {"version": "unknown", "manifest": str(manifest)}
        raw = load_json(manifest)
        return {"version": str(raw.get("version", "unknown")), "manifest": str(manifest)}

    def probe_endpoint(self) -> dict[str, Any]:
        headers = {"User-Agent": "UU-Remote-Ubuntu-Bridge-Updater/1"}
        request = urllib.request.Request(self.config.endpoint, headers=headers, method="HEAD")
        try:
            response = urllib.request.urlopen(request, timeout=30)
        except urllib.error.HTTPError as error:
            if error.code not in (403, 405):
                raise UpdateError(f"official update endpoint returned HTTP {error.code}") from error
            request = urllib.request.Request(
                self.config.endpoint,
                headers=headers | {"Range": "bytes=0-0"},
                method="GET",
            )
            response = urllib.request.urlopen(request, timeout=30)
        except (OSError, urllib.error.URLError) as error:
            raise UpdateError(f"cannot reach the official update endpoint: {error}") from error

        with response:
            final_url = response.geturl()
            disposition = response.headers.get("Content-Disposition", "")
            filename = disposition_filename(disposition)
            if not filename:
                filename = Path(urllib.parse.urlsplit(final_url).path).name
            version = release_version(filename, urllib.parse.urlsplit(final_url).path)
            length_value = response.headers.get("Content-Length", "")
            length = int(length_value) if length_value.isdigit() else 0
            return {
                "checked_at": utc_now(),
                "version": version,
                "filename": filename,
                "final_url": sanitize_url(final_url),
                "etag": response.headers.get("ETag", "").strip('"'),
                "last_modified": response.headers.get("Last-Modified", ""),
                "content_length": length,
            }

    def download_release(self, metadata: dict[str, Any]) -> Path:
        version = str(metadata["version"])
        destination = self.downloads_dir / f"uu-{task_name(version)}.exe"
        part = destination.with_suffix(".exe.part")
        self.downloads_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        request = urllib.request.Request(
            self.config.endpoint,
            headers={"User-Agent": "UU-Remote-Ubuntu-Bridge-Updater/1"},
        )
        total = 0
        try:
            with urllib.request.urlopen(request, timeout=60) as response, part.open("wb") as stream:
                declared = response.headers.get("Content-Length", "")
                if declared.isdigit() and int(declared) > self.config.max_download_bytes:
                    raise UpdateError("the reported UU installer exceeds the configured size limit")
                for block in iter(lambda: response.read(1024 * 1024), b""):
                    total += len(block)
                    if total > self.config.max_download_bytes:
                        raise UpdateError("the UU installer exceeded the configured size limit")
                    stream.write(block)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            part.unlink(missing_ok=True)
            raise
        if total == 0:
            part.unlink(missing_ok=True)
            raise UpdateError("the official endpoint returned an empty installer")
        part.chmod(0o600)
        part.replace(destination)
        return destination

    def download_metadata_path(self, version: str) -> Path:
        return self.downloads_dir / f"uu-{task_name(version)}.json"

    def record_download(
        self, metadata: dict[str, Any], installer: Path, installer_hash: str
    ) -> None:
        atomic_json(
            self.download_metadata_path(str(metadata["version"])),
            {
                "schema_version": 1,
                "version": str(metadata["version"]),
                "filename": installer.name,
                "etag": str(metadata.get("etag", "")),
                "last_modified": str(metadata.get("last_modified", "")),
                "content_length": int(metadata.get("content_length", 0)),
                "installer_sha256": installer_hash,
                "verified_at": utc_now(),
            },
        )

    def cached_download(self, metadata: dict[str, Any]) -> tuple[Path, str] | None:
        version = str(metadata["version"])
        installer = self.downloads_dir / f"uu-{task_name(version)}.exe"
        sidecar = self.download_metadata_path(version)
        if not installer.is_file() or not sidecar.is_file():
            return None
        cached = load_json(sidecar)
        expected_length = int(metadata.get("content_length", 0))
        metadata_matches = (
            cached.get("version") == version
            and cached.get("etag") == str(metadata.get("etag", ""))
            and cached.get("last_modified") == str(metadata.get("last_modified", ""))
            and cached.get("content_length") == expected_length
        )
        if not metadata_matches:
            return None
        if expected_length and installer.stat().st_size != expected_length:
            return None
        cached_hash = str(cached.get("installer_sha256", ""))
        if not re.fullmatch(r"[0-9a-f]{64}", cached_hash):
            return None
        if sha256_file(installer) != cached_hash:
            return None
        return installer, cached_hash

    def remote_base_commit(self) -> str:
        reference = f"refs/remotes/{self.config.remote}/{self.config.branch}"
        result = command_output(
            ["git", "rev-parse", "--verify", reference],
            cwd=self.config.repository,
            check=True,
        )
        return result.stdout.strip()

    def create_repair_checkout(self, task_dir: Path) -> tuple[Path, str]:
        repair_repo = task_dir / "repo"
        if repair_repo.exists():
            base = command_output(
                ["git", "rev-parse", "HEAD"], cwd=repair_repo, check=True
            ).stdout.strip()
            return repair_repo, base
        base = self.remote_base_commit()
        command_output(
            [
                "git",
                "clone",
                "--quiet",
                "--no-hardlinks",
                str(self.config.repository),
                str(repair_repo),
            ],
            timeout=300,
            check=True,
        )
        command_output(
            ["git", "checkout", "--quiet", "-b", f"automated-repair/{task_dir.name}", base],
            cwd=repair_repo,
            check=True,
        )
        command_output(
            ["git", "remote", "set-url", "--push", "origin", "disabled://automatic-repair"],
            cwd=repair_repo,
            check=True,
        )
        return repair_repo, base

    def stage_candidate(self, installer: Path, task_dir: Path) -> dict[str, Any]:
        stage_dir = task_dir / "stage"
        log_path = task_dir / "stage.log"
        command = [
            str(self.config.repository / "scripts/stage-uu-release.sh"),
            "--installer",
            str(installer),
            "--output",
            str(stage_dir),
            "--keep-workdir",
        ]
        with log_path.open("w", encoding="utf-8") as stream:
            result = subprocess.run(
                command,
                cwd=self.config.repository,
                stdin=subprocess.DEVNULL,
                stdout=stream,
                stderr=subprocess.STDOUT,
                timeout=900,
                check=False,
            )
        log_path.chmod(0o600)
        return {
            "returncode": result.returncode,
            "stage_dir": str(stage_dir),
            "server_available": (stage_dir / "GameViewerServer.exe").is_file(),
            "healthd_available": (stage_dir / "GameViewerHealthd.exe").is_file(),
            "log": str(log_path),
            "sandbox_executed": False,
        }

    def write_context(self, task: dict[str, Any], repair_repo: Path) -> Path:
        context_path = repair_repo / "build/automated-repair/CONTEXT.md"
        context_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        details = task.get("details", {})
        lines = [
            "# Automated UU Repair Context",
            "",
            f"- Task: `{task['id']}`",
            f"- Kind: `{task['kind']}`",
            f"- Created: `{task['created_at']}`",
            f"- Selected behavior track: `{self.config.track}`",
            f"- Base commit: `{task['base_commit']}`",
            f"- Codex model: `{self.config.codex_model}`",
            f"- Reasoning effort: `{self.config.codex_reasoning_effort}`",
            "",
            "## Evidence",
            "",
            "```json",
            json.dumps(details, indent=2, sort_keys=True),
            "```",
            "",
            "## Non-negotiable boundaries",
            "",
            "- Preserve the selected input track and its known-good defaults.",
            "- Work only in this repair checkout. Do not edit the live Wine prefix,",
            "  user configuration, systemd units, account state, or the source clone.",
            "- Do not run `sudo`, push, publish proprietary files, or execute an unknown",
            "  UU installer outside the repository's explicit staging sandbox.",
            "- Unknown binaries remain fail-closed. Candidate matching and Codex review",
            "  may create a draft manifest, but cannot mark it `approved`.",
            "- Keep proprietary binaries, raw logs, tokens, host identifiers, and build",
            "  output ignored and uncommitted.",
            "- Run focused tests and the full proprietary-binary-free unit suite.",
            "",
            "Read `docs/upstream-maintenance.md`, `docs/security.md`,",
            "`docs/release-tracks.md`, and `docs/automatic-updates.md` before editing.",
        ]
        context_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        context_path.chmod(0o600)
        return context_path

    def queue_task(self, kind: str, identity: str, details: dict[str, Any]) -> dict[str, Any]:
        task_id = task_name(f"{kind}-{identity}")
        task_dir = self.tasks_dir / task_id
        task_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        existing_path = task_dir / "task.json"
        if existing_path.is_file():
            existing = load_json(existing_path)
            if existing.get("phase") in TERMINAL_PHASES:
                self.write_status(
                    str(existing["phase"]),
                    active_task=task_id,
                    message="the existing repair result is retained for review",
                )
                return existing
            atomic_json(self.pending_path, existing)
            self.write_status(
                "repair-queued",
                active_task=task_id,
                message="the existing Codex repair will resume",
            )
            return existing
        repair_repo, base = self.create_repair_checkout(task_dir)
        task = {
            "schema_version": 1,
            "id": task_id,
            "kind": kind,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "phase": "queued",
            "attempts": 0,
            "thread_id": None,
            "base_commit": base,
            "repair_repo": str(repair_repo),
            "details": details,
        }
        task["context"] = str(self.write_context(task, repair_repo))
        atomic_json(existing_path, task)
        atomic_json(self.pending_path, task)
        self.write_status("repair-queued", active_task=task_id)
        return task

    def check(self) -> None:
        previous_status = load_json(self.status_path, default={})
        self.write_status("checking", last_check_started_at=utc_now())
        self.fetch_repository()
        approved = self.approved_releases()
        if not approved:
            raise UpdateError("the repository has no approved UU release manifests")
        latest_approved = approved[-1]
        installed = self.installed_release()
        observed = self.probe_endpoint()
        self.write_status(
            "checked",
            last_check_completed_at=utc_now(),
            installed_release=installed,
            latest_approved_release=latest_approved,
            observed_release=observed,
        )
        observed_key = version_key(str(observed["version"]))
        approved_key = version_key(str(latest_approved["version"]))
        if observed_key < approved_key:
            self.write_status(
                "current",
                last_check_completed_at=utc_now(),
                installed_release=installed,
                latest_approved_release=latest_approved,
                observed_release=observed,
                message="official endpoint is older than the approved baseline; no live change",
            )
            return

        previous_observed = previous_status.get("observed_release")
        if (
            observed_key == approved_key
            and isinstance(previous_observed, dict)
            and previous_observed.get("etag") == observed.get("etag")
            and previous_observed.get("last_modified")
            == observed.get("last_modified")
            and previous_observed.get("content_length") == observed.get("content_length")
            and previous_observed.get("installer_sha256")
            == latest_approved["installer_sha256"]
        ):
            observed["installer_sha256"] = previous_observed["installer_sha256"]
            self.write_status(
                "current",
                last_check_completed_at=utc_now(),
                installed_release=installed,
                latest_approved_release=latest_approved,
                observed_release=observed,
                message="official release metadata and cached full hash match the approved baseline",
            )
            return

        cached = self.cached_download(observed)
        if cached is None:
            installer = self.download_release(observed)
            installer_hash = sha256_file(installer)
            self.record_download(observed, installer, installer_hash)
        else:
            installer, installer_hash = cached
        observed["installer_sha256"] = installer_hash
        matching = next(
            (item for item in approved if item["installer_sha256"] == installer_hash), None
        )
        if matching and version_key(str(matching["version"])) == observed_key:
            if observed_key == approved_key:
                self.write_status(
                    "current",
                    last_check_completed_at=utc_now(),
                    installed_release=installed,
                    latest_approved_release=matching,
                    observed_release=observed,
                    message="official installer full hash matches the approved baseline",
                )
                return
            self.write_status(
                "approved-release-detected",
                observed_release=observed,
                latest_approved_release=matching,
                message="approved installer is cached; deployment remains maintenance-gated",
            )
            return

        identity = f"{observed['version']}-{installer_hash[:12]}"
        task_dir = self.tasks_dir / task_name(f"upstream-release-{identity}")
        existing_task = task_dir / "task.json"
        if existing_task.is_file():
            task = load_json(existing_task)
            if task.get("phase") in TERMINAL_PHASES:
                self.write_status(
                    str(task["phase"]),
                    active_task=task["id"],
                    observed_release=observed,
                    message="the existing repair result is retained for review",
                )
            else:
                atomic_json(self.pending_path, task)
                self.write_status(
                    "repair-queued",
                    active_task=task["id"],
                    observed_release=observed,
                    message="the existing Codex repair will resume",
                )
            return
        task_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        stage = self.stage_candidate(installer, task_dir)
        details = {
            "observed_release": observed,
            "installed_release": installed,
            "latest_approved_release": latest_approved,
            "installer": str(installer),
            "staging": stage,
            "note": (
                "Archive-only staging is automatic. If this wrapper cannot be extracted, "
                "an operator must explicitly authorize the networkless systemd sandbox."
            ),
        }
        self.queue_task("upstream-release", identity, details)

    def health(self) -> dict[str, Any]:
        issues: list[str] = []
        service = command_output(
            [
                "systemctl",
                "--user",
                "show",
                "uu-remote-bridge.service",
                "--property=ActiveState",
                "--property=NRestarts",
            ],
            timeout=15,
        )
        service_properties = dict(
            line.split("=", 1)
            for line in service.stdout.splitlines()
            if "=" in line
        )
        if service_properties.get("ActiveState") != "active":
            issues.append("bridge-service-inactive")
        try:
            restart_count = int(service_properties.get("NRestarts", "0"))
        except ValueError:
            restart_count = 0
        if restart_count >= 3:
            issues.append("bridge-restart-storm")
        for label, pattern in (
            ("uu-server-missing", r"GameViewerServer\.exe"),
            ("freerdp-relay-missing", r"sdl-freerdp\.exe"),
        ):
            process = command_output(
                ["pgrep", "-u", str(os.getuid()), "-f", pattern], timeout=15
            )
            if process.returncode != 0:
                issues.append(label)

        bridge_environment = Path.home() / ".config/uu-remote-bridge/environment"
        rdp_port = "3390"
        if bridge_environment.is_file():
            for line in bridge_environment.read_text(encoding="utf-8").splitlines():
                if line.startswith("UURB_RDP_PORT="):
                    candidate = line.split("=", 1)[1].strip()
                    if candidate.isdigit() and 1024 <= int(candidate) <= 65535:
                        rdp_port = candidate
        relay = command_output(
            [
                "pgrep",
                "-o",
                "-u",
                str(os.getuid()),
                "-f",
                f"gnome-remote-desktop-daemon --rdp-port {rdp_port}",
            ],
            timeout=15,
        )
        relay_pid = relay.stdout.strip()
        if relay.returncode != 0 or not relay_pid.isdigit():
            issues.append("gnome-rdp-relay-missing")
        else:
            listener = command_output(
                ["ss", "-H", "-ltnp", f"sport = :{rdp_port}"], timeout=15
            )
            if f"pid={relay_pid}," not in listener.stdout:
                issues.append("rdp-listener-owner-mismatch")

        manifest = (
            Path.home()
            / ".local/share/wineprefixes/uu-remote/compat/release-manifest.json"
        )
        if not manifest.is_file():
            issues.append("installed-manifest-missing")
        return {
            "checked_at": utc_now(),
            "healthy": not issues,
            "issues": issues,
            "restart_count": restart_count,
            "rdp_port": int(rdp_port),
        }

    def restart_bridge(self) -> dict[str, Any]:
        result = command_output(
            ["systemctl", "--user", "restart", "uu-remote-bridge.service"],
            timeout=90,
        )
        for _ in range(24):
            health = self.health()
            if health["healthy"]:
                return {"returncode": result.returncode, "health": health}
            time.sleep(2.5)
        return {"returncode": result.returncode, "health": self.health()}

    def track_checkout(self, destination: Path) -> Path:
        if destination.exists():
            shutil.rmtree(destination)
        command_output(
            [
                "git",
                "clone",
                "--quiet",
                "--no-hardlinks",
                str(self.config.repository),
                str(destination),
            ],
            timeout=300,
            check=True,
        )
        command_output(
            ["git", "checkout", "--quiet", "--detach", self.config.track],
            cwd=destination,
            timeout=60,
            check=True,
        )
        return destination

    def reinstall_known_good(self) -> dict[str, Any]:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        work = self.state_dir / "reinstalls" / stamp
        checkout = self.track_checkout(work / "repo")
        log_path = work / "reinstall.log"
        work.mkdir(parents=True, exist_ok=True, mode=0o700)
        tests = command_output(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
            cwd=checkout,
            timeout=1200,
        )
        if tests.returncode != 0:
            log_path.write_text(tests.stdout + tests.stderr, encoding="utf-8")
            log_path.chmod(0o600)
            return {"attempted": False, "reason": "known-good checkout failed tests"}

        for builder, output in (
            ("scripts/build-compat.sh", "build/compat"),
            ("scripts/build-winpr.sh", "build/freerdp"),
            ("scripts/build-libei.sh", "build/libei"),
        ):
            path = checkout / builder
            if not path.is_file():
                continue
            built = command_output(
                [str(path), str(checkout / output)],
                cwd=checkout,
                timeout=2700,
            )
            with log_path.open("a", encoding="utf-8") as stream:
                stream.write(built.stdout)
                stream.write(built.stderr)
            if built.returncode != 0:
                log_path.chmod(0o600)
                return {"attempted": False, "reason": f"prebuild failed: {builder}"}

        secret = command_output(
            [
                "/usr/bin/secret-tool",
                "lookup",
                "service",
                "uu-desktop-bridge",
                "username",
                os.environ.get("USER", str(os.getuid())),
            ],
            timeout=20,
        )
        if secret.returncode != 0 or not secret.stdout:
            return {"attempted": False, "reason": "relay credential is unavailable"}

        snapshot = self.snapshot_live_runtime(work)
        with log_path.open("a", encoding="utf-8") as stream:
            result = subprocess.run(
                [
                    str(checkout / "install.sh"),
                    "--skip-packages",
                    "--skip-account-login",
                ],
                cwd=checkout,
                stdin=subprocess.DEVNULL,
                stdout=stream,
                stderr=subprocess.STDOUT,
                timeout=1800,
                check=False,
            )
        log_path.chmod(0o600)
        health = self.health()
        rollback: dict[str, Any] | None = None
        if result.returncode != 0 or not health["healthy"]:
            rollback = self.restore_live_runtime(snapshot)
            health = rollback["health"]
        return {
            "attempted": True,
            "returncode": result.returncode,
            "health": health,
            "log": str(log_path),
            "rolled_back": rollback is not None,
            "rollback": rollback,
        }

    def runtime_snapshot_paths(self) -> list[Path]:
        home = Path.home()
        wine_prefix = home / ".local/share/wineprefixes/uu-remote"
        uu_bin = wine_prefix / "drive_c/Program Files/Netease/GameViewer/bin"
        return [
            home / ".local/bin/uu-remote",
            home / ".local/bin/uu-remote-bridge",
            home / ".local/bin/uu-keyring-unlock",
            home / ".local/libexec/uu-connection-status",
            home / ".local/libexec/uu-remote-stop-wine-prefix",
            home / ".config/uu-remote-bridge/environment",
            home / ".config/systemd/user/uu-remote-bridge.service",
            home / ".config/systemd/user/uu-keyring-unlock.service",
            wine_prefix / "compat",
            wine_prefix / "drive_c/Program Files/FreeRDP",
            uu_bin / "GameViewerServer.exe",
            uu_bin / "GameViewerServer.exe.uu-original",
            uu_bin / "GameViewerHealthd.exe",
            uu_bin / "GameViewerHealthd.exe.uu-original",
        ]

    @staticmethod
    def copy_snapshot_item(source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if source.is_symlink():
            destination.symlink_to(os.readlink(source))
        elif source.is_dir():
            shutil.copytree(source, destination, symlinks=True)
        else:
            shutil.copy2(source, destination, follow_symlinks=False)

    @staticmethod
    def remove_snapshot_item(path: Path) -> None:
        if path.is_symlink() or path.is_file():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            shutil.rmtree(path)

    def snapshot_live_runtime(self, work: Path) -> Path:
        root = work / "snapshot"
        files = root / "files"
        home = Path.home().resolve()
        entries: list[dict[str, Any]] = []
        files.mkdir(parents=True, exist_ok=True, mode=0o700)
        for source in self.runtime_snapshot_paths():
            relative = source.relative_to(home)
            exists = source.exists() or source.is_symlink()
            entries.append({"relative": str(relative), "existed": exists})
            if exists:
                self.copy_snapshot_item(source, files / relative)
        atomic_json(root / "manifest.json", {"schema_version": 1, "entries": entries})
        return root

    def restore_live_runtime(self, snapshot: Path) -> dict[str, Any]:
        raw = load_json(snapshot / "manifest.json")
        entries = raw.get("entries")
        if not isinstance(entries, list):
            raise UpdateError("runtime rollback snapshot is malformed")
        command_output(
            ["systemctl", "--user", "stop", "uu-remote-bridge.service"], timeout=90
        )
        home = Path.home().resolve()
        for entry in entries:
            if not isinstance(entry, dict):
                raise UpdateError("runtime rollback entry is malformed")
            relative = Path(str(entry.get("relative", "")))
            if relative.is_absolute() or ".." in relative.parts:
                raise UpdateError("runtime rollback path escaped the home directory")
            destination = home / relative
            self.remove_snapshot_item(destination)
            if entry.get("existed") is True:
                self.copy_snapshot_item(snapshot / "files" / relative, destination)
        command_output(["systemctl", "--user", "daemon-reload"], timeout=30)
        start = command_output(
            ["systemctl", "--user", "start", "uu-remote-bridge.service"], timeout=90
        )
        for _ in range(24):
            health = self.health()
            if health["healthy"]:
                return {"returncode": start.returncode, "health": health}
            time.sleep(2.5)
        return {"returncode": start.returncode, "health": self.health()}

    def runtime_context(self, first: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        service = command_output(
            [
                "journalctl",
                "--user",
                "-u",
                "uu-remote-bridge.service",
                "--since=-30 min",
                "-n",
                "160",
                "--no-pager",
                "-o",
                "short-iso",
            ],
            timeout=30,
        )
        journal_path = self.state_dir / "latest-runtime-journal.txt"
        journal_path.write_text(service.stdout[-30000:], encoding="utf-8")
        journal_path.chmod(0o600)
        return {
            "initial_health": first,
            "health_after_restart": after,
            "journal": str(journal_path),
            "installed_release": self.installed_release(),
            "privacy": "journal remains local and must not be committed or quoted verbatim",
        }

    def monitor_health(self) -> None:
        first = self.health()
        if first["healthy"]:
            self.write_status("healthy", bridge_health=first)
            return
        time.sleep(20)
        confirmed = self.health()
        if confirmed["healthy"]:
            self.write_status("healthy", bridge_health=confirmed, message="transient issue cleared")
            return
        restarted = self.restart_bridge()
        if restarted["health"]["healthy"]:
            self.write_status(
                "self-healed",
                bridge_health=restarted["health"],
                message="the inactive relay recovered after one supervised restart",
            )
            return
        reinstall: dict[str, Any] = {"attempted": False, "reason": "disabled"}
        if self.config.auto_reinstall_known_good:
            reinstall = self.reinstall_known_good()
            if reinstall.get("health", {}).get("healthy"):
                action = (
                    "restored the previous runtime after a failed reinstall"
                    if reinstall.get("rolled_back")
                    else f"reinstalled known-good track {self.config.track}"
                )
                self.write_status(
                    "self-healed",
                    bridge_health=reinstall["health"],
                    message=action,
                )
                return
        details = self.runtime_context(first, restarted["health"])
        details["known_good_reinstall"] = reinstall
        identity = datetime.now().strftime("%Y%m%d-%H%M")
        self.queue_task("runtime-health", identity, details)

    def load_pending(self) -> dict[str, Any] | None:
        if not self.pending_path.is_file():
            return None
        return load_json(self.pending_path)

    def save_task(self, task: dict[str, Any]) -> None:
        task["updated_at"] = utc_now()
        task_dir = self.tasks_dir / str(task["id"])
        atomic_json(task_dir / "task.json", task)
        atomic_json(self.pending_path, task)

    def codex_command(self, task: dict[str, Any], resume: bool) -> list[str]:
        repair_repo = Path(str(task["repair_repo"]))
        schema = repair_repo / "scripts/codex-repair-result.schema.json"
        last_message = self.tasks_dir / str(task["id"]) / "last-message.json"
        common = [
            "--json",
            "--model",
            self.config.codex_model,
            "--config",
            f'model_reasoning_effort="{self.config.codex_reasoning_effort}"',
            "--config",
            'approval_policy="never"',
            "--output-schema",
            str(schema),
            "--output-last-message",
            str(last_message),
        ]
        if resume:
            prompt = (
                "Resume the interrupted UU repair. Re-read build/automated-repair/"
                "CONTEXT.md, preserve existing work and test results, and finish the same "
                "task. Keep every safety and review gate in that context."
            )
            return ["codex", "exec", "resume", *common, str(task["thread_id"]), prompt]
        prompt = (
            "Handle the automated UU maintenance task described in "
            "build/automated-repair/CONTEXT.md end to end inside this checkout. "
            "First read that context and its referenced project documentation. Inspect "
            "existing work before editing, use the repository's static audit tools, keep "
            "unknown binaries fail-closed, and run the complete test suite. Produce a "
            "reviewable repair or a precise blocked result; never approve your own binary "
            "manifest, touch the live installation, use sudo, commit, or push."
        )
        return [
            "codex",
            "exec",
            *common,
            "--sandbox",
            "workspace-write",
            "--cd",
            str(repair_repo),
            prompt,
        ]

    def run_codex(self, task: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        task_dir = self.tasks_dir / str(task["id"])
        events_path = task_dir / "codex-events.jsonl"
        stderr_path = task_dir / "codex-stderr.log"
        resume = bool(task.get("thread_id"))
        command = [
            "/usr/bin/timeout",
            "--signal=TERM",
            "--kill-after=30s",
            f"{self.config.codex_timeout_seconds}s",
            *self.codex_command(task, resume),
        ]
        task["phase"] = "codex-running"
        task["attempts"] = int(task.get("attempts", 0)) + 1
        task["last_attempt_started_at"] = utc_now()
        self.save_task(task)
        self.write_status("codex-running", active_task=task["id"])

        started = time.monotonic()
        with events_path.open("a", encoding="utf-8") as events, stderr_path.open(
            "a", encoding="utf-8"
        ) as errors:
            process = subprocess.Popen(
                command,
                cwd=Path(str(task["repair_repo"])),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=errors,
                text=True,
                bufsize=1,
            )
            assert process.stdout is not None
            try:
                for line in process.stdout:
                    events.write(line)
                    events.flush()
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") == "thread.started" and event.get("thread_id"):
                        task["thread_id"] = str(event["thread_id"])
                        self.save_task(task)
                    task["last_event_at"] = utc_now()
                    if time.monotonic() - started > self.config.codex_timeout_seconds + 60:
                        process.terminate()
                        break
                try:
                    returncode = process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill()
                    returncode = process.wait(timeout=10)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=10)
        events_path.chmod(0o600)
        stderr_path.chmod(0o600)
        result_path = task_dir / "last-message.json"
        result = load_json(result_path, default={})
        return returncode, result

    def verify_repair(self, task: dict[str, Any]) -> dict[str, Any]:
        repair_repo = Path(str(task["repair_repo"]))
        status = command_output(
            ["git", "status", "--short"], cwd=repair_repo, timeout=30, check=True
        ).stdout
        tests = command_output(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
            cwd=repair_repo,
            timeout=1800,
        )
        task_dir = self.tasks_dir / str(task["id"])
        test_log = task_dir / "tests.log"
        test_log.write_text(tests.stdout + tests.stderr, encoding="utf-8")
        test_log.chmod(0o600)
        changed_manifests = set(
            command_output(
                [
                    "git",
                    "diff",
                    "--name-only",
                    str(task["base_commit"]),
                    "--",
                    "patches",
                ],
                cwd=repair_repo,
                timeout=30,
                check=True,
            ).stdout.splitlines()
        )
        changed_manifests.update(
            command_output(
                ["git", "ls-files", "--others", "--exclude-standard", "--", "patches/*.json"],
                cwd=repair_repo,
                timeout=30,
                check=True,
            ).stdout.splitlines()
        )
        safety_violations: list[str] = []
        for relative in sorted(changed_manifests):
            path = repair_repo / relative
            if not path.is_file() or path.suffix != ".json":
                continue
            try:
                raw = load_json(path)
            except UpdateError as error:
                safety_violations.append(str(error))
                continue
            if raw.get("review_status") == "approved":
                safety_violations.append(
                    f"automated repair cannot approve binary manifest {relative}"
                )
        return {
            "changed": bool(status.strip()),
            "git_status": status.splitlines(),
            "tests_passed": tests.returncode == 0,
            "test_log": str(test_log),
            "safety_violations": safety_violations,
        }

    def finish_task(self, task: dict[str, Any], result: dict[str, Any]) -> None:
        verification = self.verify_repair(task)
        requested = str(result.get("status", "blocked"))
        if verification["safety_violations"]:
            phase = "blocked"
            message = "Codex output crossed an automated binary-approval boundary"
        elif not verification["tests_passed"]:
            phase = "blocked"
            message = "Codex completed, but repository tests failed"
        elif requested == "ready_for_review" and verification["changed"]:
            phase = "ready-for-review"
            message = "Codex repair and tests completed; semantic review is required"
        elif requested == "no_change" and not verification["changed"]:
            phase = "no-change"
            message = "Codex found no safe source change"
        else:
            phase = "blocked"
            message = "Codex stopped at a documented review or evidence boundary"
        task["phase"] = phase
        task["result"] = result
        task["verification"] = verification
        task["completed_at"] = utc_now()
        atomic_json(self.tasks_dir / str(task["id"]) / "task.json", task)
        self.pending_path.unlink(missing_ok=True)
        self.write_status(phase, active_task=task["id"], message=message)

    def monitor(self) -> None:
        task = self.load_pending()
        if task is None:
            self.monitor_health()
            return
        task_model = task.get("codex_model")
        if task_model and task_model != self.config.codex_model:
            # Codex does not permit resuming a thread under a different model.
            # The persisted checkout and CONTEXT.md retain the prior evidence.
            task["thread_id"] = None
            task["phase"] = "codex-model-reset"
        task["codex_model"] = self.config.codex_model
        task["codex_reasoning_effort"] = self.config.codex_reasoning_effort
        self.save_task(task)
        next_retry = float(task.get("next_retry_epoch", 0))
        if next_retry > time.time():
            self.write_status(
                "repair-waiting",
                active_task=task["id"],
                next_retry_at=datetime.fromtimestamp(next_retry, timezone.utc).isoformat(),
            )
            return
        try:
            budget = codex_budget_from_rate_limits(
                codex_rate_limits(), self.config.codex_max_used_percent
            )
        except UpdateError as error:
            budget = {
                "verified": False,
                "allowed": False,
                "limit_percent": self.config.codex_max_used_percent,
                "credits_considered": False,
                "error": str(error),
            }
        if not budget["allowed"]:
            reset_at = budget.get("resets_at")
            retry = (
                max(time.time() + 3600, float(reset_at) + 60)
                if isinstance(reset_at, (int, float))
                else time.time() + 3600
            )
            task["phase"] = "codex-budget-deferred"
            task["codex_budget"] = budget
            task["next_retry_epoch"] = retry
            self.save_task(task)
            self.write_status(
                "codex-budget-deferred",
                active_task=task["id"],
                message=(
                    "Codex included usage is unavailable or above the automation "
                    "cap; credits are ignored"
                ),
                codex_budget=budget,
                next_retry_at=datetime.fromtimestamp(retry, timezone.utc).isoformat(),
            )
            return
        task["codex_budget"] = budget
        returncode, result = self.run_codex(task)
        if returncode == 0 and result:
            self.finish_task(task, result)
            return
        attempts = int(task.get("attempts", 1))
        delay = min(24 * 3600, 15 * 60 * (2 ** min(attempts - 1, 6)))
        task["phase"] = "codex-interrupted"
        task["last_returncode"] = returncode
        task["next_retry_epoch"] = time.time() + delay
        self.save_task(task)
        self.write_status(
            "codex-interrupted",
            active_task=task["id"],
            message="the same Codex thread will resume after bounded backoff",
            next_retry_at=datetime.fromtimestamp(
                float(task["next_retry_epoch"]), timezone.utc
            ).isoformat(),
        )

    def print_status(self) -> None:
        status = load_json(self.status_path, default={})
        print("UU Remote maintenance")
        print(f"  phase: {status.get('phase', 'not-run')}")
        print(f"  track: {self.config.track}")
        print(
            "  Codex: "
            f"{self.config.codex_model} ({self.config.codex_reasoning_effort})"
        )
        observed = status.get("observed_release")
        if isinstance(observed, dict):
            print(f"  official endpoint: {observed.get('version', 'unknown')}")
        installed = status.get("installed_release")
        if isinstance(installed, dict):
            print(f"  installed UU: {installed.get('version', 'unknown')}")
        if status.get("active_task"):
            print(f"  task: {status['active_task']}")
        if status.get("message"):
            print(f"  result: {status['message']}")
        if status.get("updated_at"):
            print(f"  updated: {status['updated_at']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path.home() / ".config/uu-remote-bridge/updater.json",
    )
    parser.add_argument("command", choices=("check", "monitor", "status"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manager: Manager | None = None
    try:
        manager = Manager(Config.read(args.config.expanduser()))
        if args.command == "status":
            manager.print_status()
            return 0
        with manager.lock():
            if args.command == "check":
                manager.check()
            else:
                manager.monitor()
        return 0
    except (UpdateError, OSError, subprocess.SubprocessError) as error:
        if manager is not None:
            try:
                manager.write_status("error", message=str(error))
            except (UpdateError, OSError):
                pass
        print(f"UU updater: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
