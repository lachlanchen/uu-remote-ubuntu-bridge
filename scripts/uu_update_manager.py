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
RETRYABLE_PHASES = {
    "blocked",
    "codex-budget-deferred",
    "codex-interrupted",
    "codex-sandbox-deferred",
    "repair-waiting",
}
REQUIRED_PROMOTION_ACCEPTANCE_FLAGS = (
    "disposable_prefix",
    "controller_input",
    "reconnect",
    "service_restart",
    "login_preservation",
)
MINIMUM_PROMOTION_STABILITY_SECONDS = 270
MAXIMUM_PROMOTION_STABILITY_SECONDS = 1800


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


def promotion_acceptance(raw: dict[str, Any]) -> dict[str, Any]:
    acceptance = raw.get("acceptance")
    if not isinstance(acceptance, dict) or acceptance.get("schema_version") != 1:
        return {
            "eligible": False,
            "reason": "no versioned maintainer acceptance record",
        }
    missing = [
        field
        for field in REQUIRED_PROMOTION_ACCEPTANCE_FLAGS
        if acceptance.get(field) is not True
    ]
    if missing:
        return {
            "eligible": False,
            "reason": "incomplete acceptance: " + ", ".join(sorted(missing)),
        }
    stability = acceptance.get("stability_seconds")
    if (
        not isinstance(stability, int)
        or isinstance(stability, bool)
        or stability < MINIMUM_PROMOTION_STABILITY_SECONDS
        or stability > MAXIMUM_PROMOTION_STABILITY_SECONDS
    ):
        return {
            "eligible": False,
            "reason": (
                "acceptance stability is outside the guarded "
                f"{MINIMUM_PROMOTION_STABILITY_SECONDS}-"
                f"{MAXIMUM_PROMOTION_STABILITY_SECONDS} second range"
            ),
        }
    installer = raw.get("installer")
    server = raw.get("server")
    if not isinstance(installer, dict) or not isinstance(server, dict):
        return {"eligible": False, "reason": "manifest binary metadata is incomplete"}
    if acceptance.get("installer_sha256") != installer.get("sha256"):
        return {
            "eligible": False,
            "reason": "acceptance is not bound to the exact installer hash",
        }
    if acceptance.get("patched_server_sha256") != server.get("patched_sha256"):
        return {
            "eligible": False,
            "reason": "acceptance is not bound to the patched server hash",
        }
    evidence = acceptance.get("evidence")
    if (
        not isinstance(evidence, str)
        or not evidence.strip()
        or Path(evidence).is_absolute()
        or ".." in Path(evidence).parts
    ):
        return {
            "eligible": False,
            "reason": "acceptance evidence must be a repository-relative path",
        }
    for field in ("accepted_at", "accepted_by"):
        value = acceptance.get(field)
        if not isinstance(value, str) or not value.strip():
            return {
                "eligible": False,
                "reason": f"acceptance is missing {field}",
            }
    return {
        "eligible": True,
        "reason": "all maintainer acceptance and hash-binding gates passed",
        "stability_seconds": stability,
        "evidence": evidence,
    }


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


def systemctl_user_command(*arguments: str) -> list[str]:
    """Address the persistent user manager instead of an RDP session bus."""
    runtime_dir = Path(f"/run/user/{os.getuid()}")
    return [
        "/usr/bin/env",
        f"DBUS_SESSION_BUS_ADDRESS=unix:path={runtime_dir}/bus",
        "/usr/bin/systemctl",
        "--user",
        *arguments,
    ]


def workspace_sandbox_probe() -> dict[str, Any]:
    """Prove that Codex's Bubblewrap user namespace can start on this host."""
    bwrap = Path("/usr/bin/bwrap")
    if not bwrap.is_file() or not os.access(bwrap, os.X_OK):
        return {
            "available": False,
            "detail": "bubblewrap is unavailable at /usr/bin/bwrap",
        }
    result = command_output(
        [
            str(bwrap),
            "--die-with-parent",
            "--unshare-user",
            "--uid",
            "0",
            "--gid",
            "0",
            "--ro-bind",
            "/",
            "/",
            "/bin/true",
        ],
        timeout=15,
    )
    detail = (result.stderr.strip() or result.stdout.strip())[-1200:]
    return {
        "available": result.returncode == 0,
        "returncode": result.returncode,
        "detail": detail,
    }


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


