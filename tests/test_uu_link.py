"""Private inbox tests: no real home, vendor process, SSH server or desktop."""
import concurrent.futures
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/uu-link"
loader = importlib.machinery.SourceFileLoader("uu_link", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
helper = importlib.util.module_from_spec(spec)
loader.exec_module(helper)


class UULinkTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="uu-link-test-")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        patch = mock.patch.object(helper.Path, "home", return_value=self.home)
        patch.start()
        self.addCleanup(patch.stop)
        profile = self.home / ".config/uu-ssh/peers/lab.json"
        profile.parent.mkdir(parents=True)
        profile.write_text('{}')

    def message(self, text='UU 中文 日本語 "quote" 😀\nline two\n'):
        message_id = helper.prepare("lab", text)
        return helper.load(helper.directory("outbox") / f"{message_id}.json")["message"]

    def test_utf8_multiline_and_duplicate_delivery(self):
        message = self.message()
        wire = helper.encode(message)
        first = helper.receive(io.BytesIO(wire))
        self.assertEqual(helper.receive(io.BytesIO(wire)), first)
        path = helper.directory("inbox") / (message["id"] + ".json")
        self.assertEqual(helper.load(path), message)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(len(list(path.parent.glob("*.json"))), 1)

    def test_simultaneous_retries_store_once(self):
        wire = helper.encode(self.message())
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: helper.receive(io.BytesIO(wire)), range(16)))
        self.assertTrue(all(result == results[0] for result in results))
        self.assertEqual(len(list(helper.directory("inbox").glob("*.json"))), 1)

    def test_id_collision_never_overwrites(self):
        message = self.message()
        helper.receive(io.BytesIO(helper.encode(message)))
        message["text"] = "different"
        with self.assertRaisesRegex(ValueError, "different content"):
            helper.receive(io.BytesIO(helper.encode(message)))

    def test_rejects_invalid_ids_fields_sizes_and_surrogates(self):
        for value in ("../escape", "-x", "UPPERCASE", ""):
            with self.assertRaises(ValueError):
                helper.identifier(value)
        for text in ("", "x" * (helper.MAX_TEXT + 1), "\ud800"):
            with self.assertRaises(ValueError):
                self.message(text)
        with self.assertRaises(ValueError):
            helper.receive(io.BytesIO(b"x" * (helper.MAX_WIRE + 1)))
        message = self.message()
        message["command"] = "must never run"
        with self.assertRaises(ValueError):
            helper.receive(io.BytesIO(helper.encode(message)))

    def test_refuses_symlink_store_and_message(self):
        message = self.message()
        inbox = helper.directory("inbox")
        target = self.home / "untouched"
        target.write_text("untouched")
        (inbox / f'{message["id"]}.json').symlink_to(target)
        with self.assertRaises((ValueError, OSError)):
            helper.receive(io.BytesIO(helper.encode(message)))
        self.assertEqual(target.read_text(), "untouched")
        receipts = helper.directory("receipts")
        receipts.rmdir()
        receipts.symlink_to(self.home, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            helper.directory("receipts")

    def test_failed_ssh_keeps_outbox_for_explicit_retry(self):
        message = self.message()
        with mock.patch.object(helper.subprocess, "run", side_effect=subprocess.TimeoutExpired("ssh", 20)) as run:
            with self.assertRaises(subprocess.TimeoutExpired):
                helper.deliver(message["id"])
            self.assertEqual(run.call_count, 1)
        self.assertFalse(helper.list_entries("outbox", 1)[0]["receipt_present"])

    def test_fixed_command_and_confirmed_retry_has_no_second_ssh(self):
        message = self.message('$(touch BAD)\n; exit\n你好')
        def remote(command, **kwargs):
            self.assertEqual(command[-1], helper.REMOTE_RECEIVER)
            self.assertEqual(command[-2], "uu-lab")
            self.assertIn("StrictHostKeyChecking=yes", command)
            self.assertIn("BatchMode=yes", command)
            self.assertIn("ClearAllForwardings=yes", command)
            self.assertEqual(kwargs["timeout"], 20)
            return subprocess.CompletedProcess(command, 0,
                helper.encode(helper.receive(io.BytesIO(kwargs["input"]))), b"")
        with mock.patch.object(helper.subprocess, "run", side_effect=remote) as run:
            first = helper.deliver(message["id"])
            self.assertEqual(helper.deliver(message["id"]), first)
            self.assertEqual(run.call_count, 1)

    def test_wrong_receipt_does_not_mark_delivered(self):
        message = self.message()
        result = subprocess.CompletedProcess([], 0, b'{"stored": true}', b"")
        with mock.patch.object(helper.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(ValueError, "confirm"):
                helper.deliver(message["id"])
        self.assertFalse(helper.list_entries("outbox", 1)[0]["receipt_present"])

    def test_no_implicit_execution_and_terminal_escapes_are_encoded(self):
        message = self.message("\x1b]52;c;SECRET\x07\nrm --never-run")
        ack = helper.receive(io.BytesIO(helper.encode(message)))
        self.assertTrue(ack["stored"])
        self.assertNotIn(b"\x1b", helper.encode(message))
        self.assertIn(b"\\u001b", helper.encode(message))
        self.assertNotIn("text", helper.list_entries("inbox", 1)[0])

    def test_installer_lifecycle_includes_helper(self):
        root = SCRIPT.parents[1]
        for relative in ("install.sh", "uninstall.sh", "scripts/upgrade-uu-remote.sh", "scripts/runtime-source-digest"):
            self.assertIn("uu-link", (root / relative).read_text())


if __name__ == "__main__":
    unittest.main()
