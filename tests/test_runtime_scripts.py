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
        self.assertIn("UURB_TEXT_KEY_DELAY_MS=%s", installer)
        self.assertIn("UURB_PHYSICAL_KEY_DELAY_MS=%s", installer)
        self.assertIn("UURB_KEYBOARD_ROUTE=%s", installer)
        self.assertIn("UURB_NETWORK_INTERFACE=%s", installer)
        self.assertIn("resolve_text_key_delay", installer)
        self.assertIn("EnvironmentFile=-%h/.config/uu-remote-bridge/environment", unit)
        self.assertIn('bridge_display="${UURB_DISPLAY:-auto}"', launcher)
        self.assertIn(
            'grd_fd_restart_threshold="${UURB_GRD_FD_RESTART_THRESHOLD:-4096}"',
            launcher,
        )
        self.assertIn(
            'text_key_delay_ms="${UURB_TEXT_KEY_DELAY_MS:-8}"',
            launcher,
        )
        self.assertIn(
            'physical_key_delay_ms="${UURB_PHYSICAL_KEY_DELAY_MS:-0}"',
            launcher,
        )
        self.assertIn(
            'keyboard_route="${UURB_KEYBOARD_ROUTE:-rdp}"',
            launcher,
        )
        self.assertIn(
            'network_interface="${UURB_NETWORK_INTERFACE:-all}"',
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
        self.assertIn("request_relay_focus", broker)
        self.assertIn("INPUT_BRIDGE_FOCUS_TIMEOUT_MS", broker)
        self.assertIn("Sleep(text_key_delay_ms)", broker)
        self.assertIn('L"UURB_TEXT_KEY_DELAY_MS"', broker)
        self.assertIn('"x11-text"', broker)
        self.assertIn('"rdp-text-fallback"', broker)
        self.assertIn("TCP_NODELAY", broker)
        translated = broker.index("if (!translate_inputs")
        direct_x11 = broker.index("x11_result = send_x11_inputs", translated)
        relay_focus = broker.index(
            "*focus_ready = request_relay_focus", direct_x11
        )
        self.assertLess(translated, direct_x11)
        self.assertLess(direct_x11, relay_focus)
        self.assertIn("Sleep(physical_key_delay_ms)", broker)
        self.assertIn('L"UURB_PHYSICAL_KEY_DELAY_MS"', broker)
        self.assertIn('category = "keyboard"', bridge)
        self.assertIn('category = "mouse"', bridge)
        self.assertIn('category = "keyboard"', broker)
        self.assertIn('category = "mouse"', broker)
        self.assertIn("static void flush_log", bridge)
        self.assertIn("static void flush_log", broker)
        self.assertLess(
            broker.index("if (!read_all(pipe, inputs"),
            broker.index("started_ms = GetTickCount64();"),
        )
        serve_client = broker.index("static void serve_client(HANDLE pipe)")
        self.assertLess(
            broker.index("started_ms = GetTickCount64();", serve_client),
            broker.index("response.result = send_relay_inputs", serve_client),
        )

    def test_direct_x11_keyboard_route_is_opt_in_and_fail_safe(self):
        builder = (REPOSITORY / "scripts" / "build-compat.sh").read_text()
        installer = (REPOSITORY / "install.sh").read_text()
        launcher = (REPOSITORY / "scripts" / "uu-remote-bridge").read_text()
        verifier = (REPOSITORY / "scripts" / "verify.sh").read_text()
        broker = (REPOSITORY / "src" / "uu_input_broker.c").read_text()
        helper = (REPOSITORY / "src" / "uu_x11_input.c").read_text()

        self.assertIn("uu-x11-input", builder)
        self.assertIn("-lws2_32", builder)
        self.assertIn("--keyboard-route rdp|x11|auto", installer)
        self.assertIn("start_x11_input_helper", launcher)
        self.assertIn('active_keyboard_route="rdp"', launcher)
        self.assertIn("UURB_X11_INPUT_PORT", launcher)
        self.assertIn("UURB_X11_INPUT_TOKEN", launcher)
        self.assertIn("direct X11 physical-key helper is active", verifier)
        self.assertIn("send_x11_inputs", broker)
        self.assertIn('route = "x11-error"', broker)
        self.assertIn("ERROR_CONNECTION_ABORTED", broker)
        self.assertIn("release_pressed_keys", helper)
        self.assertIn("minimum_hold_ms", helper)
        self.assertNotIn("XTestFakeButtonEvent", helper)

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "uu-x11-input"
            subprocess.run(
                [
                    "gcc",
                    "-std=c11",
                    "-O2",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-I",
                    str(REPOSITORY / "src"),
                    "-o",
                    str(output),
                    str(REPOSITORY / "src" / "uu_x11_input.c"),
                    "-ldl",
                ],
                check=True,
                cwd=REPOSITORY,
            )

    def test_text_delay_migration_preserves_v010_behavior(self):
        resolver = REPOSITORY / "scripts" / "runtime-settings.sh"

        with tempfile.TemporaryDirectory() as temporary:
            environment_file = Path(temporary) / "environment"

            def resolve(saved="", explicit=None):
                environment = os.environ.copy()
                environment.pop("UURB_TEXT_KEY_DELAY_MS", None)
                if explicit is not None:
                    environment["UURB_TEXT_KEY_DELAY_MS"] = explicit
                result = subprocess.run(
                    [
                        "bash",
                        "-c",
                        'source "$1"; resolve_text_key_delay "$2" "$3"',
                        "bash",
                        str(resolver),
                        str(environment_file),
                        saved,
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    env=environment,
                )
                return result.stdout.strip()

            self.assertEqual(resolve(), "8")
            environment_file.touch()
            self.assertEqual(resolve(), "0")
            self.assertEqual(resolve(saved="6"), "6")
            self.assertEqual(resolve(saved="6", explicit="11"), "11")

    def test_routine_input_retains_proven_broker_fallback(self):
        bridge = (REPOSITORY / "src" / "uu_input_bridge.c").read_text()

        self.assertIn("if (unicode_keyboard)", bridge)
        fallback_condition = bridge.index("if (result != count) {")
        broker_call = bridge.index(
            "result = send_through_broker", fallback_condition
        )
        self.assertLess(fallback_condition, broker_call)

    def test_network_diagnosis_is_installed_and_exposed(self):
        installer = (REPOSITORY / "install.sh").read_text()
        uninstaller = (REPOSITORY / "uninstall.sh").read_text()
        command = (REPOSITORY / "scripts" / "uu-remote").read_text()

        self.assertIn("scripts/uu_connection_status.py", installer)
        self.assertIn("uu-connection-status", installer)
        self.assertIn("uu-connection-status", uninstaller)
        self.assertIn("network)", command)
        self.assertIn('exec /usr/bin/python3 "$connection_status_bin"', command)

    def test_optional_network_filter_is_scoped_and_fail_open(self):
        builder = (REPOSITORY / "scripts" / "build-compat.sh").read_text()
        installer = (REPOSITORY / "install.sh").read_text()
        launcher = (REPOSITORY / "scripts" / "uu-remote-bridge").read_text()
        network_filter = (REPOSITORY / "src" / "uu_network_filter.c").read_text()

        self.assertIn("uu-network-filter.so", builder)
        self.assertIn("--network-interface", installer)
        self.assertIn("select_network_interface", launcher)
        self.assertIn("default_network_interface", launcher)
        self.assertIn("network_route_checks >= 40", launcher)
        self.assertIn("Default network interface changed", launcher)
        self.assertIn('"${wine_host_environment[@]}" "$compat_dir/winlogon.exe"', launcher)
        self.assertNotIn("export LD_PRELOAD", launcher)
        self.assertIn("fail-open", network_filter)
        self.assertIn('strcmp(name, "lo")', network_filter)
        self.assertIn("if (!selected_found)", network_filter)
        self.assertIn("*copy = *entry", network_filter)
        self.assertNotIn("last = entry", network_filter)


if __name__ == "__main__":
    unittest.main()
