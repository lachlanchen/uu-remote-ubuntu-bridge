"""Physical input must reach the configured native desktop, despite Wine ACKs."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get('UURB_TEST_WINE') == '1', 'isolated Wine test')
class InputRoutingTests(unittest.TestCase):
    def test_native_route_overrides_false_success_and_preserves_rdp(self):
        wine = os.environ.get('UURB_WINE_BIN', '/opt/wine-stable/bin/wine')
        wineserver = os.environ.get('UURB_WINESERVER_BIN', '/opt/wine-stable/bin/wineserver')
        with tempfile.TemporaryDirectory() as tmp:
            probe = str(Path(tmp) / 'input-routing.exe')
            subprocess.run(['x86_64-w64-mingw32-gcc', '-std=c11', '-O2',
                            '-Wall', '-Wextra', '-Werror', '-o', probe,
                            str(ROOT / 'tests/probes/uu_input_routing_probe.c'),
                            '-luser32'], check=True)
            xvfb = subprocess.Popen(['Xvfb', '-displayfd', '1', '-screen', '0',
                                     '640x480x24', '-nolisten', 'tcp'],
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            env = dict(os.environ, DISPLAY=':' + xvfb.stdout.readline().decode().strip(),
                       XAUTHORITY='', WINEPREFIX=tmp + '/wine', WINEDEBUG='-all',
                       WINEDLLOVERRIDES='mscoree,mshtml=')
            try:
                result = subprocess.run([wine, probe], env=env, capture_output=True, timeout=90)
                self.assertEqual(result.returncode, 0,
                                 result.stdout.decode(errors='replace') +
                                 result.stderr.decode(errors='replace'))
                self.assertIn(b'PASS:', result.stdout)
            finally:
                subprocess.run([wineserver, '-k'], env=env, capture_output=True, timeout=10)
                xvfb.terminate(); xvfb.wait(timeout=5); xvfb.stdout.close()
