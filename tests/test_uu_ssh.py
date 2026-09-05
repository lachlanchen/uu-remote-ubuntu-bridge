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
        self.args = argparse.Namespace(
            peer="lab", port=22709, user="alice", device_id="test-id",
            via_ssh_host=None, direct=False, shell_transport=None,
            mapping_target=None,
        )

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
        self.assertEqual(peer["stricthostkeychecking"], "true")
        self.assertEqual(peer["preferredauthentications"], "publickey")
        self.assertEqual(peer["passwordauthentication"], "no")
        self.assertEqual(peer["kbdinteractiveauthentication"], "no")
        self.assertEqual(peer["numberofpasswordprompts"], "0")
        self.assertEqual(peer["forwardagent"], "no")
        self.assertEqual(peer["controlmaster"], "false")
        self.assertEqual(peer["connectionattempts"], "1")
        self.assertIn("    ControlPath none\n",
                      (self.home / ".ssh/uu-bridge/lab.conf").read_text())
        self.assertEqual(effective("original")["hostname"], "example.invalid")
        self.assertEqual(effective("unrelated")["serveraliveinterval"], "17")

    def test_jump_host_route_is_explicit_parseable_and_removable(self):
        self.args.via_ssh_host = "glassagent-mac"
        self.args.shell_transport = "ssh"
        self.add_peer()
        profile = helper.load("lab")
        self.assertEqual(profile["via_ssh_host"], "glassagent-mac")
        self.assertEqual(profile["shell_transport"], "ssh")
        self.assertEqual(profile["mapping_target"], "127.0.0.1")
        fragment = (self.home / ".ssh/uu-bridge/lab.conf").read_text()
        self.assertIn("    ProxyJump glassagent-mac\n", fragment)

        self.args.via_ssh_host = None
        self.args.direct = True
        self.add_peer()
        profile = helper.load("lab")
        self.assertEqual(profile["via_ssh_host"], "")
        self.assertEqual(profile["shell_transport"], "ssh")
        self.assertNotIn("ProxyJump", (self.home / ".ssh/uu-bridge/lab.conf").read_text())

    def test_remote_lan_mapping_target_is_validated_and_preserved(self):
        self.args.mapping_target = "192.168.1.99"
        self.add_peer()
        self.assertEqual(helper.load("lab")["mapping_target"], "192.168.1.99")
        self.args.mapping_target = None
        self.args.port = 22023
        self.add_peer()
        self.assertEqual(helper.load("lab")["mapping_target"], "192.168.1.99")

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
        for invalid in ("-oProxyCommand=bad", "host name", "../host", "host\nProxyJump evil"):
            with self.assertRaises(argparse.ArgumentTypeError):
                helper.ssh_host(invalid)
        for valid in ("127.0.0.1", "192.168.1.99", "::1", "server.example", "host.local."):
            self.assertEqual(helper.mapping_target(valid), valid)
        for invalid in ("", "-bad.example", "bad-.example", "host name", "host/path",
                        "host\nProxyJump evil"):
            with self.assertRaises(argparse.ArgumentTypeError):
                helper.mapping_target(invalid)

    def test_closed_mapping_reports_action_without_starting_services(self):
        self.add_peer()
        with mock.patch.object(helper.socket, "create_connection", side_effect=ConnectionRefusedError()):
            with mock.patch.object(helper.subprocess, "run") as run, mock.patch.object(helper.os, "execv") as execute:
                with self.assertRaisesRegex(ValueError, "Port mapping") as raised:
                    helper.check("lab")
                message = str(raised.exception)
                self.assertNotIn("--list-sessions", message)
                self.assertIn("cancel any takeover prompt", message)
                self.assertIn("never opens a UU controller", message)
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
                command = run.call_args.args[0]
                self.assertEqual(command[:3], ["ssh", "-o", "BatchMode=yes"])
                self.assertIn("StrictHostKeyChecking=yes", command)
                self.assertIn("PreferredAuthentications=publickey", command)
                self.assertIn("ForwardAgent=no", command)
                self.assertIn("ClearAllForwardings=yes", command)
                self.assertIn("ConnectionAttempts=1", command)
                self.assertIn("NumberOfPasswordPrompts=0", command)
                self.assertEqual(command[-2:], ["uu-lab", "hostname; id -un; uname -s"])
                self.assertEqual(run.call_args.kwargs["timeout"], 15)

    def test_jump_host_check_skips_local_socket_probe(self):
        self.args.via_ssh_host = "glassagent-mac"
        self.args.shell_transport = "ssh"
        self.add_peer()
        with mock.patch.object(helper.socket, "create_connection") as connect:
            with mock.patch.object(helper.subprocess, "run", return_value=argparse.Namespace(returncode=0)) as run:
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(helper.check("lab"), 0)
                connect.assert_not_called()
                self.assertIn("through jump host glassagent-mac", output.getvalue())
                self.assertEqual(run.call_args.args[0][-2], "uu-lab")

    def test_shell_dispatches_only_the_configured_transport(self):
        literal = ["printf '%s'", "a b", "中文"]
        with mock.patch.object(helper, "load", return_value={
                "device_id": "test-id", "shell_transport": "ssh"}):
            with mock.patch.object(helper.os, "execvp") as execute:
                with mock.patch.object(helper, "terminal") as terminal:
                    helper.shell("lab", literal)
                    execute.assert_called_once_with("ssh", ["ssh", "uu-lab", *literal])
                    terminal.assert_not_called()

    def test_terminal_shell_requests_fresh_session_unless_action_is_explicit(self):
        cases = (
            ((), ["--new-session"]),
            (("--session-id", "42"), ["--session-id", "42"]),
            (("--session-id=42",), ["--session-id=42"]),
            (("--list-sessions",), ["--list-sessions"]),
            (("--new-session",), ["--new-session"]),
            (("--kill-session", "42"), ["--kill-session", "42"]),
        )
        for options, expected in cases:
            with self.subTest(options=options):
                with mock.patch.object(helper, "load", return_value={
                        "device_id": "test-id", "shell_transport": "terminal"}):
                    with mock.patch.object(helper.shutil, "which", return_value="/bin/uu-agent"):
                        with mock.patch.object(helper.os, "execv") as execute:
                            helper.shell("lab", list(options))
                            execute.assert_called_once_with(
                                "/bin/uu-agent",
                                ["/bin/uu-agent", "term", "--device-id", "test-id", *expected],
                            )

    def test_invalid_profile_transport_never_executes(self):
        with mock.patch.object(helper, "load", return_value={"shell_transport": "fallback"}):
            with mock.patch.object(helper.os, "execvp") as execute:
                with self.assertRaisesRegex(ValueError, "unsupported shell transport"):
                    helper.shell("lab", [])
                execute.assert_not_called()

    def test_ssh_timeout_reports_failure_without_uu_recovery(self):
        self.add_peer()
        connection = mock.MagicMock()
        connection.__enter__.return_value.recv.return_value = b"SSH-2.0-OpenSSH\r\n"
        with mock.patch.object(helper.socket, "create_connection", return_value=connection):
            with mock.patch.object(helper.subprocess, "run", side_effect=subprocess.TimeoutExpired("ssh", 15)) as run:
                with mock.patch.object(helper.os, "execv") as execute:
                    with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(ValueError, "timed out after 15 seconds"):
                        helper.check("lab")
                    self.assertEqual(run.call_count, 1)
                    execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
