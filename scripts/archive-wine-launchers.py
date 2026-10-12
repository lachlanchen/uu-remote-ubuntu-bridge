#!/usr/bin/env python3
"""Archive visible UU shortcuts belonging to one Wine prefix (dry-run by default)."""

import argparse
import configparser
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile


def owned_shortcut(path: Path, prefix: Path) -> str | None:
    if path.is_symlink() or not path.is_file():
        return None
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    try:
        parser.read_string(path.read_text(encoding="utf-8"))
        entry = parser["Desktop Entry"]
        if any(entry.get(key, "").lower() == "true" for key in ("NoDisplay", "Hidden")):
            return None
        args = shlex.split(entry["Exec"])
        if not args or args.pop(0) not in ("env", "/usr/bin/env"):
            return None
        environment = {}
        while args and "=" in args[0]:
            key, value = args.pop(0).split("=", 1)
            environment[key] = value
        owner = environment.get("WINEPREFIX", "")
        if not owner or not Path(owner).is_absolute() or Path(owner).resolve() != prefix.resolve():
            return None
        if len(args) < 2 or Path(args[0]).name not in ("wine", "wine64"):
            return None
        target = args[1].replace("\\", "/").rsplit("/", 1)[-1]
        if target.casefold() in ("uu远程.lnk", "uu remote.lnk", "gameviewer.exe"):
            return target
    except (OSError, UnicodeError, configparser.Error, KeyError, ValueError):
        pass
    return None


def desktop_directory() -> Path:
    try:
        result = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True,
                                text=True, timeout=3, check=True)
        value = Path(result.stdout.strip())
        if value.is_absolute():
            return value
    except (OSError, subprocess.SubprocessError):
        pass
    return Path.home() / "Desktop"


def archive(prefix: Path, applications: Path, desktop: Path, state: Path,
            apply: bool = False) -> list[dict[str, str]]:
    candidates = set((applications / "wine/Programs").rglob("*.desktop"))
    candidates.update(desktop.glob("*.desktop"))
    selected = set()
    for path in candidates:
        target = owned_shortcut(path, prefix)
        if target:
            selected.add(path)
            # Only the paired Desktop .lnk named by this owned launcher.
            paired = path.with_suffix(".lnk")
            if path.parent == desktop and target == paired.name and paired.is_file() and not paired.is_symlink():
                selected.add(paired)
    if not selected:
        return []
    backup = None
    if apply:
        state.mkdir(parents=True, exist_ok=True, mode=0o700)
        backup = Path(tempfile.mkdtemp(prefix="wine-launchers-", dir=state))
    records = []
    for index, source in enumerate(sorted(selected)):
        destination = backup / f"{index}-{source.name}" if backup else None
        record = {"source": str(source), "backup": str(destination) if destination else "dry-run"}
        records.append(record)
        if backup:
            # Persist the restore map before moving each file. If interrupted,
            # original or backup still exists; a rerun only sees remaining entries.
            journal = backup / "restore-map.json"
            journal.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n")
            journal.chmod(0o600)
            shutil.move(str(source), str(destination))
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wine-prefix", type=Path, required=True)
    parser.add_argument("--desktop-dir", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    home = Path.home()
    data = Path(os.environ.get("XDG_DATA_HOME", home / ".local/share"))
    state = Path(os.environ.get("XDG_STATE_HOME", home / ".local/state")) / "uu-remote-bridge/launcher-backups"
    records = archive(args.wine_prefix, data / "applications",
                      args.desktop_dir or desktop_directory(), state, args.apply)
    print(json.dumps({"applied": args.apply, "shortcuts": records}, ensure_ascii=False))


if __name__ == "__main__":
    main()
