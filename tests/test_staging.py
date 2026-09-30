import shlex
import subprocess
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


class StagingTests(unittest.TestCase):
    def test_systemd_bind_property_preserves_spaces_quotes_and_backslashes(self):
        source = (REPO / "scripts/stage-uu-release.sh").read_text()
        function = source.split("systemd_bind_path() {", 1)[1].split("\n}\n", 1)[0]
        for path in ('/tmp/Program Files/setup.exe', '/tmp/a"b/c\\d.exe'):
            with self.subTest(path=path):
                result = subprocess.run(
                    ["bash", "-c", "systemd_bind_path() {" + function
                     + '\n}\nsystemd_bind_path "$1" /input/uu-installer.exe', "test", path],
                    text=True, capture_output=True, check=True,
                )
                self.assertEqual(shlex.split(result.stdout), [path + ":/input/uu-installer.exe"])
        for path in ('/tmp/with:colon', '/tmp/with\nnewline'):
            result = subprocess.run(
                ["bash", "-c", "systemd_bind_path() {" + function
                 + '\n}\nsystemd_bind_path "$1" /work', "test", path],
                text=True, capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)

    def test_sandbox_startup_is_bounded_and_honors_passwordless_sudo(self):
        source = (REPO / "scripts/stage-uu-release.sh").read_text()
        self.assertIn("sudo -n true 2>/dev/null || sudo -v", source)
        self.assertIn("--property=RuntimeMaxSec=360", source)
        self.assertIn("120s", source)
        self.assertIn('--property="BindReadOnlyPaths=$installer_bind"', source)