def codex_rate_limits(
    codex_executable: str | Path = "codex", timeout: int = 15
) -> dict[str, Any]:
    try:
        process = subprocess.Popen(
            [str(codex_executable), "app-server", "--stdio"],
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
    codex_executable: Path
    codex_model: str
    codex_reasoning_effort: str
    codex_timeout_seconds: int
    codex_max_used_percent: int
    idle_minutes: int
    auto_reinstall_known_good: bool
    auto_promote_accepted_release: bool
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
        codex_value = str(raw.get("codex_executable", "")).strip()
        codex_executable = Path(codex_value).expanduser()
        if (
            not codex_value
            or not codex_executable.is_absolute()
            or not codex_executable.is_file()
            or not os.access(codex_executable, os.X_OK)
        ):
            raise UpdateError(
                "the updater needs an absolute executable Codex path; "
                "rerun configure-updater.sh enable"
            )
        max_used_percent = int(raw.get("codex_max_used_percent", 20))
        if not 0 <= max_used_percent <= 100:
            raise UpdateError("codex_max_used_percent must be between 0 and 100")
        auto_reinstall = raw.get("auto_reinstall_known_good", False)
        auto_promote = raw.get("auto_promote_accepted_release", False)
        if not isinstance(auto_reinstall, bool) or not isinstance(
            auto_promote, bool
        ):
            raise UpdateError("automatic updater action flags must be JSON booleans")
        return cls(
            path=path,
            repository=repository,
            state_dir=state_dir,
            remote=str(raw.get("remote", "origin")),
            branch=str(raw.get("branch", "main")),
            track=str(raw.get("track", "track-rdp-broker-20260724")),
            endpoint=str(raw.get("endpoint", DEFAULT_ENDPOINT)),
            codex_executable=codex_executable,
            codex_model=model,
            codex_reasoning_effort=effort,
            codex_timeout_seconds=max(300, int(raw.get("codex_timeout_seconds", 5400))),
            codex_max_used_percent=max_used_percent,
            idle_minutes=max(5, int(raw.get("idle_minutes", 45))),
            auto_reinstall_known_good=auto_reinstall,
            auto_promote_accepted_release=auto_promote,
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
        self.promotion_marker_path = (
            self.state_dir / "promotion-in-progress.json"
        )
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
        source_commit = self.remote_base_commit()
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
                acceptance = promotion_acceptance(raw)
                if acceptance["eligible"]:
                    evidence = str(acceptance["evidence"])
                    evidence_check = command_output(
                        ["git", "cat-file", "-e", f"{reference}:{evidence}"],
                        cwd=self.config.repository,
                        timeout=30,
                    )
                    if evidence_check.returncode != 0:
                        acceptance = {
                            "eligible": False,
                            "reason": (
                                "acceptance evidence is absent from the "
                                "pinned repository commit"
                            ),
                        }
                releases.append(
                    {
                        "version": version,
                        "installer_sha256": str(installer["sha256"]),
                        "manifest": f"{reference}:{relative}",
                        "manifest_path": relative,
                        "manifest_sha256": hashlib.sha256(
                            rendered.encode("utf-8")
                        ).hexdigest(),
                        "source_commit": source_commit,
                        "promotion_acceptance": acceptance,
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

    def create_promotion_checkout(
        self, task_dir: Path, source_commit: str
    ) -> Path:
        promotion_repo = task_dir / "promotion-repo"
        if promotion_repo.exists():
            head = command_output(
                ["git", "rev-parse", "HEAD"],
                cwd=promotion_repo,
                timeout=30,
                check=True,
            ).stdout.strip()
            if head != source_commit:
                raise UpdateError(
                    "retained promotion checkout differs from its pinned commit"
                )
            return promotion_repo
        command_output(
            [
                "git",
                "clone",
                "--quiet",
                "--no-hardlinks",
                str(self.config.repository),
                str(promotion_repo),
            ],
            timeout=300,
            check=True,
        )
        command_output(
            ["git", "checkout", "--quiet", "--detach", source_commit],
            cwd=promotion_repo,
            timeout=60,
            check=True,
        )
        command_output(
            [
                "git",
                "remote",
                "set-url",
                "--push",
                "origin",
                "disabled://approved-promotion",
            ],
            cwd=promotion_repo,
            check=True,
        )
        return promotion_repo

    def queue_promotion(
        self,
        release: dict[str, Any],
        installer: Path,
        observed: dict[str, Any],
        installed: dict[str, str],
    ) -> dict[str, Any]:
        acceptance = release.get("promotion_acceptance")
        if not isinstance(acceptance, dict) or acceptance.get("eligible") is not True:
            raise UpdateError("release is not eligible for guarded promotion")
        source_commit = str(release.get("source_commit", ""))
        manifest_relative = str(release.get("manifest_path", ""))
        manifest_digest = str(release.get("manifest_sha256", ""))
        if (
            not re.fullmatch(r"[0-9a-f]{40,64}", source_commit)
            or not re.fullmatch(r"[0-9a-f]{64}", manifest_digest)
            or not manifest_relative
            or Path(manifest_relative).is_absolute()
            or ".." in Path(manifest_relative).parts
        ):
            raise UpdateError("approved release lacks pinned promotion metadata")
        if (
            not installer.is_file()
            or sha256_file(installer) != release["installer_sha256"]
        ):
            raise UpdateError("cached installer no longer matches the accepted release")

        identity = (
            f"{release['version']}-{str(release['installer_sha256'])[:12]}-"
            f"{manifest_digest[:12]}"
        )
        task_id = task_name(f"approved-promotion-{identity}")
        task_dir = self.tasks_dir / task_id
        task_path = task_dir / "task.json"
        task_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        if task_path.is_file():
            task = load_json(task_path)
            phase = str(task.get("phase", ""))
            if phase == "promoted":
                self.write_status(
                    "current",
                    active_task=task_id,
                    installed_release=self.installed_release(),
                    observed_release=observed,
                    message="the accepted UU release was already promoted",
                )
                return task
            if phase == "promotion-blocked":
                self.write_status(
                    phase,
                    active_task=task_id,
                    observed_release=observed,
                    message=(
                        "the guarded promotion failed closed and will not "
                        "retry automatically"
                    ),
                )
                return task
        else:
            promotion_repo = self.create_promotion_checkout(
                task_dir, source_commit
            )
            manifest = promotion_repo / manifest_relative
            if not manifest.is_file() or sha256_file(manifest) != manifest_digest:
                raise UpdateError(
                    "pinned promotion manifest failed checkout verification"
                )
            task = {
                "schema_version": 1,
                "id": task_id,
                "kind": "approved-promotion",
                "created_at": utc_now(),
                "updated_at": utc_now(),
                "phase": "promotion-queued",
                "attempts": 0,
                "source_commit": source_commit,
                "promotion_repo": str(promotion_repo),
                "details": {
                    "release": release,
                    "observed_release": observed,
                    "installed_release": installed,
                    "installer": str(installer),
                    "manifest": str(manifest),
                    "acceptance": acceptance,
                },
            }

        pending = self.load_pending()
        if pending is not None and pending.get("id") != task_id:
            task["phase"] = "promotion-deferred"
            task["updated_at"] = utc_now()
            atomic_json(task_path, task)
            self.write_status(
                "promotion-deferred",
                active_task=task_id,
                observed_release=observed,
                message=(
                    "an existing maintenance task must finish before the "
                    "accepted release can enter its guarded transaction"
                ),
            )
            return task

        task["phase"] = "promotion-queued"
        task["updated_at"] = utc_now()
        atomic_json(task_path, task)
        atomic_json(self.pending_path, task)
        self.write_status(
            "promotion-queued",
            active_task=task_id,
            observed_release=observed,
            message=(
                "accepted release queued for snapshot, login-preserving "
                "in-place update, runtime verification, and rollback on failure"
            ),
        )
        return task

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
        handoff_source = (
            self.config.repository / "docs/automated-repair-agent-handoff.md"
        )
        handoff_snapshot = context_path.parent / "OPERATIONAL-HANDOFF.md"
        if not handoff_source.is_file():
            raise UpdateError(f"missing automated repair handoff: {handoff_source}")
        shutil.copyfile(handoff_source, handoff_snapshot)
        handoff_snapshot.chmod(0o600)
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
            "## Required operational memory",
            "",
            "Before editing, read `build/automated-repair/OPERATIONAL-HANDOFF.md`.",
            "It preserves the two-host keyboard history, direct-X11 acceptance,",
            "failed hypotheses, rollback rules, and the automated action contract.",
            "Then read `docs/upstream-maintenance.md`, `docs/security.md`,",
            "`docs/release-tracks.md`, `docs/automatic-updates.md`,",
            "`docs/debugging-journey.md`, `docs/mobile-keyboard-parity-handoff.md`,",
            "`docs/xrdp-and-keyboard-recovery.md`, and `docs/troubleshooting.md`.",
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
        try:
            installed_key: tuple[int, ...] | None = version_key(
                str(installed["version"])
            )
        except UpdateError:
            installed_key = None
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
            and installed_key is not None
            and installed_key >= approved_key
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
            (
                item
                for item in approved
                if item["installer_sha256"] == installer_hash
                and version_key(str(item["version"])) == observed_key
            ),
            None,
        )
        if matching:
            matching_key = version_key(str(matching["version"]))
            if installed_key is not None and installed_key >= matching_key:
                self.write_status(
                    "current",
                    last_check_completed_at=utc_now(),
                    installed_release=installed,
                    latest_approved_release=matching,
                    observed_release=observed,
                    message="official installer full hash matches the approved baseline",
                )
                return
            acceptance = matching.get("promotion_acceptance")
            if not isinstance(acceptance, dict) or acceptance.get("eligible") is not True:
                reason = (
                    str(acceptance.get("reason"))
                    if isinstance(acceptance, dict)
                    else "the release has no complete promotion acceptance"
                )
                self.write_status(
                    "approved-release-detected",
                    installed_release=installed,
                    observed_release=observed,
                    latest_approved_release=matching,
                    message=(
                        "approved installer is cached but cannot transfer: "
                        + reason
                    ),
                )
                return
            if not self.config.auto_promote_accepted_release:
                self.write_status(
                    "accepted-release-ready",
                    installed_release=installed,
                    observed_release=observed,
                    latest_approved_release=matching,
                    message=(
                        "fully accepted installer is cached; automatic guarded "
                        "promotion is disabled"
                    ),
                )
                return
            self.queue_promotion(matching, installer, observed, installed)
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
            systemctl_user_command(
                "show",
                "uu-remote-bridge.service",
                "--property=ActiveState",
                "--property=NRestarts",
                "--property=ActiveEnterTimestampMonotonic",
            ),
            timeout=15,
        )
        service_properties = dict(
            line.split("=", 1)
            for line in service.stdout.splitlines()
            if "=" in line
        )
        if service.returncode != 0:
            issues.append("bridge-service-query-failed")
        elif service_properties.get("ActiveState") != "active":
            issues.append("bridge-service-inactive")
        try:
            restart_count = int(service_properties.get("NRestarts", "0"))
        except ValueError:
            restart_count = 0
        try:
            active_since = (
                int(service_properties.get("ActiveEnterTimestampMonotonic", "0"))
                / 1_000_000
            )
        except ValueError:
            active_since = 0
        active_age_seconds = (
            max(0.0, time.monotonic() - active_since) if active_since else None
        )
        if restart_count >= 3 and (
            active_age_seconds is None or active_age_seconds <= 15 * 60
        ):
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
                "-u",
                str(os.getuid()),
                "-f",
                f"gnome-remote-desktop-daemon --rdp-port {rdp_port}",
            ],
            timeout=15,
        )
        relay_pids = {
            line.strip()
            for line in relay.stdout.splitlines()
            if line.strip().isdigit()
        }
        if relay.returncode != 0 or not relay_pids:
            issues.append("gnome-rdp-relay-missing")
        else:
            listener = command_output(
                ["ss", "-H", "-ltnp", f"sport = :{rdp_port}"], timeout=15
            )
            if not any(f"pid={pid}," in listener.stdout for pid in relay_pids):
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
            "active_age_seconds": active_age_seconds,
            "rdp_port": int(rdp_port),
        }

    def restart_bridge(self) -> dict[str, Any]:
        result = command_output(
            systemctl_user_command("restart", "uu-remote-bridge.service"),
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
            systemctl_user_command("stop", "uu-remote-bridge.service"), timeout=90
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
        command_output(systemctl_user_command("daemon-reload"), timeout=30)
        start = command_output(
            systemctl_user_command("start", "uu-remote-bridge.service"), timeout=90
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
        if "bridge-service-query-failed" in confirmed["issues"]:
            details = self.runtime_context(first, confirmed)
            details["confirmed_health"] = details.pop(
                "health_after_restart", confirmed
            )
            details["known_good_reinstall"] = {
                "attempted": False,
                "reason": "the service-manager probe was indeterminate",
            }
            identity = datetime.now().strftime("%Y%m%d-%H%M")
            self.queue_task("runtime-health", identity, details)
            return
        if not self.config.auto_reinstall_known_good:
            details = self.runtime_context(first, confirmed)
            details["confirmed_health"] = details.pop(
                "health_after_restart", confirmed
            )
            details["automatic_live_recovery"] = {
                "attempted": False,
                "reason": (
                    "disabled by default so updater health observations cannot "
                    "restart RDP or UU"
                ),
            }
            details["known_good_reinstall"] = {
                "attempted": False,
                "reason": "automatic live recovery is disabled",
            }
            identity = datetime.now().strftime("%Y%m%d-%H%M")
            self.queue_task("runtime-health", identity, details)
            return
        restarted = self.restart_bridge()
        if restarted["health"]["healthy"]:
            self.write_status(
                "self-healed",
                bridge_health=restarted["health"],
                message="the inactive relay recovered after one supervised restart",
            )
            return
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

    def refresh_operator_staging(self, task: dict[str, Any]) -> None:
        if task.get("kind") != "upstream-release":
            return
        task_dir = self.tasks_dir / str(task["id"])
        stage_dir = task_dir / "stage-sandbox"
        record_path = stage_dir / "SHA256"
        server = stage_dir / "GameViewerServer.exe"
        healthd = stage_dir / "GameViewerHealthd.exe"
        if not stage_dir.exists():
            return
        if not all(path.is_file() for path in (record_path, server, healthd)):
            raise UpdateError(
                f"operator staging is incomplete for task {task['id']}"
            )
        record = dict(
            line.split("=", 1)
            for line in record_path.read_text(encoding="utf-8").splitlines()
            if "=" in line
        )
        observed = task.get("details", {}).get("observed_release", {})
        expected_installer = str(observed.get("installer_sha256", ""))
        if (
            record.get("staging_method") != "systemd-sandbox"
            or not re.fullmatch(r"[0-9a-f]{64}", expected_installer)
            or record.get("installer_sha256") != expected_installer
            or record.get("server_sha256") != sha256_file(server)
            or record.get("healthd_sha256") != sha256_file(healthd)
        ):
            raise UpdateError(
                f"operator staging failed hash or sandbox validation for {task['id']}"
            )
        task["details"]["staging"] = {
            "returncode": 0,
            "stage_dir": str(stage_dir),
            "server_available": True,
            "healthd_available": True,
            "server_sha256": record["server_sha256"],
            "healthd_sha256": record["healthd_sha256"],
            "sandbox_executed": True,
            "operator_authorized": True,
        }

    def retry_task(self) -> None:
        task = self.load_pending()
        if task is None:
            status = load_json(self.status_path, default={})
            task_id = str(status.get("active_task", "")).strip()
            if not task_id:
                raise UpdateError("there is no retained UU repair task to retry")
            task_path = self.tasks_dir / task_name(task_id) / "task.json"
            if not task_path.is_file():
                raise UpdateError(f"retained UU repair task is unavailable: {task_id}")
            task = load_json(task_path)

        phase = str(task.get("phase", ""))
        if phase not in RETRYABLE_PHASES:
            raise UpdateError(
                f"UU repair task {task.get('id', 'unknown')} cannot be retried "
                f"from phase {phase or 'unknown'}"
            )

        task["phase"] = "queued"
        task["thread_id"] = None
        task["retry_count"] = int(task.get("retry_count", 0)) + 1
        task["manually_retried_at"] = utc_now()
        self.refresh_operator_staging(task)
        for key in (
            "completed_at",
            "last_returncode",
            "next_retry_epoch",
            "result",
            "verification",
        ):
            task.pop(key, None)
        self.save_task(task)
        self.write_status(
            "repair-queued",
            active_task=task["id"],
            message=(
                "the retained repair evidence and checkout will be retried "
                "in a new Codex thread"
            ),
        )

    def save_task(self, task: dict[str, Any]) -> None:
        task["updated_at"] = utc_now()
        task_dir = self.tasks_dir / str(task["id"])
        atomic_json(task_dir / "task.json", task)
        atomic_json(self.pending_path, task)

    def promotion_paths(
        self, task: dict[str, Any]
    ) -> tuple[Path, Path, Path, Path, Path]:
        task_id = task_name(str(task.get("id", "")))
        if not task_id or task_id != task.get("id"):
            raise UpdateError("promotion task identifier is unsafe")
        task_dir = (self.tasks_dir / task_id).resolve()
        tasks_root = self.tasks_dir.resolve()
        try:
            task_dir.relative_to(tasks_root)
        except ValueError as error:
            raise UpdateError("promotion task escaped the local state directory") from error
        promotion_repo = Path(str(task.get("promotion_repo", ""))).resolve()
        try:
            promotion_repo.relative_to(task_dir)
        except ValueError as error:
            raise UpdateError("promotion checkout escaped its task directory") from error
        details = task.get("details")
        if not isinstance(details, dict):
            raise UpdateError("promotion task details are missing")
        manifest = Path(str(details.get("manifest", ""))).resolve()
        try:
            manifest.relative_to(promotion_repo)
        except ValueError as error:
            raise UpdateError("promotion manifest escaped its pinned checkout") from error
        installer = Path(str(details.get("installer", ""))).resolve()
        work_dir = task_dir / "promotion"
        helper = promotion_repo / "scripts/promote-approved-release.py"
        if not helper.is_file():
            raise UpdateError("promotion transaction helper is unavailable")
        if not manifest.is_file() or not installer.is_file():
            raise UpdateError("promotion task files are incomplete")
        release = details.get("release")
        if (
            not isinstance(release, dict)
            or sha256_file(installer) != release.get("installer_sha256")
            or sha256_file(manifest) != release.get("manifest_sha256")
        ):
            raise UpdateError("promotion task hashes no longer match its acceptance")
        return task_dir, promotion_repo, helper, manifest, work_dir

    def recover_interrupted_promotion(self) -> bool:
        if not self.promotion_marker_path.is_file():
            return False
        marker = load_json(self.promotion_marker_path)
        work_dir = Path(str(marker.get("work_dir", ""))).resolve()
        try:
            relative = work_dir.relative_to(self.tasks_dir.resolve())
        except ValueError as error:
            raise UpdateError(
                "promotion recovery marker escaped the updater state directory"
            ) from error
        if len(relative.parts) < 2 or relative.parts[1] != "promotion":
            raise UpdateError("promotion recovery marker names an unsafe work directory")
        task_id = relative.parts[0]
        task_path = self.tasks_dir / task_id / "task.json"
        if not task_path.is_file():
            raise UpdateError("promotion recovery task is unavailable")
        task = load_json(task_path)
        task_dir = (self.tasks_dir / task_id).resolve()
        expected_work = task_dir / "promotion"
        promotion_repo = Path(str(task.get("promotion_repo", ""))).resolve()
        try:
            promotion_repo.relative_to(task_dir)
        except ValueError as error:
            raise UpdateError(
                "promotion recovery checkout escaped its task directory"
            ) from error
        helper = promotion_repo / "scripts/promote-approved-release.py"
        if not helper.is_file():
            promotion_repo = (
                Path.home() / ".local/libexec/uu-remote-updater"
            ).resolve()
            helper = promotion_repo / "scripts/promote-approved-release.py"
            if not helper.is_file():
                raise UpdateError(
                    "no retained or installed promotion recovery helper is available"
                )
        if expected_work != work_dir:
            raise UpdateError("promotion marker and retained task disagree")
        prefix = Path.home() / ".local/share/wineprefixes/uu-remote"
        if Path(str(marker.get("prefix", ""))).resolve() != prefix.resolve():
            raise UpdateError("promotion marker does not name the managed UU prefix")
        result = command_output(
            [
                sys.executable,
                str(helper),
                "recover",
                "--repository",
                str(promotion_repo),
                "--work-dir",
                str(work_dir),
                "--state-dir",
                str(self.state_dir),
                "--prefix",
                str(prefix),
            ],
            cwd=promotion_repo,
            timeout=1800,
        )
        if result.returncode != 0:
            raise UpdateError(
                "automatic UU promotion recovery failed: "
                + (result.stderr or result.stdout).strip()[-1200:]
            )
        try:
            recovery = json.loads(result.stdout.splitlines()[-1])
        except (IndexError, json.JSONDecodeError) as error:
            raise UpdateError(
                "promotion recovery returned no valid result record"
            ) from error
        if not isinstance(recovery, dict):
            raise UpdateError("promotion recovery result is not an object")
        task["phase"] = "promotion-blocked"
        task["recovery"] = recovery
        task["completed_at"] = utc_now()
        atomic_json(task_dir / "task.json", task)
        pending = self.load_pending()
        if pending is not None and pending.get("id") == task_id:
            self.pending_path.unlink(missing_ok=True)
        self.write_status(
            "promotion-blocked",
            active_task=task_id,
            message=(
                "an interrupted promotion was rolled back to the complete "
                "previous Wine prefix; automatic retry is disabled"
            ),
        )
        return True

    def run_promotion(self, task: dict[str, Any]) -> None:
        if not self.config.auto_promote_accepted_release:
            task["phase"] = "promotion-held"
            self.save_task(task)
            self.write_status(
                "promotion-held",
                active_task=task["id"],
                message=(
                    "guarded automatic promotion is disabled; the live UU "
                    "prefix and XRDP were not touched"
                ),
            )
            return
        activity_dir = (
            Path.home()
            / ".local/share/wineprefixes/uu-remote/drive_c/Program Files"
            / "Netease/GameViewer/log/server/log"
        )
        activity_files = (
            [path for path in activity_dir.glob("*.txt") if path.is_file()]
            if activity_dir.is_dir()
            else []
        )
        if not activity_files:
            task["phase"] = "promotion-waiting-idle"
            self.save_task(task)
            self.write_status(
                "promotion-waiting-idle",
                active_task=task["id"],
                message=(
                    "UU client activity cannot be verified; refusing to "
                    "interrupt a possibly active connection"
                ),
            )
            return
        activity_mtimes: list[float] = []
        for path in activity_files:
            try:
                activity_mtimes.append(path.stat().st_mtime)
            except OSError:
                continue
        if not activity_mtimes:
            task["phase"] = "promotion-waiting-idle"
            self.save_task(task)
            self.write_status(
                "promotion-waiting-idle",
                active_task=task["id"],
                message=(
                    "UU activity timestamps are unavailable; refusing to "
                    "interrupt a possibly active connection"
                ),
            )
            return
        latest_activity = max(activity_mtimes)
        quiet_seconds = max(0.0, time.time() - latest_activity)
        required_quiet_seconds = self.config.idle_minutes * 60
        if quiet_seconds < required_quiet_seconds:
            task["phase"] = "promotion-waiting-idle"
            task["quiet_seconds"] = int(quiet_seconds)
            self.save_task(task)
            self.write_status(
                "promotion-waiting-idle",
                active_task=task["id"],
                message=(
                    "an accepted update is ready, but recent UU activity keeps "
                    "the live connection untouched"
                ),
                required_quiet_minutes=self.config.idle_minutes,
            )
            return
        task_dir, promotion_repo, helper, manifest, work_dir = self.promotion_paths(
            task
        )
        details = task["details"]
        release = details["release"]
        installer = Path(str(details["installer"])).resolve()
        task["phase"] = "promotion-running"
        task["attempts"] = int(task.get("attempts", 0)) + 1
        task["last_attempt_started_at"] = utc_now()
        self.save_task(task)
        self.write_status(
            "promotion-running",
            active_task=task["id"],
            message=(
                "running the snapshot and login-preserving UU-only transaction; "
                "XRDP is outside the transaction"
            ),
        )
        result = command_output(
            [
                sys.executable,
                str(helper),
                "apply",
                "--repository",
                str(promotion_repo),
                "--manifest",
                str(manifest),
                "--installer",
                str(installer),
                "--work-dir",
                str(work_dir),
                "--state-dir",
                str(self.state_dir),
                "--source-commit",
                str(task["source_commit"]),
            ],
            cwd=promotion_repo,
            timeout=7200,
        )
        result_path = work_dir / "result.json"
        promotion_result = (
            load_json(result_path)
            if result_path.is_file()
            else {
                "status": "failed",
                "error": (result.stderr or result.stdout).strip()[-1200:],
            }
        )
        if result.returncode == 0 and promotion_result.get("status") == "promoted":
            task["phase"] = "promoted"
            task["result"] = promotion_result
            task["completed_at"] = utc_now()
            atomic_json(task_dir / "task.json", task)
            self.pending_path.unlink(missing_ok=True)
            self.write_status(
                "promoted",
                active_task=task["id"],
                installed_release=self.installed_release(),
                observed_release=details.get("observed_release"),
                message=(
                    f"UU {release['version']} passed the guarded transaction; "
                    "existing account state was preserved and XRDP was unchanged"
                ),
            )
            return
        task["phase"] = "promotion-blocked"
        task["result"] = promotion_result
        task["completed_at"] = utc_now()
        atomic_json(task_dir / "task.json", task)
        self.pending_path.unlink(missing_ok=True)
        self.write_status(
            "promotion-blocked",
            active_task=task["id"],
            message=(
                "guarded promotion failed closed; the previous complete prefix "
                "was restored and automatic retry is disabled"
            ),
        )

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
            return [
                str(self.config.codex_executable),
                "exec",
                "resume",
                *common,
                str(task["thread_id"]),
                prompt,
            ]
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
            str(self.config.codex_executable),
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
        task["live_promotion"] = {
            "eligible": False,
            "reason": (
                "automated Codex output never authorizes transfer to the live "
                "UU prefix; semantic binary review and controller acceptance "
                "must finish first"
            ),
        }
        task["completed_at"] = utc_now()
        atomic_json(self.tasks_dir / str(task["id"]) / "task.json", task)
        self.pending_path.unlink(missing_ok=True)
        self.write_status(phase, active_task=task["id"], message=message)

    def monitor(self) -> None:
        if self.recover_interrupted_promotion():
            return
        task = self.load_pending()
        if task is None:
            self.monitor_health()
            return
        if task.get("kind") == "approved-promotion":
            self.run_promotion(task)
            return
        task_model = task.get("codex_model")
        if task_model and task_model != self.config.codex_model:
            # Codex does not permit resuming a thread under a different model.
            # The persisted checkout and CONTEXT.md retain the prior evidence.
            task["thread_id"] = None
            task["phase"] = "codex-model-reset"
        task["codex_model"] = self.config.codex_model
        task["codex_reasoning_effort"] = self.config.codex_reasoning_effort
        repair_repo_value = task.get("repair_repo")
        repair_repo = (
            Path(str(repair_repo_value)) if repair_repo_value else None
        )
        if repair_repo is not None and repair_repo.is_dir():
            task["context"] = str(self.write_context(task, repair_repo))
        self.save_task(task)
        next_retry = float(task.get("next_retry_epoch", 0))
        if next_retry > time.time():
            self.write_status(
                "repair-waiting",
                active_task=task["id"],
                next_retry_at=datetime.fromtimestamp(next_retry, timezone.utc).isoformat(),
            )
            return
        sandbox = workspace_sandbox_probe()
        if not sandbox["available"]:
            retry = time.time() + 3600
            task["phase"] = "codex-sandbox-deferred"
            task["workspace_sandbox"] = sandbox
            task["next_retry_epoch"] = retry
            self.save_task(task)
            self.write_status(
                "codex-sandbox-deferred",
                active_task=task["id"],
                message=(
                    "Codex workspace-write could not start. On Ubuntu, enable "
                    "the distro bwrap-userns-restrict AppArmor profile."
                ),
                workspace_sandbox=sandbox,
                next_retry_at=datetime.fromtimestamp(retry, timezone.utc).isoformat(),
            )
            return
        task["workspace_sandbox"] = sandbox
        try:
            budget = codex_budget_from_rate_limits(
                codex_rate_limits(self.config.codex_executable),
                self.config.codex_max_used_percent,
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
    parser.add_argument("command", choices=("check", "monitor", "retry", "status"))
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
            elif args.command == "retry":
                manager.retry_task()
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
