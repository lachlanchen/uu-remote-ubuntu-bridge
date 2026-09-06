"""Exercise target selection when XRDP overwrites the user-manager DISPLAY."""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PhysicalTargetTests(unittest.TestCase):
    def test_gdm_desktop_wins_with_xrdp_manager_environment(self):
        source = (ROOT / 'scripts/uu-remote-bridge').read_text()
        functions = source[source.index('normalized_x_display() {'):
                           source.index('select_desktop_candidate() {')]
        script = '''set -eu
desktop_target=physical
manager_display=:10.0
manager_bus=unix:path=/run/user/$UID/bus
''' + functions + '''
desktop_candidate_matches_target :0 '' '' "$manager_bus" "/run/user/$UID/gdm/Xauthority"
if desktop_candidate_matches_target :10.0 xrdp-sesman '' unix:path=/tmp/rdp ''; then
    exit 1
fi
if desktop_candidate_matches_target :10.0 xrdp-sesman '' "$manager_bus" ''; then
    exit 1
fi
# Existing explicit-display mode and XRDP mode remain available.
desktop_target=:11
desktop_candidate_matches_target :11.0 '' '' '' ''
desktop_target=xrdp
desktop_candidate_matches_target :10.0 xrdp-sesman '' '' ''
'''
        subprocess.run(['bash', '-c', script], check=True)

    def test_invalid_shared_port_fails_without_starting_a_server(self):
        source = (ROOT / 'scripts/uu-remote-bridge').read_text()
        function = source[source.index('reuse_shared_vnc_relay() {'):
                          source.index('start_desktop_relay() {')]
        for port in ('0', '22', '5899', '6000', '5922;echo bad'):
            script = 'log() { :; }\n' + function + '\nshared_vnc_port=$1\nreuse_shared_vnc_relay\n'
            result = subprocess.run(['bash', '-c', script, 'test', port],
                                    capture_output=True, timeout=3)
            self.assertNotEqual(result.returncode, 0, port)


if __name__ == '__main__':
    unittest.main()
