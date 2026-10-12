"""The windowed UU viewer must not export or forward input outside UU windows.

Outside the UU windows the private display shows the live desktop relay, which
forwards the mouse to the real desktop. The geometry tests run the pure
function; the others run the real `open_window` of scripts/uu-remote-console
against a private Xvfb with solid-colour fixture windows (a red "relay" under
the UU windows that logs every pointer event), a real x11vnc and a minimal RFB
client. Nothing touches a real desktop, a UU session or the bridge service: the
bridge lookup, the focus helper and the viewer are replaced.
"""

import importlib.util
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONSOLE = ROOT / "scripts" / "uu-remote-console"
PROBES = ROOT / "tests" / "probes"
FIXTURE = PROBES / "window_region_fixture.py"
DEFINITIONS = CONSOLE.read_text().split('case "${1:-open}" in', 1)[0]

RED, GREEN, BLUE = (255, 0, 0), (0, 255, 0), (0, 0, 255)
CURSOR = {(0, 0, 0), (255, 255, 255)}  # x11vnc paints the mouse cursor

spec = importlib.util.spec_from_file_location("rfb", PROBES / "rfb_framebuffer_client.py")
rfb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rfb)


def geometry(x, y, width, height):
    return "WINDOW=1\nX=%d\nY=%d\nWIDTH=%d\nHEIGHT=%d\nSCREEN=0\n" % (x, y, width, height)


class CoveredRegionTests(unittest.TestCase):
    def region(self, *windows, clip="", awk="/usr/bin/awk"):
        script = (
            'source <(sed -n "/^covered_region() {/,/^}/p" "$1" | sed "s|/usr/bin/awk|$2|"); '
            'shift 2; covered_region "$@"'
        )
        result = subprocess.run(
            ["bash", "-c", script, "bash", str(CONSOLE), awk, "1920", "1080", clip],
            input="".join(windows), text=True, capture_output=True, check=True,
        )
        return result.stdout.strip()

    def test_l_shaped_overlap_does_not_include_the_hole(self):
        # The reviewed case: a 900x600 main window and a 500x400 popup at
        # +850+500. Their bounding box 1350x900 contains (1200,100), which no
        # UU window covers.
        main, popup = geometry(0, 0, 900, 600), geometry(850, 500, 500, 400)
        for awk in ("/usr/bin/gawk", "/usr/bin/mawk"):
            if os.access(awk, os.X_OK):
                with self.subTest(awk=awk):
                    self.assertEqual("900x600+0+0", self.region(main, popup, awk=awk))

    def test_the_largest_fully_covered_rectangle_wins(self):
        main = geometry(500, 200, 920, 680)
        # A popup inside the main window and a distant toast change nothing.
        self.assertEqual("920x680+500+200", self.region(
            main, geometry(600, 300, 300, 200), geometry(1560, 900, 300, 120)))
        # Windows that tile a rectangle are exported whole.
        self.assertEqual("800x400+100+100", self.region(
            geometry(100, 100, 500, 400), geometry(600, 100, 300, 400)))
        # A larger remote-control window wins; regions are clamped to the screen.
        self.assertEqual("1700x950+100+50", self.region(main, geometry(100, 50, 1700, 950)))
        self.assertEqual("250x180+0+0", self.region(geometry(-50, -20, 300, 200)))
        self.assertEqual("", self.region(geometry(0, 0, 30, 30)))

    def test_the_exported_region_is_stale_when_not_fully_covered(self):
        main, popup = geometry(0, 0, 900, 600), geometry(850, 500, 500, 400)
        self.assertEqual("900x600+0+0 covered", self.region(main, popup, clip="900x600+0+0"))
        self.assertEqual("900x600+0+0 stale", self.region(main, popup, clip="1350x900+0+0"))
        self.assertEqual("500x400+0+0 stale", self.region(geometry(0, 0, 500, 400), clip="900x600+0+0"))


class SettingTest(unittest.TestCase):
    def test_the_region_mode_is_off_unless_asked_for(self):
        def setting(environment, saved=None):
            with tempfile.TemporaryDirectory() as home:
                if saved:
                    config = Path(home, ".config", "uu-remote-bridge")
                    config.mkdir(parents=True)
                    (config / "environment").write_text(saved)
                env = {k: v for k, v in os.environ.items() if not k.startswith("UURB_")}
                env.update(environment, HOME=home, XDG_RUNTIME_DIR=home, XDG_STATE_HOME=home)
                return subprocess.run(
                    ["bash", "-c", DEFINITIONS + '\nprintf "%s" "$experimental_window_region"'],
                    env=env, capture_output=True, text=True, check=True,
                ).stdout

        self.assertEqual("0", setting({}))
        self.assertEqual("1", setting({"UURB_EXPERIMENTAL_WINDOW_REGION": "1"}))
        self.assertEqual("1", setting({}, "UURB_EXPERIMENTAL_WINDOW_REGION=1\n"))


