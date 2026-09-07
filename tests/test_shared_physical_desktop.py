"""Exercise target selection when XRDP overwrites the user-manager DISPLAY."""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PhysicalTargetTests(unittest.TestCase):
    def test_verifier_accepts_only_live_matching_vnc_transports(self):
        source = (ROOT / 'scripts/verify.sh').read_text()
        function = source[source.index('vnc_relay_ready() {'):
                          source.index('x11_route_ready() {')]
        function = function.replace('/usr/bin/ss ', 'probe_ss ')
        script = r'''
set -eu
shared_vnc_port=$1
mode=$2
state_dir=$3
pgrep() {
    if [[ "$*" == *vncviewer* ]]; then
        [[ "$mode" != wrong-viewer ]] || return 1
    elif [[ -n "$shared_vnc_port" ]]; then
        [[ "$*" == *"-rfbport 5922"* ]] || return 1
    else
        [[ "$*" == *"-autoport 5922"* ]] || return 1
    fi
    printf '%s\n' "$$"
}
probe_ss() {
    [[ "$mode" != missing-listener ]] || return 0
    pid=$$
    [[ "$mode" != wrong-owner ]] || pid=1
    printf 'LISTEN 0 32 127.0.0.1:5922 0.0.0.0:* users:(("x11vnc",pid=%s,fd=8))\n' "$pid"
}
''' + function + '\nvnc_relay_ready\n'
        with tempfile.TemporaryDirectory() as temporary:
            (Path(temporary) / 'desktop-x11vnc.log').write_text('PORT=5922\n')
            for port, mode, success in (
                ('5922', 'ready', True),
                ('', 'ready', True),
                ('5922', 'missing-listener', False),
                ('5922', 'wrong-owner', False),
                ('5922', 'wrong-viewer', False),
                ('6000', 'ready', False),
            ):
                with self.subTest(port=port, mode=mode):
                    result = subprocess.run(
                        ['bash', '-c', script, 'probe', port, mode, temporary,
                         '-display', ':0'],
                        capture_output=True, text=True, timeout=5,
                    )
                    self.assertEqual(result.returncode == 0, success, result.stderr)

    def test_vnc_does_not_require_unused_freerdp_binary(self):
        source = (ROOT / 'scripts/verify.sh').read_text()
        self.assertIn('if [[ "$desktop_relay" == vnc ]]; then\n'
                      "    printf 'INFO  FreeRDP is not used", source)
        self.assertIn('elif [[ -f "$freerdp" ]]', source)

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
