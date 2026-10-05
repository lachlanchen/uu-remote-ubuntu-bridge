import json
import subprocess
import tempfile
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
INSPECTOR = REPOSITORY / "scripts" / "inspect-wine-device-registry.py"


class WineRegistryTests(unittest.TestCase):
    def write_registry(self, root: Path, body: str) -> Path:
        prefix = root / "prefix"
        prefix.mkdir()
        (prefix / "system.reg").write_text(
            "WINE REGISTRY Version 2\n\n" + body,
            encoding="utf-8",
        )
        return prefix

    def test_inspector_finds_only_audited_stale_device_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            prefix = self.write_registry(
                Path(temporary),
                r"""
[System\\ControlSet001\\Services\\winebth] 1
"Start"=dword:00000003

[System\\ControlSet001\\Enum\\WINEBTH\\DEVICE\\A] 1
"DeviceDesc"="Bluetooth device"

[System\\ControlSet001\\Enum\\WINEBTH\\DEVICE\\A\\Properties] 1
"Property"="nested device metadata"

[System\\ControlSet001\\Enum\\ROOT\\HIDCLASS\\0000] 1
"DeviceDesc"="gvinput Device"
"HardwareId"=str(7):"netease\\gvinput\0"
"Service"="gvinput"

[System\\ControlSet001\\Enum\\ROOT\\MOUSE\\0000] 1
"DeviceDesc"="HID-compliant mouse"
"HardwareId"=str(7):"HID\\GVInput&Col01\0"

[System\\ControlSet001\\Control\\Class\\{745a17a0-74d3-11d0-b6fe-00a0c90f57da}\\0004] 1
"InfPath"="gvinput.inf"

[System\\ControlSet001\\Control\\Class\\{4D36E96F-E325-11CE-BFC1-08002BE10318}\\0000] 1
"InfPath"="gvinputmf.inf"

[System\\ControlSet001\\Services\\gvinput] 1
"Start"=dword:00000003

[System\\ControlSet001\\Services\\gvinputmf] 1
"Start"=dword:00000003
""",
            )
            inspected = subprocess.run(
                [str(INSPECTOR), "inspect", str(prefix)],
                check=True,
                capture_output=True,
                text=True,
            )
            status = json.loads(inspected.stdout)
            self.assertEqual(1, status["winebth_devices"])
            self.assertEqual(1, status["gvinput_hid_roots"])
            self.assertEqual(1, status["gvinput_mouse_roots"])
            self.assertEqual(2, status["gvinput_services"])
            self.assertFalse(status["clean"])

            plan = subprocess.run(
                [str(INSPECTOR), "plan", str(prefix)],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            self.assertIn(r"Enum\WINEBTH", plan)
            self.assertIn(r"Enum\ROOT\HIDCLASS", plan)
            self.assertIn(r"Enum\ROOT\MOUSE", plan)
            self.assertIn(r"Services\gvinput", plan)
            self.assertIn(r"Services\gvinputmf", plan)

    def test_inspector_accepts_disabled_bluetooth_with_only_a_radio(self):
        with tempfile.TemporaryDirectory() as temporary:
            prefix = self.write_registry(
                Path(temporary),
                r"""
[System\\ControlSet001\\Services\\winebth] 1
"Start"=dword:00000004

[System\\ControlSet001\\Enum\\WINEBTH\\RADIO\\HCI0] 1
"DeviceDesc"="Bluetooth radio"
""",
            )
            subprocess.run(
                [str(INSPECTOR), "verify", str(prefix)],
                check=True,
                capture_output=True,
                text=True,
            )

    def test_no_device_cleanup_produces_zero_shell_deletion_entries(self):
        # Start=3 still needs the cleaner's service-disable step; Start=4 is
        # already clean. Neither case should ask Wine to delete an empty key.
        for start in (3, 4):
            with self.subTest(start=start), tempfile.TemporaryDirectory() as temporary:
                prefix = self.write_registry(
                    Path(temporary),
                    r"""
[System\\ControlSet001\\Services\\winebth] 1
"Start"=dword:0000000START

[System\\ControlSet001\\Enum\\WINEBTH\\RADIO\\HCI0] 1
"DeviceDesc"="Bluetooth radio"
""".replace("START", str(start)),
                )
                registry = prefix / "system.reg"
                original = registry.read_bytes()
                plan = subprocess.run(
                    [str(INSPECTOR), "plan", str(prefix)],
                    check=True,
                    capture_output=True,
                ).stdout
                # Exercise the same mapfile contract used by the cleaner:
                # one stray newline becomes one (empty) deletion target.
                entries = subprocess.run(
                    ["bash", "-c", 'mapfile -t keys; printf "%s" "${#keys[@]}"'],
                    input=plan,
                    check=True,
                    capture_output=True,
                ).stdout
                self.assertEqual(b"0", entries)
                self.assertEqual(b"", plan)
                self.assertEqual(original, registry.read_bytes())

    def test_disabled_service_does_not_hide_accumulated_bluetooth_devices(self):
        with tempfile.TemporaryDirectory() as temporary:
            prefix = self.write_registry(
                Path(temporary),
                r"""
[System\\ControlSet001\\Services\\winebth] 1
"Start"=dword:00000004

[System\\ControlSet001\\Enum\\WINEBTH\\DEVICE\\A] 1
"DeviceDesc"="Bluetooth device"
""",
            )
            result = subprocess.run(
                [str(INSPECTOR), "verify", str(prefix)],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, result.returncode)
            inspected = subprocess.run(
                [str(INSPECTOR), "inspect", str(prefix)],
                check=True,
                capture_output=True,
                text=True,
            )
            status = json.loads(inspected.stdout)
            self.assertEqual(4, status["winebth_start"])
            self.assertEqual(1, status["winebth_devices"])
            self.assertFalse(status["clean"])

    def test_preflight_refuses_an_unrelated_root_hid_device(self):
        with tempfile.TemporaryDirectory() as temporary:
            prefix = self.write_registry(
                Path(temporary),
                r"""
[System\\ControlSet001\\Services\\winebth] 1
"Start"=dword:00000004

[System\\ControlSet001\\Enum\\ROOT\\HIDCLASS\\0000] 1
"DeviceDesc"="Unrelated root HID device"
"HardwareId"=str(7):"vendor\\other\0"
""",
            )
            result = subprocess.run(
                [str(INSPECTOR), "preflight", str(prefix)],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("refusing broad ROOT device cleanup", result.stderr)


if __name__ == "__main__":
    unittest.main()
