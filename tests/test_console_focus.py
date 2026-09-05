"""Exercise console focus helpers with fake X commands, never a live desktop."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SOURCE = (Path(__file__).resolve().parents[1] / "scripts/uu-remote-console").read_text()


class ConsoleFocusTests(unittest.TestCase):
    def run_helpers(self, mode, commands):
        with tempfile.TemporaryDirectory(prefix="uu-focus-test-") as temp:
            directory = Path(temp)
            xdo = directory / "xdotool"
            xdo.write_text('''#!/usr/bin/env bash
case "$*" in
  *search*gameviewer*) printf '100\\n200\\n';;
  *getwindowname*) printf 'UU Remote\\n';;
  *search*Ubuntu-Desktop-Relay*)
    [[ "$FOCUS_TEST_MODE" == rdp ]] || exit 1
    printf '101\\n';;
  *search*realvnc-vncviewer*)
    [[ "$FOCUS_TEST_MODE" == vnc ]] || exit 1
    printf '202\\n';;
  *) printf '%s\\n' "$*" >> "$FOCUS_TEST_LOG";;
esac
''')
            xprop = directory / "xprop"
            xprop.write_text('''#!/usr/bin/env bash
if [[ "$*" == *100* ]]; then
    printf 'WM_STATE(WM_STATE): window state: Normal\\n'
else
    printf 'WM_STATE: not found.\\n'
fi
''')
            xdo.chmod(0o700)
            xprop.chmod(0o700)
            # Source only definitions, substitute private fake X executables,
            # and override discovery so the real X server is never used.
            script = SOURCE.split('case "${1:-open}" in', 1)[0]
            script = script.replace("/usr/bin/xdotool", str(xdo)).replace("/usr/bin/xprop", str(xprop))
            script += '\ndiscover_bridge() { bridge_display=:99; bridge_xauthority=/none; }\n'
            script += commands
            env = dict(os.environ, HOME=temp, XDG_RUNTIME_DIR=temp, XDG_STATE_HOME=temp,
                       FOCUS_TEST_MODE=mode, FOCUS_TEST_LOG=str(directory / "calls"))
            result = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True)
            calls = (directory / "calls").read_text() if (directory / "calls").exists() else ""
            return result, calls, (directory / "uu-remote-bridge/console-focus").exists()

    def test_restores_rdp(self):
        result, calls, lease = self.run_helpers("rdp", "focus_client; release_client")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("windowactivate 101", calls)
        self.assertFalse(lease)

    def test_restores_native_vnc_and_filters_toast(self):
        result, calls, lease = self.run_helpers("vnc", "focus_client; release_client")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("windowmap 100 windowactivate --sync 100", calls)
        self.assertNotIn("200", calls)
        self.assertIn("windowactivate 202", calls)
        self.assertFalse(lease)

    def test_missing_relay_still_releases_lease(self):
        result, calls, lease = self.run_helpers("none", "focus_client; release_client")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("windowactivate 101", calls)
        self.assertNotIn("windowactivate 202", calls)
        self.assertFalse(lease)


if __name__ == "__main__":
    unittest.main()
