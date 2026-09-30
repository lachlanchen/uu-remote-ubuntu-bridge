import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


class HostCompatibilityTests(unittest.TestCase):
    def run_check(self, architecture):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            uname = root / "uname"
            uname.write_text(f"#!/bin/sh\nprintf '%s\\n' '{architecture}'\n")
            uname.chmod(0o755)
            env = dict(os.environ, HOME=str(home), PATH=f"{root}:/usr/bin:/bin")
            result = subprocess.run(
                [str(REPO / "install.sh"), "--check-host"],
                env=env, capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(list(home.iterdir()), [], "preflight must not write HOME")
            return result

    def test_arm_host_reports_runtime_boundary_before_installing(self):
        for architecture in ("aarch64", "arm64", "armv7l"):
            with self.subTest(architecture=architecture):
                result = self.run_check(architecture)
                self.assertEqual(result.returncode, 1)
                self.assertIn("not a supported runtime", result.stderr)
                self.assertIn("x86 CPU emulation", result.stderr)
                self.assertIn("docs/compatibility.md", result.stderr)

    def test_supported_cpu_does_not_claim_desktop_acceptance(self):
        result = self.run_check("x86_64")
        os_release = Path("/etc/os-release").read_text()
        if 'ID=ubuntu\n' in os_release and 'VERSION_ID="24.04"' in os_release:
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("does not install packages", result.stdout)
            self.assertIn("logged-in GNOME 46", result.stdout)
        else:
            self.assertEqual(result.returncode, 1)
            self.assertIn("Only Ubuntu 24.04", result.stderr)