def tools_missing():
    missing = [p for p in ("flock", "ss", "x11vnc", "xdotool", "xdpyinfo") if not os.access("/usr/bin/" + p, os.X_OK)]
    missing += [name for name in ("Xvfb",) if not shutil.which(name)]
    if not missing:
        probe = subprocess.run(
            [sys.executable, "-c", "import gi; gi.require_version('Gtk', '3.0'); from gi.repository import Gtk"],
            capture_output=True,
        )
        if probe.returncode:
            missing.append("python3-gi")
    return missing


# Stands in for /usr/bin/vncviewer: records its arguments, optionally opens a
# window like the real viewer on the local display, and exits once the x11vnc
# server it was pointed at stops listening, as the real viewer does.
VIEWER_STUB = """#!/bin/bash
printf '%s\\n' "$*" >>"$VIEWER_ARGS"
port="${@: -1}"
port="${port##*:}"
[[ -n "${VIEWER_WINDOW:-}" ]] && FX_TITLE='UU Remote - TigerVNC' python3 "$FIXTURE" viewer 0 0 1200 800 202020 'TigerVNC Viewer' >/dev/null 2>&1 &
while /usr/bin/ss -H -ltn "sport = :$port" | grep -q .; do sleep 0.2; done
"""


@unittest.skipIf(tools_missing(), "needs Xvfb, x11vnc, xdotool, ss, flock and python3-gi")
class WindowRegionIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = Path(tempfile.mkdtemp(prefix="uu-region-test-"))
        cls.local = cls.start_xvfb("1920x1080x24")
        cls.private = cls.start_xvfb("1600x900x24")

    @classmethod
    def tearDownClass(cls):
        for process, _ in (cls.local, cls.private):
            process.terminate()
            process.wait(10)
        shutil.rmtree(cls.directory, ignore_errors=True)

    @staticmethod
    def start_xvfb(screen):
        read_end, write_end = os.pipe()
        process = subprocess.Popen(
            ["Xvfb", "-displayfd", str(write_end), "-screen", "0", screen, "-nolisten", "tcp"],
            pass_fds=(write_end,), stderr=subprocess.DEVNULL,
        )
        os.close(write_end)
        number = b""
        while not number.endswith(b"\n"):
            number += os.read(read_end, 16)
        os.close(read_end)
        return process, ":" + number.decode().strip()

    def setUp(self):
        self.work = Path(tempfile.mkdtemp(dir=self.directory))
        self.log, self.calls, self.viewer_args = (self.work / n for n in ("events.log", "calls.log", "viewer-args"))
        self.log.touch()
        self.calls.touch()
        self.children, self.clients, self.ids, self.harness = [], [], {}, None
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for client in self.clients:
            client.close()
        if self.harness is not None:
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(self.harness.pid, sig)
                    self.harness.wait(5)
                    break
                except ProcessLookupError:
                    break
                except subprocess.TimeoutExpired:
                    continue
        for process in self.children:
            process.terminate()
            process.wait(10)

    def environment(self, display, **extra):
        env = dict(os.environ, DISPLAY=display, FX_LOG=str(self.log), GDK_BACKEND="x11", **extra)
        env.pop("WAYLAND_DISPLAY", None)
        return env

    def start_windows(self, *windows):
        """Start the red relay, then the UU windows (tag, x, y, w, h, colour)."""
        for tag, x, y, width, height, color in (("relay", 0, 0, 1600, 900, "ff0000"),) + windows:
            process = subprocess.Popen(
                [sys.executable, str(FIXTURE), tag, str(x), str(y), str(width), str(height), color,
                 "relay" if tag == "relay" else "gameviewer.exe"],
                env=self.environment(self.private[1]), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            )
            self.children.append(process)
            ready = process.stdout.readline().split()  # "ready XID"; stacked in mapping order
            self.assertEqual("ready", ready[0] if ready else "")
            self.ids[tag] = ready[1]

    def xdotool(self, *arguments):
        subprocess.run(["xdotool", *arguments], env=self.environment(self.private[1]), check=True)

    def open_window(self, experimental=True, viewer_window=False):
        """Run the real open_window; return an RFB client of its x11vnc."""
        stub = self.work / "vncviewer"
        stub.write_text(VIEWER_STUB)
        stub.chmod(0o700)
        xauthority = self.work / "Xauthority"
        xauthority.touch()
        script = DEFINITIONS.replace("/usr/bin/vncviewer", str(stub)) + f"""
ensure_bridge() {{ bridge_display={self.private[1]}; bridge_xauthority={xauthority}; }}
discover_bridge() {{ ensure_bridge; }}
find_client_window() {{ printf '%s\\n' {self.ids['main']}; }}
focus_client() {{ printf 'focus\\n' >>{self.calls}; }}
release_client() {{ :; }}
notify_error() {{ printf 'notify: %s\\n' "$1" >>{self.calls}; }}
open_window
"""
        (self.work / "harness.sh").write_text(script)
        extra = {"HOME": str(self.work), "XDG_RUNTIME_DIR": str(self.work / "run"), "XDG_STATE_HOME": str(self.work / "state"),
                 "VIEWER_ARGS": str(self.viewer_args), "FIXTURE": str(FIXTURE)}
        if experimental:
            extra["UURB_EXPERIMENTAL_WINDOW_REGION"] = "1"
        if viewer_window:
            extra["VIEWER_WINDOW"] = "1"
        self.harness = subprocess.Popen(
            ["bash", str(self.work / "harness.sh")], env=self.environment(self.local[1], **extra),
            start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        self.port_file = self.work / "run" / "uu-remote-console" / "window.port"
        return self.connect()

    def connect(self):
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                port = int(self.port_file.read_text().strip())
                self.clients.append(rfb.RFBClient(port))
                return self.clients[-1]
            except (OSError, ValueError, EOFError, ConnectionError):
                time.sleep(0.1)
        self.fail("could not connect to the window server: " + self.calls.read_text())

    def x11vnc_arguments(self):
        group = os.getpgid(self.harness.pid)
        for entry in filter(str.isdigit, os.listdir("/proc")):
            try:
                if os.getpgid(int(entry)) == group:
                    arguments = Path(f"/proc/{entry}/cmdline").read_bytes().split(b"\0")
                    if arguments[0].endswith(b"x11vnc"):
                        return [a.decode() for a in arguments[1:] if a]
            except OSError:
                continue
        return []

    def wait_until(self, condition, timeout=8.0):
        deadline = time.time() + timeout
        while time.time() < deadline and not condition():
            time.sleep(0.1)
        return condition()

    def events(self, tag=""):
        return [line for line in self.log.read_text().splitlines() if line.startswith(tag)]

    def click(self, client, x, y):
        client.click(x, y)
        time.sleep(0.8)  # x11vnc hands pointer events to the X server late

    def test_l_shaped_overlap_hides_the_hole_and_the_relay_gets_no_input(self):
        # The reviewed L: main 900x600 at +100+100 and a popup 500x300 at
        # +950+500. The bounding box 1350x700 holds a red hole at (1200,200).
        self.start_windows(("main", 100, 100, 900, 600, "00ff00"), ("popup", 950, 500, 500, 300, "0000ff"))
        client = self.open_window()
        self.assertEqual((900, 600), (client.width, client.height))
        for x, y in ((0, 0), (899, 0), (0, 599), (450, 300)):
            self.click(client, x, y)
        self.assertEqual([], self.events("relay"))
        self.assertTrue(self.events("main press"))
        colors = set(client.frame()) - CURSOR  # read the frame last: it slows pointer input
        self.assertEqual({GREEN, BLUE}, colors, "only UU windows may be exported, never the relay")
        arguments = self.x11vnc_arguments()
        self.assertEqual("900x600+100+100", arguments[arguments.index("-clip") + 1])
        self.assertIn("-Maximize=1", self.viewer_args.read_text())

    def test_a_moved_window_restarts_on_the_new_region_and_clicks_land_in_it(self):
        # x11vnc keeps mapping the pointer to the old origin when -clip is
        # changed in place, so the server is restarted instead.
        self.start_windows(("main", 100, 100, 900, 600, "00ff00"))
        self.open_window()
        self.xdotool("windowmove", self.ids["main"], "300", "200")
        self.assertTrue(self.wait_until(lambda: "900x600+300+200" in self.x11vnc_arguments()))
        client = self.connect()
        self.click(client, 10, 10)  # not (0,0): a new connection's pointer already is there
        self.assertIn("main press 310 210", self.events())
        self.assertEqual([], self.events("relay"))

    def test_with_no_uu_window_the_server_stops_at_once(self):
        self.start_windows(("main", 100, 100, 900, 600, "00ff00"))
        client = self.open_window()
        self.xdotool("windowunmap", self.ids["main"])
        self.assertTrue(self.wait_until(lambda: not self.x11vnc_arguments(), timeout=3))
        with self.assertRaises(OSError):
            client.click(450, 300)
            client.click(450, 300)
        self.assertEqual([], self.events("relay"))
        # UU is asked to show its window again, then the viewer gives up.
        self.assertTrue(self.wait_until(lambda: self.harness.poll() is not None, timeout=10))
        self.assertIn("not visible", self.calls.read_text())
        self.assertGreaterEqual(self.calls.read_text().count("focus"), 2)

    def test_the_default_still_shows_the_main_window_only(self):
        self.start_windows(("main", 100, 100, 900, 600, "00ff00"), ("popup", 950, 500, 500, 300, "0000ff"))
        client = self.open_window(experimental=False)
        self.assertEqual((900, 600), (client.width, client.height))
        arguments = self.x11vnc_arguments()
        self.assertEqual(self.ids["main"], arguments[arguments.index("-id") + 1])
        self.assertNotIn("-clip", arguments)
        self.assertNotIn("-Maximize", self.viewer_args.read_text())

    def test_the_viewer_window_gets_its_own_class(self):
        self.start_windows(("main", 100, 100, 900, 600, "00ff00"))
        self.open_window(viewer_window=True)

        def classes(pattern):
            return subprocess.run(["xdotool", "search", "--class", pattern], env=self.environment(self.local[1]),
                                  capture_output=True, text=True).stdout.split()

        self.assertTrue(self.wait_until(lambda: classes("^UU-Remote$")))
        self.assertEqual([], classes("^TigerVNC Viewer$"))


if __name__ == "__main__":
    unittest.main()
