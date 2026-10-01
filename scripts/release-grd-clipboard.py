#!/usr/bin/env python3
"""Release only this bridge's stalled GRD clipboard FUSE requests at shutdown."""

from __future__ import annotations

import os
from pathlib import Path
import re
import sys
import time


def identity(process: Path) -> tuple[int, str, str]:
    # comm may contain spaces; starttime is field 22 after the closing ')'.
    fields = (process / "stat").read_text().rsplit(") ", 1)[1].split()
    return (process.stat().st_uid, str((process / "exe").readlink()), fields[19])


def clipboard_mounts(text: str, uid: int) -> dict[int, str]:
    result = {}
    pattern = re.compile(rf"/run/user/{uid}/gnome-remote-desktop/cliprdr-[A-Za-z0-9]+")
    for line in text.splitlines():
        before, separator, after = line.partition(" - ")
        fields, filesystem = before.split(), after.split()
        if not separator or len(fields) < 6 or len(filesystem) < 3:
            continue
        if (filesystem[0] != "fuse" or filesystem[1] != "/dev/fuse"
                or not pattern.fullmatch(fields[4])
                or f"user_id={uid}" not in filesystem[2].split(",")):
            continue
        major, colon, minor = fields[2].partition(":")
        if colon and major == "0" and minor.isdigit():
            result[int(minor)] = fields[4]
    return result


def open_connections(process: Path) -> set[int]:
    result = set()
    for fd in (process / "fd").iterdir():
        try:
            if str(fd.readlink()) != "/dev/fuse":
                continue
            text = (process / "fdinfo" / fd.name).read_text()
            match = re.search(r"^fuse_connection:\s*([0-9]+)\s*$", text, re.MULTILINE)
            if match:
                result.add(int(match[1]))
        except (FileNotFoundError, ProcessLookupError):
            continue
    return result


def release(pid: int, *, proc: Path = Path("/proc"),
            connections: Path = Path("/sys/fs/fuse/connections")) -> int:
    uid = os.getuid()
    process = proc / str(pid)
    try:
        original = identity(process)
        if original[0] != uid or Path(original[1]).name != "gnome-remote-desktop-daemon":
            return 0
        if (process / "cgroup").read_text() != (proc / "self/cgroup").read_text():
            return 0
        # Called after TERM and the launcher's grace period, before SIGKILL.
        if not re.search(r"^State:\s+D\b", (process / "status").read_text(), re.MULTILINE):
            return 0
        if (process / "wchan").read_text().strip() != "request_wait_answer":
            return 0
        mounts = clipboard_mounts((process / "mountinfo").read_text(), uid)
        released = 0
        for number in open_connections(process) & mounts.keys():
            control = connections / str(number)
            if control.stat().st_uid != uid or int((control / "waiting").read_text()) <= 0:
                continue
            # Check identity and ownership again immediately before touching fusectl.
            if identity(process) != original or number not in open_connections(process):
                continue
            current = clipboard_mounts((process / "mountinfo").read_text(), uid)
            if current.get(number) != mounts[number]:
                continue
            (control / "abort").write_text("1\n")
            released += 1
            print(f"Released stalled GRD clipboard connection {number} during shutdown.")
        if released:
            # Let GRD's FUSE thread unmount before the launcher's final KILL pass.
            for _ in range(10):
                if not process.exists():
                    break
                time.sleep(0.05)
        return released
    except (FileNotFoundError, ProcessLookupError):
        return 0
    except (OSError, ValueError, IndexError) as error:
        print(f"GRD clipboard shutdown check skipped: {error}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    if len(sys.argv) != 2 or not sys.argv[1].isdigit() or int(sys.argv[1]) <= 1:
        raise SystemExit("usage: release-grd-clipboard.py GRD_PID")
    release(int(sys.argv[1]))
