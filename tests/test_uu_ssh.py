"""Isolated helper tests: never modify the real user's SSH configuration."""

import argparse
import contextlib
import importlib.machinery
import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/uu-ssh"
loader = importlib.machinery.SourceFileLoader("uu_ssh", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
helper = importlib.util.module_from_spec(spec)
loader.exec_module(helper)


class UUSSHTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="uu-ssh-test-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.home_patch = mock.patch.object(helper.Path, "home", return_value=self.home)
        self.home_patch.start()
        self.addCleanup(self.home_patch.stop)
        self.key = helper.ensure_key()  # Real ssh-keygen, isolated temporary key.
        self.args = argparse.Namespace(peer="lab", port=22709, user="alice", device_id="test-id")

    def add_peer(self, effective="hostname uu-lab\n"):
        with mock.patch.object(helper.subprocess, "run", return_value=argparse.Namespace(stdout=effective)):
            with contextlib.redirect_stdout(io.StringIO()):
                helper.add(self.args)

    def test_idempotent_preserves_original_key_config_and_device_id(self):
        config = self.home / ".ssh/config"
        original = "ServerAliveInterval 17\nHost original\n    HostName example.invalid\n"
        config.write_text(original)
        key_before = self.key.read_bytes()
        self.add_peer()
        result = config.read_bytes()
        stat = config.stat().st_mtime_ns
        self.args.device_id = None
        self.add_peer()
        self.assertEqual(config.read_bytes(), result)
        self.assertEqual(config.stat().st_mtime_ns, stat)
        self.assertEqual(self.key.read_bytes(), key_before)
        self.assertEqual(helper.load("lab")["device_id"], "test-id")
        backups = list(config.parent.glob("config.before-uu-ssh.*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), original)
        self.assertEqual(config.stat().st_mode & 0o777, 0o600)

    def test_openssh_parses_alias_and_preserves_original_global_scope(self):
        config = self.home / ".ssh/config"
        config.write_text("ServerAliveInterval 17\nHost original\n    HostName example.invalid\n")
        self.add_peer()
        # OpenSSH expands ~ from passwd, not HOME; substitute only the test
        # include path before asking the real parser to validate semantics.
        expanded = self.home / "test-ssh-config"
        expanded.write_text(config.read_text().replace("~/.ssh", str(self.home / ".ssh")))
        def effective(host):
            result = subprocess.run(["ssh", "-F", str(expanded), "-G", host],
                                    text=True, capture_output=True, check=True)
            return dict(line.split(None, 1) for line in result.stdout.splitlines())
        peer = effective("uu-lab")
        self.assertEqual(peer["hostname"], "127.0.0.1")
        self.assertEqual(peer["port"], "22709")
        self.assertEqual(peer["user"], "alice")
        self.assertEqual(peer["hostkeyalias"], "uu-lab")
        self.assertEqual(peer["forwardagent"], "no")
        self.assertEqual(effective("original")["hostname"], "example.invalid")
        self.assertEqual(effective("unrelated")["serveraliveinterval"], "17")

    def test_refuses_unrelated_alias_and_unmanaged_fragment(self):
        with self.assertRaisesRegex(ValueError, "unrelated"):
            self.add_peer("hostname someone-else.invalid\n")
        target = self.home / ".ssh/uu-bridge/lab.conf"
        target.parent.mkdir()
        target.write_text("Host unrelated\n")
        with self.assertRaisesRegex(ValueError, "unmanaged"):
            self.add_peer()
        self.assertEqual(target.read_text(), "Host unrelated\n")

    def test_rejects_symlinks_and_invalid_names(self):
        target = self.home / "target"
        target.write_text("keep")
        link = self.home / "link"
        link.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "symlink"):
            helper.write_private(link, "replace")
        self.assertEqual(target.read_text(), "keep")
        for invalid in ("../lab", "-oProxyCommand=bad", "lab\nHost evil", "lab/home"):
            with self.assertRaises(argparse.ArgumentTypeError):
                helper.name(invalid)
        for invalid in ("22", "0", "65536"):
            with self.assertRaises(argparse.ArgumentTypeError):
                helper.port(invalid)

    def test_closed_mapping_reports_action_without_starting_services(self):
        self.add_peer()
        with mock.patch.object(helper.socket, "create_connection", side_effect=ConnectionRefusedError()):
            with mock.patch.object(helper.subprocess, "run") as run, mock.patch.object(helper.os, "execv") as execute:
                with self.assertRaisesRegex(ValueError, "Port mapping") as raised:
                    helper.check("lab")
                message = str(raised.exception)
                self.assertIn("timeout 15 uu-ssh terminal lab --list-sessions", message)
                self.assertIn("check controller ownership", message)
                self.assertIn("does not create one or guarantee recovery", message)
                run.assert_not_called()
                execute.assert_not_called()

    def test_closed_mapping_without_device_id_does_not_offer_terminal_query(self):
        self.args.device_id = None
        self.add_peer()
        with mock.patch.object(helper.socket, "create_connection", side_effect=ConnectionRefusedError()):
            with self.assertRaises(ValueError) as raised:
                helper.check("lab")
        self.assertNotIn("--list-sessions", str(raised.exception))

    def test_non_ssh_listener_does_not_offer_mapping_initialization(self):
        self.add_peer()
        connection = mock.MagicMock()
        connection.__enter__.return_value.recv.return_value = b"HTTP/1.1 200 OK\r\n"
        with mock.patch.object(helper.socket, "create_connection", return_value=connection):
            with mock.patch.object(helper.subprocess, "run") as run:
                with self.assertRaisesRegex(ValueError, "SSH banner") as raised:
                    helper.check("lab")
                self.assertNotIn("--list-sessions", str(raised.exception))
                run.assert_not_called()

    def test_successful_check_uses_noninteractive_native_ssh(self):
        self.add_peer()
        connection = mock.MagicMock()
        connection.__enter__.return_value.recv.return_value = b"SSH-2.0-OpenSSH\r\n"
        with mock.patch.object(helper.socket, "create_connection", return_value=connection):
            with mock.patch.object(helper.subprocess, "run", return_value=argparse.Namespace(returncode=0)) as run:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(helper.check("lab"), 0)
                self.assertEqual(run.call_args.args[0][:4], ["ssh", "-o", "BatchMode=yes", "uu-lab"])


if __name__ == "__main__":
    unittest.main()
