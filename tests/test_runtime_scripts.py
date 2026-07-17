import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]


class RuntimeScriptTests(unittest.TestCase):
    def test_all_shell_entrypoints_parse(self):
        scripts = [REPOSITORY / "install.sh", REPOSITORY / "uninstall.sh"]
        scripts.extend(sorted((REPOSITORY / "scripts").glob("*.sh")))
        scripts.extend(
            path
            for path in sorted((REPOSITORY / "scripts").iterdir())
            if path.is_file() and path.read_bytes().startswith(b"#!/usr/bin/env bash")
        )
        unique_scripts = sorted(set(scripts))
        subprocess.run(
            ["bash", "-n", *(str(path) for path in unique_scripts)],
            check=True,
            cwd=REPOSITORY,
        )

    def test_xrdp_private_bus_relay_is_supervised(self):
        launcher = (REPOSITORY / "scripts" / "uu-remote-bridge").read_text()
        self.assertIn("DBUS_SESSION_BUS_ADDRESS=$desktop_bus", launcher)
        self.assertIn("gnome-remote-desktop-daemon --rdp-port", launcher)
        self.assertIn('"$grd_pid"', launcher)
        self.assertIn("/usr/bin/openssl version -m", launcher)
        self.assertIn('"OPENSSL_MODULES=$native_openssl_modules"', launcher)
        self.assertIn("grd_user_service_was_active", launcher)

    def test_physical_session_uses_manager_display_fallback(self):
        launcher = (REPOSITORY / "scripts" / "uu-remote-bridge").read_text()

        self.assertIn('manager_wayland="${WAYLAND_DISPLAY:-}"', launcher)
        self.assertIn('"$candidate_bus" == "$manager_bus"', launcher)
        self.assertIn(
            'candidate_display="${candidate_display:-$manager_display}"',
            launcher,
        )

    def test_runtime_settings_are_persistent_and_collision_safe(self):
        installer = (REPOSITORY / "install.sh").read_text()
        launcher = (REPOSITORY / "scripts" / "uu-remote-bridge").read_text()
        verifier = (REPOSITORY / "scripts" / "verify.sh").read_text()
        unit = (REPOSITORY / "systemd" / "uu-remote-bridge.service").read_text()

        self.assertIn("--rdp-port", installer)
        self.assertIn("--resolution", installer)
        self.assertIn("--display", installer)
        self.assertIn("UURB_RDP_PORT=%s", installer)
        self.assertIn("UURB_RESOLUTION=%s", installer)
        self.assertIn("UURB_DISPLAY=%s", installer)
        self.assertIn("UURB_GRD_FD_RESTART_THRESHOLD=%s", installer)
        self.assertIn("EnvironmentFile=-%h/.config/uu-remote-bridge/environment", unit)
        self.assertIn('bridge_display="${UURB_DISPLAY:-auto}"', launcher)
        self.assertIn(
            'grd_fd_restart_threshold="${UURB_GRD_FD_RESTART_THRESHOLD:-4096}"',
            launcher,
        )
        self.assertIn("/tmp/.X11-unix/X$display_number", launcher)
        self.assertIn("saved_setting UURB_RDP_PORT", verifier)
        self.assertIn("restore_bridge_after_failure", installer)
        self.assertLess(
            installer.index('port_listener="$('),
            installer.index('stop uu-remote-bridge.service'),
        )

    def test_missing_or_uninjectable_uu_server_restarts_bridge(self):
        launcher = (REPOSITORY / "scripts" / "uu-remote-bridge").read_text()

        self.assertIn("missing_checks >= 40", launcher)
        self.assertIn("UU server was absent for 10 seconds", launcher)
        self.assertIn("Could not re-inject UU server process", launcher)

    def test_wine_cleanup_is_prefix_scoped(self):
        helper = REPOSITORY / "scripts" / "stop-wine-prefix"
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            wine_probe = temporary_path / "wine-probe"
            shutil.copy2("/bin/sleep", wine_probe)
            wine_probe.chmod(0o755)
            target_prefix = str(temporary_path / "target-prefix")
            other_prefix = str(temporary_path / "other-prefix")
            target_environment = os.environ | {"WINEPREFIX": target_prefix}
            other_environment = os.environ | {"WINEPREFIX": other_prefix}
            target = subprocess.Popen(
                [str(wine_probe), "60"], env=target_environment
            )
            unrelated = subprocess.Popen(
                [str(wine_probe), "60"], env=other_environment
            )
            try:
                subprocess.run(
                    [str(helper), target_prefix, "/nonexistent/wineserver"],
                    check=True,
                    cwd=REPOSITORY,
                )
                target.wait(timeout=3)
                self.assertIsNone(unrelated.poll())
            finally:
                for process in (target, unrelated):
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=3)

    def test_service_cleanup_has_no_unbounded_child_wait(self):
        launcher = (REPOSITORY / "scripts" / "uu-remote-bridge").read_text()

        self.assertIn("processes_alive=false", launcher)
        self.assertIn('kill -KILL "$pid"', launcher)
        self.assertNotIn('wait "$pid"', launcher)
        self.assertIn('"$lock_pid" == "$xvfb_pid"', launcher)
        self.assertIn('[[ -r "$display_lock" ]]', launcher)
        self.assertIn('rm -f "$display_lock" "$display_socket"', launcher)

    def test_gnome_rdp_descriptor_exhaustion_is_bounded(self):
        installer = (REPOSITORY / "install.sh").read_text()
        launcher = (REPOSITORY / "scripts" / "uu-remote-bridge").read_text()
        libei_builder = (REPOSITORY / "scripts" / "build-libei.sh").read_text()
        libei_patch = (
            REPOSITORY / "patches" / "libei-1.2.1-close-keymap-fd.patch"
        ).read_text()
        unit = (REPOSITORY / "systemd" / "uu-remote-bridge.service").read_text()
        verifier = (REPOSITORY / "scripts" / "verify.sh").read_text()

        self.assertIn("scripts/build-libei.sh", installer)
        self.assertIn("7e06f06aa4dd1f7d", libei_builder)
        self.assertIn("xclose (keymap_fd)", libei_patch)
        self.assertIn('"LD_LIBRARY_PATH=$libei_dir"', launcher)
        self.assertIn("--grd-fd-restart-threshold", installer)
        self.assertIn("grd_fd_restart_threshold > 0", launcher)
        self.assertIn("restarting the relay before exhaustion", launcher)
        self.assertIn("LimitNOFILE=65536", unit)
        self.assertIn("GNOME RDP descriptor limit", verifier)
        self.assertIn("descriptor growth stayed bounded", verifier)

    def test_installed_runtime_drift_is_detected(self):
        installer = (REPOSITORY / "install.sh").read_text()
        verifier = (REPOSITORY / "scripts" / "verify.sh").read_text()
        digest = REPOSITORY / "scripts" / "runtime-source-digest"

        self.assertTrue(digest.exists())
        self.assertIn(".runtime-source-sha256", installer)
        self.assertIn("installed runtime matches this source checkout", verifier)

    def test_verifier_cannot_confuse_xrdp_with_gnome_rdp(self):
        verifier = (REPOSITORY / "scripts" / "verify.sh").read_text()
        self.assertIn("/usr/bin/gsettings", verifier)
        self.assertIn("gnome-remote-de", verifier)
        self.assertIn("unix:path=${XDG_RUNTIME_DIR:-/run/user/$UID}/bus", verifier)
        self.assertNotIn('rdp_port="$(gsettings ', verifier)

    def test_user_service_starts_from_default_target(self):
        unit = (REPOSITORY / "systemd" / "uu-remote-bridge.service").read_text()
        self.assertIn("WantedBy=default.target", unit)
        self.assertNotIn("WantedBy=graphical-session.target", unit)

    def test_freerdp_cache_is_checksum_backed(self):
        builder = (REPOSITORY / "scripts" / "build-winpr.sh").read_text()
        self.assertIn(".build-recipe", builder)
        self.assertIn("sha256sum -c .build-sha256", builder)

    def test_clipboard_channel_is_enabled(self):
        launcher = (REPOSITORY / "scripts" / "uu-remote-bridge").read_text()

        self.assertIn("+clipboard", launcher)
        self.assertNotIn("-clipboard", launcher)

    def test_phone_ime_unicode_input_is_normalized(self):
        bridge = (REPOSITORY / "src" / "uu_input_bridge.c").read_text()
        broker = (REPOSITORY / "src" / "uu_input_broker.c").read_text()

        self.assertIn("contains_unicode_keyboard", bridge)
        self.assertIn("KEYEVENTF_UNICODE", bridge)
        self.assertIn("key_mapping_for_character", broker)
        self.assertIn("VkKeyScanW", broker)
        self.assertIn('normalized_unicode ? "normalized"', broker)


if __name__ == "__main__":
    unittest.main()
