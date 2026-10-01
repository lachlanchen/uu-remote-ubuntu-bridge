import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "release_grd_clipboard", REPO / "scripts/release-grd-clipboard.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ClipboardShutdownTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.proc = root / "proc"
        self.process = self.proc / "7"
        self.connections = root / "connections"
        for path in (self.process / "fd", self.process / "fdinfo",
                     self.proc / "self", self.connections / "41"):
            path.mkdir(parents=True)
        (self.process / "exe").symlink_to("/usr/libexec/gnome-remote-desktop-daemon")
        (self.process / "stat").write_text("7 (gnome remote) D " + "0 " * 18 + "12345\n")
        (self.process / "status").write_text("State:\tD (disk sleep)\n")
        (self.process / "wchan").write_text("request_wait_answer\n")
        for path in (self.process, self.proc / "self"):
            (path / "cgroup").write_text("0::/user.slice/uu-remote-bridge.service\n")
        (self.process / "fd/35").symlink_to("/dev/fuse")
        (self.process / "fdinfo/35").write_text("mnt_id:\t30\nfuse_connection:\t41\n")
        self.mount = (f"50 737 0:41 / /run/user/{os.getuid()}/gnome-remote-desktop/"
                      f"cliprdr-abc123 rw - fuse /dev/fuse rw,user_id={os.getuid()},group_id=1000\n")
        (self.process / "mountinfo").write_text(self.mount)
        (self.connections / "41/waiting").write_text("1\n")
        self.abort = self.connections / "41/abort"
        self.abort.write_text("")

    def release(self):
        return module.release(7, proc=self.proc, connections=self.connections)

    def test_releases_only_matching_stalled_connection(self):
        self.assertEqual(1, self.release())
        self.assertEqual("1\n", self.abort.read_text())

    def test_other_service_is_not_touched(self):
        (self.process / "cgroup").write_text("0::/another.service\n")
        self.assertEqual(0, self.release())
        self.assertEqual("", self.abort.read_text())

    def test_healthy_process_is_not_touched(self):
        (self.process / "status").write_text("State:\tS (sleeping)\n")
        self.assertEqual(0, self.release())

    def test_already_exited_process_is_safe_noop(self):
        (self.process / "stat").unlink()
        self.assertEqual(0, self.release())
        self.assertEqual("", self.abort.read_text())

    def test_wrong_wait_reason_is_not_touched(self):
        (self.process / "wchan").write_text("io_schedule\n")
        self.assertEqual(0, self.release())

    def test_unrelated_mount_is_not_touched(self):
        (self.process / "mountinfo").write_text(self.mount.replace("gnome-remote-desktop", "documents"))
        self.assertEqual(0, self.release())

    def test_connection_not_owned_by_process_is_not_touched(self):
        (self.process / "fdinfo/35").write_text("fuse_connection:\t42\n")
        self.assertEqual(0, self.release())

    def test_old_kernel_without_connection_fdinfo_is_safe_noop(self):
        (self.process / "fdinfo/35").write_text("mnt_id:\t30\n")
        self.assertEqual(0, self.release())

    def test_idle_connection_is_not_touched(self):
        (self.connections / "41/waiting").write_text("0\n")
        self.assertEqual(0, self.release())

    def test_helper_runs_after_term_grace_before_kill(self):
        source = (REPO / "scripts/uu-remote-bridge").read_text()
        cleanup = source[source.index("cleanup() {"):source.index("trap cleanup", source.index("cleanup() {"))]
        self.assertLess(cleanup.index("sleep 0.1"), cleanup.index("uu-release-grd-clipboard"))
        self.assertLess(cleanup.index("uu-release-grd-clipboard"), cleanup.index("kill -KILL"))


if __name__ == "__main__":
    unittest.main()
