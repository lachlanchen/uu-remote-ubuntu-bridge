"""Test argv forwarding without opening a real UU terminal or desktop."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class UUShellTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="uu-shell-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.script = self.root / "uu-shell"
        shutil.copy2(ROOT / "scripts/uu-shell", self.script)
        fake = self.root / "uu-ssh"
        fake.write_text("#!/bin/bash\nprintf '%s\\0' \"$@\"\nexit 17\n")
        fake.chmod(0o700)

    def run_shell(self, *args):
        return subprocess.run(["bash", str(self.script), *args], capture_output=True)

    def test_fresh_session_by_default_and_preserves_exit_status(self):
        result = self.run_shell("lab")
        self.assertEqual(result.returncode, 17)
        self.assertEqual(result.stdout.split(b"\0")[:-1],
                         [b"terminal", b"lab", b"--new-session"])

    def test_explicit_session_actions_are_not_changed(self):
        for options in (("--session-id", "42"), ("--session-id=42",),
                        ("--list-sessions",), ("--new-session",),
                        ("--kill-session", "42"), ("--kill-session=42",)):
            with self.subTest(options=options):
                result = self.run_shell("lab", *options)
                expected = ["terminal", "lab", *options]
                self.assertEqual(result.stdout.split(b"\0")[:-1],
                                 [item.encode() for item in expected])

    def test_arguments_are_forwarded_without_shell_interpretation(self):
        token = "quotes ' 中文 $(touch SHOULD_NOT_EXIST)"
        result = self.run_shell("lab", "--session-id", token)
        self.assertEqual(result.stdout.split(b"\0")[:-1],
                         [b"terminal", b"lab", b"--session-id", token.encode()])

    def test_help_does_not_call_vendor_helper(self):
        for options in ((), ("--help",), ("-h",)):
            result = self.run_shell(*options)
            self.assertEqual(result.returncode, 0)
            self.assertIn(b"Usage: uu-shell PEER", result.stdout)
            self.assertNotIn(b"\0", result.stdout)

    def test_installer_lifecycle_includes_helper(self):
        for relative in ("install.sh", "uninstall.sh", "scripts/upgrade-uu-remote.sh",
                         "scripts/runtime-source-digest"):
            with self.subTest(relative=relative):
                self.assertIn("uu-shell", (ROOT / relative).read_text())


if __name__ == "__main__":
    unittest.main()
