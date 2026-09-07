"""Opt-in checks of the shipped restart policy in an isolated user unit."""

import configparser
import os
from pathlib import Path
import subprocess
import time
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(
    os.environ.get('UURB_TEST_SYSTEMD') == '1',
    'set UURB_TEST_SYSTEMD=1 to test an isolated live systemd user unit',
)
class ServiceRecoveryTests(unittest.TestCase):
    def test_clean_exit_recovers_repeatedly_but_explicit_stop_stays_stopped(self):
        unit = configparser.ConfigParser(interpolation=None, strict=False)
        unit.read(ROOT / 'systemd' / 'uu-remote-bridge.service')
        name = f'uu-recovery-test-{uuid.uuid4().hex}.service'
        properties = [
            f'Restart={unit["Service"]["Restart"]}',
            f'StartLimitIntervalSec={unit["Unit"]["StartLimitIntervalSec"]}',
            'RestartSec=100ms',
        ]
        command = ['systemd-run', '--user', '--quiet', '--unit', name]
        for setting in properties:
            command.extend(['--property', setting])
        command.append('/usr/bin/true')
        ctl = ['systemctl', '--user']
        try:
            subprocess.run(command, check=True, capture_output=True, timeout=10)
            deadline = time.monotonic() + 15
            restarts = 0
            while time.monotonic() < deadline:
                result = subprocess.run(
                    ctl + ['show', name, '-p', 'NRestarts', '--value'],
                    check=True, capture_output=True, text=True, timeout=5,
                )
                restarts = int(result.stdout.strip() or '0')
                if restarts >= 6:
                    break
                time.sleep(0.1)
            self.assertGreaterEqual(restarts, 6, 'clean exit stopped retrying')
            subprocess.run(ctl + ['stop', name], check=True, timeout=10)
            time.sleep(0.5)
            result = subprocess.run(
                ctl + ['show', name, '-p', 'ActiveState', '--value'],
                capture_output=True, text=True, timeout=5,
            )
            self.assertEqual(result.stdout.strip(), 'inactive', result.stderr)
        finally:
            subprocess.run(ctl + ['stop', name], capture_output=True, timeout=10)
            subprocess.run(
                ctl + ['reset-failed', name], capture_output=True, timeout=10,
            )
