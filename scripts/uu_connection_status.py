#!/usr/bin/env python3
"""Summarize UU transport health without printing private connection data."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path


REPORT_MARKER = "report json "
WATCHDOG_RE = re.compile(
    r"current polinttime is:\s*(?P<threshold>\d+).*?"
    r"delay time is:\s*(?P<delay>\d+)"
)
LOG_TIMESTAMP_RE = re.compile(
    r"^\[(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?)\]"
)


def latest_file(log_dir: Path, pattern: str) -> Path | None:
    files = [path for path in log_dir.glob(pattern) if path.is_file()]
    return max(files, key=lambda path: path.stat().st_mtime, default=None)


def load_reports(
    log_dir: Path,
) -> list[tuple[Path, dict[str, object], datetime]]:
    reports: list[tuple[Path, dict[str, object], datetime]] = []
    for path in sorted(log_dir.glob("streamer_log_*.txt")):
        with path.open(errors="replace") as stream:
            for line in stream:
                if REPORT_MARKER not in line:
                    continue
                payload = line.split(REPORT_MARKER, 1)[1].strip()
                try:
                    report = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if isinstance(report, dict) and "forced_relay" in report:
                    timestamp_match = LOG_TIMESTAMP_RE.match(line)
                    if timestamp_match:
                        completed_at = datetime.fromisoformat(
                            timestamp_match.group("timestamp")
                        )
                    else:
                        completed_at = datetime.fromtimestamp(
                            path.stat().st_mtime
                        )
                    reports.append((path, report, completed_at))
    return sorted(reports, key=lambda item: item[2])


def load_watchdog_events(server_log: Path | None) -> list[tuple[int, int]]:
    events: list[tuple[int, int]] = []
    if server_log is None:
        return events
    with server_log.open(errors="replace") as stream:
        for line in stream:
            match = WATCHDOG_RE.search(line)
            if match:
                events.append(
                    (int(match.group("threshold")), int(match.group("delay")))
                )
    return events


def format_number(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "unknown"
    return f"{value:.0f} ms"


def summarize(log_dir: Path) -> tuple[list[str], int]:
    reports = load_reports(log_dir)
    if not reports:
        return (["No completed UU stream report was found."], 1)

    stream_log, report, completed_at = reports[-1]
    matching_server_log = stream_log.with_name(
        stream_log.name.removeprefix("streamer_")
    )
    server_log = (
        matching_server_log
        if matching_server_log.is_file()
        else latest_file(log_dir, "log_*.txt")
    )
    watchdog_events = load_watchdog_events(server_log)
    forced = report.get("forced_relay") == 1
    candidate = str(report.get("candidate_type", "unknown"))
    average = report.get("average_delay")
    maximum = report.get("max_delay")
    p90_rtt = report.get("streamer_p90_rtt")
    p2p_attempted = report.get("need_to_p2p_punch") == 1
    publisher_country = str(report.get("publisher_country", "")).strip()
    subscriber_country = str(report.get("subscriber_country", "")).strip()
    cross_region = bool(
        publisher_country
        and subscriber_country
        and publisher_country != subscriber_country
    )
    prior_p2p_blocked = any(
        item.get("punch_stopped_by_firewall") == 1
        for _, item, _ in reports
    )

    age_seconds = max(0, int((datetime.now() - completed_at).total_seconds()))
    age_minutes = age_seconds // 60

    lines = [
        "UU connection summary (latest completed session)",
        f"  completed: {completed_at:%Y-%m-%d %H:%M:%S}",
        f"  age: {age_minutes} minute(s)",
        f"  path: {candidate}{' (forced by controller)' if forced else ''}",
        f"  average delay: {format_number(average)}",
        f"  maximum delay: {format_number(maximum)}",
        f"  p90 RTT: {format_number(p90_rtt)}",
        f"  P2P attempted: {'yes' if p2p_attempted else 'no'}",
    ]
    if publisher_country and subscriber_country:
        lines.append(
            "  controller/host relay geography: "
            f"{'cross-region' if cross_region else 'same-region'}"
        )
    if watchdog_events:
        threshold = watchdog_events[-1][0]
        max_observed = max(delay for _, delay in watchdog_events)
        lines.append(
            "  key watchdog: "
            f"{len(watchdog_events)} forced release(s), "
            f"threshold {threshold} ms, max observed {max_observed} ms"
        )
    else:
        lines.append("  key watchdog: no forced releases logged")

    high_delay = isinstance(average, (int, float)) and average >= 250
    if forced and high_delay:
        lines.extend(
            [
                "Assessment: network-bound input loss is likely.",
                "The controller selected a high-latency relay before the host "
                "received the keys.",
                "Use Automatic/P2P on the controlling UU client when available; "
                "do not add host-side key retries.",
            ]
        )
    elif high_delay:
        lines.append("Assessment: transport latency is high enough to disrupt input.")
    else:
        lines.append("Assessment: transport delay does not currently explain input loss.")

    if prior_p2p_blocked:
        lines.append(
            "Note: earlier automatic sessions recorded P2P blocked by NAT/firewall, "
            "so compare both modes rather than assuming P2P will be faster."
        )
    if cross_region and high_delay:
        lines.append(
            "Note: the controller and host used different relay regions; "
            "check the controlling device's VPN, proxy, and exit network "
            "before changing host input code."
        )
    if age_seconds >= 300:
        lines.append(
            "Note: this completed session is stale and does not describe a "
            "newly started or currently idle bridge."
        )
    return lines, 0


def main() -> int:
    if len(sys.argv) > 2:
        print("usage: uu-connection-status [LOG_DIR]", file=sys.stderr)
        return 2
    if len(sys.argv) == 2:
        log_dir = Path(sys.argv[1]).expanduser()
    else:
        log_dir = (
            Path.home()
            / ".local/share/wineprefixes/uu-remote/drive_c/Program Files"
            / "Netease/GameViewer/log/server/log"
        )
    if not log_dir.is_dir():
        print(f"UU log directory is unavailable: {log_dir}", file=sys.stderr)
        return 1
    lines, status = summarize(log_dir)
    print("\n".join(lines))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
