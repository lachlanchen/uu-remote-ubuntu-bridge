#!/usr/bin/env python3
"""Inspect UU's dedicated Wine registry for unsupported device buildup."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


SEPARATOR = r"\\"
HID_CLASS_GUID = "{745a17a0-74d3-11d0-b6fe-00a0c90f57da}"
MOUSE_CLASS_GUID = "{4d36e96f-e325-11ce-bfc1-08002be10318}"


@dataclass(frozen=True)
class RegistryStatus:
    registry_bytes: int
    winebth_start: int | None
    winebth_sections: int
    winebth_devices: int
    gvinput_hid_roots: int
    gvinput_mouse_roots: int
    unexpected_hid_roots: int
    unexpected_mouse_roots: int
    gvinput_hid_class_keys: int
    gvinput_mouse_class_keys: int
    gvinput_services: int

    @property
    def clean(self) -> bool:
        return (
            self.winebth_start == 4
            and self.winebth_devices == 0
            and self.gvinput_hid_roots == 0
            and self.gvinput_mouse_roots == 0
            and self.unexpected_hid_roots == 0
            and self.unexpected_mouse_roots == 0
            and self.gvinput_hid_class_keys == 0
            and self.gvinput_mouse_class_keys == 0
            and self.gvinput_services == 0
        )


def parse_registry(path: Path) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    body: list[str] = []

    with path.open(encoding="utf-8", errors="replace") as stream:
        for raw_line in stream:
            line = raw_line.rstrip("\n")
            if line.startswith("[") and "] " in line:
                if current is not None:
                    sections[current] = body
                current = line[1 : line.rfind("] ")].lower()
                body = []
            elif current is not None:
                body.append(line)
    if current is not None:
        sections[current] = body
    return sections


def section_parts(name: str) -> list[str]:
    return name.split(SEPARATOR)


def body_text(lines: list[str]) -> str:
    return "\n".join(lines).lower()


def dword_value(lines: list[str], name: str) -> int | None:
    pattern = re.compile(
        rf'^"{re.escape(name)}"=dword:([0-9a-f]{{8}})$',
        re.IGNORECASE,
    )
    for line in lines:
        match = pattern.match(line)
        if match:
            return int(match.group(1), 16)
    return None


def windows_key(name: str) -> str:
    parts = section_parts(name)
    if len(parts) < 2 or parts[:2] != ["system", "controlset001"]:
        raise ValueError(f"unsupported registry section: {name}")
    return (
        "HKEY_LOCAL_MACHINE\\System\\CurrentControlSet\\"
        + "\\".join(parts[2:])
    )


def inspect(
    sections: dict[str, list[str]], registry_bytes: int
) -> tuple[RegistryStatus, list[str]]:
    hid_roots: list[str] = []
    mouse_roots: list[str] = []
    unexpected_hid: list[str] = []
    unexpected_mouse: list[str] = []
    hid_classes: list[str] = []
    mouse_classes: list[str] = []
    services: list[str] = []
    winebth_sections: list[str] = []
    winebth_device_roots: set[tuple[str, ...]] = set()
    winebth_start: int | None = None

    for name, lines in sections.items():
        parts = section_parts(name)
        text = body_text(lines)

        if parts == ["system", "controlset001", "services", "winebth"]:
            winebth_start = dword_value(lines, "Start")
        if parts[:4] == ["system", "controlset001", "enum", "winebth"]:
            winebth_sections.append(name)
            if len(parts) >= 6 and parts[4] == "device":
                winebth_device_roots.add(tuple(parts[:6]))

        if (
            len(parts) == 6
            and parts[:5]
            == ["system", "controlset001", "enum", "root", "hidclass"]
        ):
            if (
                "netease\\\\gvinput" in text
                and '"service"="gvinput"' in text
            ):
                hid_roots.append(name)
            else:
                unexpected_hid.append(name)

        if (
            len(parts) == 6
            and parts[:5]
            == ["system", "controlset001", "enum", "root", "mouse"]
        ):
            if "hid\\\\gvinput&col01" in text:
                mouse_roots.append(name)
            else:
                unexpected_mouse.append(name)

        if (
            len(parts) == 6
            and parts[:5]
            == ["system", "controlset001", "control", "class", HID_CLASS_GUID]
            and parts[5].isdigit()
            and '"infpath"="gvinput.inf"' in text
        ):
            hid_classes.append(name)

        if (
            len(parts) == 6
            and parts[:5]
            == [
                "system",
                "controlset001",
                "control",
                "class",
                MOUSE_CLASS_GUID,
            ]
            and parts[5].isdigit()
            and '"infpath"="gvinputmf.inf"' in text
        ):
            mouse_classes.append(name)

        if (
            len(parts) >= 4
            and parts[:3] == ["system", "controlset001", "services"]
            and parts[3] in {"gvinput", "gvinputmf"}
        ):
            services.append(name)

    delete_keys: list[str] = []
    if winebth_device_roots:
        delete_keys.append(
            r"HKEY_LOCAL_MACHINE\System\CurrentControlSet\Enum\WINEBTH"
        )
    if hid_roots and not unexpected_hid:
        delete_keys.append(
            r"HKEY_LOCAL_MACHINE\System\CurrentControlSet\Enum\ROOT\HIDCLASS"
        )
    if mouse_roots and not unexpected_mouse:
        delete_keys.append(
            r"HKEY_LOCAL_MACHINE\System\CurrentControlSet\Enum\ROOT\MOUSE"
        )
    delete_keys.extend(windows_key(name) for name in hid_classes)
    delete_keys.extend(windows_key(name) for name in mouse_classes)
    if services:
        delete_keys.extend(
            [
                r"HKEY_LOCAL_MACHINE\System\CurrentControlSet\Services\gvinput",
                r"HKEY_LOCAL_MACHINE\System\CurrentControlSet\Services\gvinputmf",
            ]
        )

    status = RegistryStatus(
        registry_bytes=registry_bytes,
        winebth_start=winebth_start,
        winebth_sections=len(winebth_sections),
        winebth_devices=len(winebth_device_roots),
        gvinput_hid_roots=len(hid_roots),
        gvinput_mouse_roots=len(mouse_roots),
        unexpected_hid_roots=len(unexpected_hid),
        unexpected_mouse_roots=len(unexpected_mouse),
        gvinput_hid_class_keys=len(hid_classes),
        gvinput_mouse_class_keys=len(mouse_classes),
        gvinput_services=len({section_parts(name)[3] for name in services}),
    )
    return status, sorted(set(delete_keys))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("inspect", "plan", "preflight", "verify"))
    parser.add_argument("prefix", type=Path)
    args = parser.parse_args()

    registry = args.prefix / "system.reg"
    if not registry.is_file():
        parser.error(f"Wine system registry does not exist: {registry}")
    sections = parse_registry(registry)
    status, delete_keys = inspect(sections, registry.stat().st_size)

    if args.command == "inspect":
        payload = asdict(status)
        payload["clean"] = status.clean
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if status.unexpected_hid_roots or status.unexpected_mouse_roots:
        print(
            "refusing broad ROOT device cleanup because unrelated devices "
            "share the target subtree",
            file=sys.stderr,
        )
        return 1

    if args.command == "plan":
        # Bash mapfile treats even one blank line as a deletion target.
        if delete_keys:
            print("\n".join(delete_keys))
        return 0

    if args.command == "preflight":
        print(
            "Wine device registry: "
            f"{status.winebth_devices} Bluetooth device(s), "
            f"{status.gvinput_hid_roots} gvinput HID root(s), "
            f"{status.gvinput_mouse_roots} gvinput mouse root(s), "
            f"{status.gvinput_hid_class_keys + status.gvinput_mouse_class_keys} "
            "gvinput class key(s)"
        )
        return 0

    if status.clean:
        print("Wine device registry hygiene is active")
        return 0
    print(json.dumps(asdict(status), sort_keys=True), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
