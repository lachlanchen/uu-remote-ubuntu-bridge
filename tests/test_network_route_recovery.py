"""Exercise the actual Bash route debounce without networks or desktop services."""

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "scripts/uu-remote-bridge").read_text()
START = SOURCE.index("route_change_requires_restart() {\n")
FUNCTION = SOURCE[START:SOURCE.index("\n}\n", START) + 3]


class NetworkRouteRecoveryTests(unittest.TestCase):
    def decisions(self, routes):
        # Run under production's errexit/nounset settings. The function's false
        # result must be consumed by an if, rather than killing the supervisor.
        script = "set -Eeuo pipefail\n" + FUNCTION + """
active_network_interface=eth0
pending_network_interface=''
pending_network_checks=0
for candidate in "$@"; do
    if route_change_requires_restart "$candidate"; then
        printf 'restart\\n'
    else
        printf 'keep\\n'
    fi
done
"""
        result = subprocess.run(
            ["bash", "-c", script, "route-test", *routes],
            check=True, text=True, capture_output=True, timeout=5,
        )
        return result.stdout.splitlines()

    def test_stable_replacement_requires_three_samples(self):
        self.assertEqual(self.decisions(["wlan0"] * 3),
                         ["keep", "keep", "restart"])

    def test_brief_change_then_original_does_not_restart(self):
        self.assertEqual(self.decisions(["wlan0", "wlan0", "eth0", "wlan0"]),
                         ["keep"] * 4)

    def test_missing_route_resets_pending_change(self):
        self.assertEqual(self.decisions(["wlan0", "wlan0", "", "wlan0", "wlan0", "wlan0"]),
                         ["keep"] * 5 + ["restart"])

    def test_alternating_replacements_do_not_accumulate(self):
        self.assertEqual(self.decisions(["wlan0", "usb0", "wlan0", "usb0", "usb0", "usb0"]),
                         ["keep"] * 5 + ["restart"])

    def test_original_or_absent_route_does_not_restart(self):
        self.assertEqual(self.decisions(["", "eth0", "", "eth0"]),
                         ["keep"] * 4)

    def test_supervisor_uses_guard_and_tolerates_failed_route_probe(self):
        self.assertIn('current_default_interface="$(default_network_interface || true)"', SOURCE)
        self.assertIn('if route_change_requires_restart "$current_default_interface"; then', SOURCE)


if __name__ == "__main__":
    unittest.main()
