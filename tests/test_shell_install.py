import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('install_shell', ROOT / 'scripts/install-shell-tools.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class ShellInstallTests(unittest.TestCase):
    def test_native_only_install_needs_no_fleet_and_retains_exact_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            old = home / '.local/bin/uu-shell'
            old.parent.mkdir(parents=True)
            old.write_bytes(b'old-shell\n')
            inventory = home / 'inventory.json'
            inventory.write_text(json.dumps({'lab': {'name':'lab', 'device_id':'test-id',
                'shell_transport':'terminal', 'terminal_shell':'zsh'}}))
            with patch.object(Path, 'home', return_value=home), \
                 patch.object(sys, 'argv', ['install-shell-tools.py', '--inventory', str(inventory)]):
                installer.main()
                before = old.stat().st_mtime_ns
                installer.main()
            self.assertEqual(old.stat().st_mtime_ns, before)
            backups = list((home / '.local/state/uu-shell-tools/backups').iterdir())
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), b'old-shell\n')
            self.assertFalse((home / '.ssh').exists())
            self.assertEqual((home / '.config/uu-ssh/peers/lab.json').stat().st_mode & 0o777, 0o600)

    def test_unenrolled_peer_is_rejected_before_any_shortcut_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            bundle = home / '.config/lazytunnel-fleet/bundle.json'
            bundle.parent.mkdir(parents=True)
            bundle.write_text('{"aliases":["known"]}')
            inventory = home / 'inventory.json'
            inventory.write_text(json.dumps({'lab': {'name':'lab', 'fleet_peer':'unknown',
                'shell_transport':'lazytunnel', 'terminal_shell':'powershell'}}))
            with patch.object(Path, 'home', return_value=home), \
                 patch.object(sys, 'argv', ['installer', '--inventory', str(inventory)]):
                with self.assertRaisesRegex(ValueError, 'not enrolled'):installer.main()
            self.assertFalse((home / '.local/bin').exists())
