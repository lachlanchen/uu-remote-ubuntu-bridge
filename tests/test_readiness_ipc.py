import os
from itertools import product
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReadinessTests(unittest.TestCase):
    def test_live_echo_is_required_and_startup_is_retried(self):
        source = (ROOT / 'scripts/verify.sh').read_text()
        start = source.index('structured_release_ipc_ready() {')
        function = source[start:source.index('\nwhile (($#));', start)]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            wine = root / 'wine'
            wine.write_text('''#!/bin/bash
if [[ "$2" == version || "$2" == --version ]]; then
    if [[ "$TEST_VERSION" == 4.44.1.3978 && "$2" == version ]]; then
        printf 'cliVersion: %s\nmessage: Main application is not running\n' "$TEST_REPORTED"
        exit
    fi
    [[ "$MODE" != wrong-version ]] || { echo 4.42.0.9999; exit; }
    echo "$TEST_REPORTED"
elif [[ "$2" == echo ]]; then
    n=$(cat "$COUNTER" 2>/dev/null || echo 0)
    echo $((n+1)) >"$COUNTER"
    [[ "$MODE" != missing-ipc ]] || exit 1
    [[ "$MODE" != delayed || "$n" -ge 2 ]] || exit 1
    [[ "$MODE" != wrong-echo ]] || { echo stale; exit; }
    if [[ "$TEST_VERSION" == 4.44.1.3978 && "$MODE" != unformatted-echo ]]; then
        printf 'echo: %s\\r\\n' "$3"
    else
        echo "$3"
    fi
fi
''')
            wine.chmod(0o700)
            (root / 'display').write_text(':90\n')
            (root / 'auth').touch()
            (root / 'cli').touch()
            setup = '''set -euo pipefail
release_version="$TEST_VERSION"
reported_version="$TEST_REPORTED"
wine_bin="$TEST_ROOT/wine"
uuyc_cli="$TEST_ROOT/cli"
wine_prefix="$TEST_ROOT/prefix"
private_display_file="$TEST_ROOT/display"
bridge_xauthority_file="$TEST_ROOT/auth"
sleep() { :; }
'''
            for (version, reported), (mode, success, calls) in product((
                ('4.42.1.2835', '4.42.0.2770'),
                ('4.44.1.3978', '4.44.1.3978'),
            ), (
                ('ready', True, 1), ('delayed', True, 3),
                ('wrong-version', False, 0), ('missing-ipc', False, 10),
                ('wrong-echo', False, 10),
                ('unformatted-echo', False, 10),
            )):
                with self.subTest(version=version, mode=mode):
                    if mode == 'unformatted-echo' and version != '4.44.1.3978':
                        success, calls = True, 1
                    counter = root / 'counter'
                    counter.unlink(missing_ok=True)
                    result = subprocess.run(['bash', '-c', setup + function +
                                             '\nstructured_release_ipc_ready\n'],
                                            env=dict(os.environ, TEST_ROOT=temp, MODE=mode,
                                                     TEST_VERSION=version, TEST_REPORTED=reported,
                                                     COUNTER=str(counter)),
                                            capture_output=True, text=True, timeout=5)
                    self.assertEqual(result.returncode == 0, success, result.stderr)
                    self.assertEqual(int(counter.read_text()) if counter.exists() else 0, calls)
