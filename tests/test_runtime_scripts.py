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

    def test_uu_agent_discovers_runtime_without_hardcoded_device_ids(self):
        helper = (REPOSITORY / "scripts" / "uu-agent").read_text()
        installer = (REPOSITORY / "install.sh").read_text()
        digest = (REPOSITORY / "scripts" / "runtime-source-digest").read_text()

        self.assertIn("GameViewerServer.exe", helper)
        self.assertIn("ControlGroup", helper)
        self.assertIn("uuyc-cli.exe", helper)
        self.assertIn("WINEPREFIX", helper)
        self.assertIn("DBUS_SESSION_BUS_ADDRESS=unix:path=", helper)
        self.assertIn('"${systemctl_user[@]}" is-active', helper)
        self.assertIn("Do not commit", helper)
        self.assertNotRegex(helper, r"aeaw[a-z0-9]{8,}")
        self.assertIn('scripts/uu-agent" "$HOME/.local/bin/uu-agent"', installer)
        self.assertIn("scripts/uu-agent", digest)

    def test_reusable_upgrader_is_installed_and_fail_closed(self):
        upgrader = (
            REPOSITORY / "scripts" / "upgrade-uu-remote.sh"
        ).read_text()
        installer = (REPOSITORY / "install.sh").read_text()
        uninstaller = (REPOSITORY / "uninstall.sh").read_text()
        command = (REPOSITORY / "scripts" / "uu-remote").read_text()
        digest = (REPOSITORY / "scripts" / "runtime-source-digest").read_text()

        self.assertIn("status --porcelain", upgrader)
        self.assertIn("merge --ff-only", upgrader)
        self.assertIn("updater_command promote-now", upgrader)
        self.assertIn("accepted product promotion ended in phase", upgrader)
        self.assertIn("--skip-account-login", upgrader)
        self.assertIn("restore_runtime_backup", upgrader)
        self.assertIn("run_live_check --allow-runtime-drift", upgrader)
        self.assertIn("uu-agent", upgrader)
        self.assertIn("uu-remote-upgrade", installer)
        self.assertIn("uu-remote-upgrade", uninstaller)
        self.assertIn("upgrade)", command)
        self.assertIn("scripts/upgrade-uu-remote.sh", digest)

        verifier = (REPOSITORY / "scripts" / "verify.sh").read_text()
        self.assertIn("--allow-runtime-drift", verifier)
        self.assertIn("installed runtime differs from pulled source", verifier)

    def test_wine_device_registry_hygiene_is_reversible_and_reusable(self):
        installer = (REPOSITORY / "install.sh").read_text()
        uninstaller = (REPOSITORY / "uninstall.sh").read_text()
        verifier = (REPOSITORY / "scripts" / "verify.sh").read_text()
        command = (REPOSITORY / "scripts" / "uu-remote").read_text()
        cleaner = (
            REPOSITORY / "scripts" / "clean-wine-device-registry"
        ).read_text()
        digest = (REPOSITORY / "scripts" / "runtime-source-digest").read_text()

        self.assertIn('devcon_backup="$devcon_exe.uu-original"', installer)
        self.assertIn("clean-wine-device-registry", installer)
        self.assertIn("system.reg.before-device-hygiene", cleaner)
        self.assertIn("--manage-service", cleaner)
        self.assertIn("restore an unknown devcon.exe backup", uninstaller)
        self.assertIn("overwrite an unknown live devcon.exe", uninstaller)
        self.assertIn("Wine device registry cannot accumulate", verifier)
        self.assertIn("repair-registry)", command)
        self.assertIn("scripts/clean-wine-device-registry", digest)
        self.assertIn("scripts/inspect-wine-device-registry.py", digest)

    def test_health_stub_comparison_ignores_only_pe_build_metadata(self):
        comparer = REPOSITORY / "scripts" / "compare-pe-normalized.py"
        builder = (REPOSITORY / "scripts" / "build-compat.sh").read_text()
        verifier = (REPOSITORY / "scripts" / "verify.sh").read_text()

        self.assertIn("--no-insert-timestamp", builder)
        self.assertIn("SOURCE_DATE_EPOCH", builder)
        self.assertIn("compare-pe-normalized.py", verifier)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = bytearray(256)
            left[:2] = b"MZ"
            left[0x3C:0x40] = (0x80).to_bytes(4, "little")
            left[0x80:0x84] = b"PE\0\0"
            left[0x98:0x9A] = (0x20B).to_bytes(2, "little")
            left[0x88:0x8C] = b"\x01\x02\x03\x04"
            left[0xD8:0xDC] = b"\x05\x06\x07\x08"
            right = bytearray(left)
            right[0x88:0x8C] = b"\x11\x12\x13\x14"
            right[0xD8:0xDC] = b"\x15\x16\x17\x18"
            left_path = root / "left.exe"
            right_path = root / "right.exe"
            left_path.write_bytes(left)
            right_path.write_bytes(right)
            subprocess.run(
                [str(comparer), str(left_path), str(right_path)],
                check=True,
            )
            right[0xE0] = 1
            right_path.write_bytes(right)
            self.assertNotEqual(
                0,
                subprocess.run(
                    [str(comparer), str(left_path), str(right_path)],
                    capture_output=True,
                ).returncode,
            )

    def test_xrdp_private_bus_relay_is_supervised(self):
        launcher = (REPOSITORY / "scripts" / "uu-remote-bridge").read_text()
        self.assertIn("DBUS_SESSION_BUS_ADDRESS=$desktop_bus", launcher)
        self.assertIn("gnome-remote-desktop-daemon --rdp-port", launcher)
        self.assertIn('"$grd_pid"', launcher)
        self.assertIn('grep -q "pid=$grd_pid,"', launcher)
        self.assertNotIn("grep -q 'gnome-remote-de'", launcher)
        self.assertIn("/usr/bin/openssl version -m", launcher)
        self.assertIn('"OPENSSL_MODULES=$native_openssl_modules"', launcher)
        self.assertIn("grd_user_service_was_active", launcher)

    def test_internal_rdp_relay_cannot_play_audio_back_to_the_host(self):
        launcher = (REPOSITORY / "scripts" / "uu-remote-bridge").read_text()

        self.assertIn("/audio-mode:2", launcher)
        self.assertNotIn("/audio-mode:0", launcher)

    def test_uu_audio_can_be_disabled_without_changing_other_wine_prefixes(self):
        launcher = (REPOSITORY / "scripts" / "uu-remote-bridge").read_text()
        silent_alsa = (REPOSITORY / "config" / "alsa-null.conf").read_text()
        upgrader = (
            REPOSITORY / "scripts" / "upgrade-uu-remote.sh"
        ).read_text()

        self.assertIn('uu_audio_setting="${UURB_UU_AUDIO:-system}"', launcher)
        self.assertIn('[[ "$uu_audio_setting" != system', launcher)
        self.assertIn("winepulse.drv=d;winedbg.exe=d", launcher)
        self.assertIn(
            "export WINEDLLOVERRIDES='winedbg.exe=d;mscoree,mshtml='",
            launcher,
        )
        self.assertIn("pcm.!default", silent_alsa)
        self.assertIn("type null", silent_alsa)
        self.assertIn("alsa-null.conf", upgrader)
        self.assertIn("uu-remote-bridge.service.d", upgrader)
        self.assertNotIn("systemctl --user restart pipewire", launcher)
        self.assertNotIn("systemctl --user restart wireplumber", launcher)

    def test_physical_session_uses_manager_display_fallback(self):
        launcher = (REPOSITORY / "scripts" / "uu-remote-bridge").read_text()

        self.assertIn('manager_wayland="${WAYLAND_DISPLAY:-}"', launcher)
        self.assertIn("refresh_manager_environment()", launcher)
        self.assertIn(
            '"${systemctl_user[@]}" show-environment',
            launcher,
        )
        self.assertLess(
            launcher.index("refresh_manager_environment\n\n    while read"),
            launcher.index('candidate_display="$(process_environment_value'),
        )
        self.assertIn('"$candidate_bus" == "$manager_bus"', launcher)
        self.assertIn(
            'candidate_display="${candidate_display:-$manager_display}"',
            launcher,
        )

    def test_desktop_target_can_pin_the_existing_xrdp_session(self):
        launcher = (REPOSITORY / "scripts" / "uu-remote-bridge").read_text()
        verifier = (REPOSITORY / "scripts" / "verify.sh").read_text()

        self.assertIn('desktop_target="${UURB_DESKTOP_TARGET:-auto}"', launcher)
        self.assertIn("--property=Service --value", launcher)
        self.assertIn('[[ "$candidate_service" == xrdp-sesman ]]', launcher)
        self.assertIn('"$candidate_bus" == "$manager_bus"', launcher)
        self.assertIn('[[ "$desktop_target" != auto ]]', launcher)
        self.assertLess(
            launcher.index('if [[ "$desktop_target" != auto ]]'),
            launcher.index('if [[ -z "$fallback_bus" ]]'),
        )
        self.assertIn(
            "Waiting for logged-in GNOME desktop target '$desktop_target'",
            launcher,
        )
        self.assertIn("expected an XRDP session", verifier)
        self.assertIn('relay_normalized_display="$(', verifier)
        self.assertIn(
            '[[ "$relay_normalized_display" == "$target_normalized_display" ]]',
            verifier,
        )

    def test_blank_nested_rdp_can_use_an_opt_in_local_vnc_relay(self):
        installer = (REPOSITORY / "install.sh").read_text()
        launcher = (REPOSITORY / "scripts" / "uu-remote-bridge").read_text()
        verifier = (REPOSITORY / "scripts" / "verify.sh").read_text()

        self.assertIn('desktop_relay="${UURB_DESKTOP_RELAY:-rdp}"', launcher)
        self.assertIn("--desktop-relay rdp|vnc", installer)
        self.assertIn("UURB_DESKTOP_RELAY=%s", installer)
        self.assertIn("--vnc-grab-keyboard off|on", installer)
        self.assertIn("UURB_VNC_GRAB_KEYBOARD=%s", installer)
        self.assertIn(
            'vnc_grab_keyboard="${UURB_VNC_GRAB_KEYBOARD:-on}"',
            launcher,
        )
        self.assertIn('[[ "$desktop_relay" == vnc ]]', launcher)
        self.assertIn("-autoport 5922", launcher)
        self.assertIn("-localhost", launcher)
        self.assertIn("-no6", launcher)
        self.assertIn("-modtweak", launcher)
        self.assertIn("-xkb", launcher)
        self.assertIn("-add_keysyms", launcher)
        self.assertIn("-seldir recv", launcher)
        self.assertIn(
            '-GrabKeyboard="$vnc_grab_keyboard_value"', launcher
        )
        self.assertIn("-ClientCutText=1", launcher)
        self.assertIn("-ServerCutText=0", launcher)
        self.assertIn("-SendPrimary=0", launcher)
        self.assertIn("-SendInitialClipboard=0", launcher)
        self.assertIn("DBUS_SESSION_BUS_ADDRESS=unix:path=/dev/null", launcher)
        self.assertIn("^127\\.0\\.0\\.1:.* - RealVNC Viewer$", launcher)
        self.assertIn("-AcceptBell=0", launcher)
        self.assertIn("-AudioVolume=0", launcher)
        self.assertIn('"$desktop_x11vnc_pid"', launcher)
        self.assertIn('"$vncviewer_pid"', launcher)
        self.assertIn("vnc_relay_ready", verifier)
        self.assertIn("localhost VNC relay owns", verifier)
        self.assertIn("candidate_relay_window_id", launcher)
        self.assertIn("RealVNC may replace its initial top-level window", launcher)
        self.assertIn("device_init: success", verifier)
        self.assertIn("auto login success", verifier)
        self.assertIn("handle response for: create room, error_code:0", verifier)

    def test_runtime_settings_are_persistent_and_collision_safe(self):
        installer = (REPOSITORY / "install.sh").read_text()
        launcher = (REPOSITORY / "scripts" / "uu-remote-bridge").read_text()
        verifier = (REPOSITORY / "scripts" / "verify.sh").read_text()
        unit = (REPOSITORY / "systemd" / "uu-remote-bridge.service").read_text()

        self.assertIn("--rdp-port", installer)
        self.assertIn("--resolution", installer)
        self.assertIn("--follow-desktop-resolution", installer)
        self.assertIn("--display", installer)
        self.assertIn("UURB_RDP_PORT=%s", installer)
        self.assertIn("UURB_RESOLUTION=%s", installer)
        self.assertIn("UURB_FOLLOW_DESKTOP_RESOLUTION=%s", installer)
        self.assertIn("UURB_DISPLAY=%s", installer)
        self.assertIn("UURB_DESKTOP_TARGET=%s", installer)
        self.assertIn("UURB_DESKTOP_RELAY=%s", installer)
        self.assertIn("UURB_GRD_FD_RESTART_THRESHOLD=%s", installer)
        self.assertIn("UURB_TEXT_KEY_DELAY_MS=%s", installer)
        self.assertIn("UURB_PHYSICAL_KEY_DELAY_MS=%s", installer)
        self.assertIn("UURB_KEYBOARD_ROUTE=%s", installer)
        self.assertIn("UURB_PHONE_TEXT_MODE=%s", installer)
        self.assertIn("UURB_NETWORK_INTERFACE=%s", installer)
        self.assertIn("UURB_CURSOR_GUARD=%s", installer)
        self.assertIn("UURB_CURSOR_SIZE=%s", installer)
        self.assertIn("resolve_text_key_delay", installer)
        self.assertIn("EnvironmentFile=-%h/.config/uu-remote-bridge/environment", unit)
        self.assertIn('bridge_display="${UURB_DISPLAY:-auto}"', launcher)
        self.assertIn(
            'desktop_target="${UURB_DESKTOP_TARGET:-auto}"',
            launcher,
        )
        self.assertIn(
            'follow_desktop_resolution="${UURB_FOLLOW_DESKTOP_RESOLUTION:-off}"',
            launcher,
        )
        self.assertIn("--desktop-target", installer)
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
            'phone_text_mode="${UURB_PHONE_TEXT_MODE:-auto}"',
            launcher,
        )
        self.assertIn(
            'network_interface="${UURB_NETWORK_INTERFACE:-all}"',
            launcher,
        )
        self.assertIn(
            'cursor_size_setting="${UURB_CURSOR_SIZE:-auto}"',
            launcher,
        )
        self.assertIn(
            'cursor_guard_setting="${UURB_CURSOR_GUARD:-off}"',
            launcher,
        )
        self.assertIn("--cursor-guard off|on", installer)
        self.assertIn("resolve_cursor_size", launcher)
        self.assertIn('export UURB_CURSOR_SIZE="$cursor_size"', launcher)
        self.assertNotIn(
            "org.gnome.desktop.interface cursor-size",
            launcher,
        )
        self.assertIn(
            'wine_prefix="${UURB_WINEPREFIX:-$HOME/.local/share/wineprefixes/uu-remote}"',
            launcher,
        )
        self.assertIn('[[ "$wine_prefix" != /* ]]', launcher)
        self.assertIn('export WINEPREFIX="$wine_prefix"', launcher)
        self.assertIn("/tmp/.X11-unix/X$display_number", launcher)
        self.assertIn("saved_setting UURB_RDP_PORT", verifier)
        self.assertIn("saved_setting UURB_DESKTOP_TARGET", verifier)
        self.assertIn("restore_bridge_after_failure", installer)
        self.assertLess(
            installer.index('port_listener="$('),
            installer.index('stop uu-remote-bridge.service'),
        )

    def test_resolution_follow_is_opt_in_stable_and_bridge_scoped(self):
        installer = (REPOSITORY / "install.sh").read_text()
        launcher = (REPOSITORY / "scripts" / "uu-remote-bridge").read_text()

        self.assertIn("--follow-desktop-resolution off|on", installer)
        self.assertIn("align_resolution_at_startup", launcher)
        self.assertIn("persist_relay_resolution", launcher)
        self.assertIn("resolution_grace_checks=240", launcher)
        self.assertIn("pending_resolution_checks >= 3", launcher)
        self.assertIn(
            '[[ "$current_desktop_resolution" == \\\n'
            '                            "$pending_resolution" ]]',
            launcher,
        )
        self.assertIn('"${systemctl_user[@]}" --no-block restart', launcher)
        self.assertIn('"$service_name"', launcher)
        self.assertNotIn("systemctl restart xrdp", launcher)

    def test_windowed_app_is_default_and_console_remains_loopback_only(self):
        console = (REPOSITORY / "scripts" / "uu-remote-console").read_text()
        command = (REPOSITORY / "scripts" / "uu-remote").read_text()
        launcher = (REPOSITORY / "scripts" / "uu-remote-bridge").read_text()
        installer = (REPOSITORY / "install.sh").read_text()
        uninstaller = (REPOSITORY / "uninstall.sh").read_text()
        unit = (
            REPOSITORY / "systemd" / "uu-remote-console.service"
        ).read_text()
        desktop = (
            REPOSITORY / "desktop" / "uu-remote.desktop.in"
        ).read_text()
        digest = (REPOSITORY / "scripts" / "runtime-source-digest").read_text()

        self.assertIn('"127.0.0.1:$web_port"', console)
        self.assertIn('"127.0.0.1:$vnc_port"', console)
        self.assertIn("-localhost", console)
        self.assertIn("-no6", console)
        self.assertIn("-nopw", console)
        self.assertIn("-u WAYLAND_DISPLAY XDG_SESSION_TYPE=x11", console)
        self.assertNotIn("0.0.0.0", console)
        self.assertIn("bridge_xauthority_file", console)
        self.assertIn("private-display", console)
        self.assertIn("uu-remote-console.service", installer)
        self.assertIn("novnc", installer)
        self.assertIn("tigervnc-viewer", installer)
        self.assertIn("websockify", installer)
        self.assertIn("x11vnc", installer)
        self.assertIn("/usr/bin/vncviewer", installer)
        self.assertIn("uu-remote-console.service", uninstaller)
        self.assertIn("ExecStart=%h/.local/bin/uu-remote-console serve", unit)
        self.assertIn("NoNewPrivileges=yes", unit)
        self.assertIn("Exec=@EXEC@", desktop)
        self.assertIn("StartupWMClass=TigerVNC Viewer", desktop)
        self.assertNotIn("noVNC", desktop)
        self.assertIn('"$desktop_entry" "$HOME/.local/bin/uu-remote"', installer)
        self.assertIn('exec "$console_bin" window "$@"', command)
        self.assertNotIn("activate_physical_client", command)
        self.assertNotIn("open-client", command)
        self.assertIn('exec "$console_bin" open "$@"', command)
        self.assertIn('-id "$client_window"', console)
        self.assertIn("/usr/bin/flock -n 9", console)
        self.assertIn("activate_existing_window", console)
        self.assertIn("cleanup_window", console)
        self.assertIn("127.0.0.1::$window_port", console)
        self.assertNotIn("desktop_client_environment", launcher)
        self.assertNotIn("open-client", launcher)
        self.assertIn("bootstrap_account", launcher)
        self.assertIn('console_focus_file="$runtime_dir/console-focus"', launcher)
        self.assertIn('[[ ! -e "$console_focus_file"', launcher)
        self.assertIn("scripts/uu-remote-console", digest)
        self.assertIn("systemd/uu-remote-console.service", digest)
        self.assertIn("desktop/uu-remote.desktop.in", digest)

        environment = os.environ | {
            "UURB_CONSOLE_VNC_PORT": "5926",
            "UURB_CONSOLE_WEB_PORT": "6086",
        }
        result = subprocess.run(
            [str(REPOSITORY / "scripts" / "uu-remote-console"), "url"],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )
        self.assertEqual(
            result.stdout.strip(),
            "http://127.0.0.1:6086/vnc.html"
            "?autoconnect=1&resize=scale&reconnect=1",
        )

    def test_macos_current_desktop_relay_is_tunneled_and_probe_tolerant(self):
        console = (REPOSITORY / "scripts" / "uu-remote-console").read_text()
        installer = (REPOSITORY / "install.sh").read_text()
        macos_launcher = (
            REPOSITORY / "scripts" / "macos-connect-7090.applescript"
        ).read_text()

        self.assertIn('relay_vnc_port="${UURB_RELAY_VNC_PORT:-5922}"', console)
        self.assertIn("find_relay_window", console)
        self.assertIn("-id \"$relay_window\"", console)
        self.assertIn("-listen 127.0.0.1", console)
        self.assertIn('-rfbauth "$relay_vnc_auth_file"', console)
        self.assertIn("-forever", console)
        self.assertIn("-shared", console)
        self.assertIn("connected_checks >= 3", console)
        self.assertIn("idle_checks >= 25", console)
        self.assertIn("prepare_relay_vnc_auth", console)
        self.assertIn("service uu-desktop-bridge", console)
        self.assertIn("username \"$USER\"", console)
        self.assertIn("/usr/bin/script -qefc", console)
        self.assertIn(
            'vnc_password="$(LC_ALL=C printf \'%.8s\' "$password")"',
            console,
        )
        self.assertIn("/usr/bin/script -qefc", installer)
        self.assertIn(
            'relay_vnc_password="$(LC_ALL=C printf \'%.8s\' '
            '"$rdp_password")"',
            installer,
        )
        self.assertIn("x11vnc -storepasswd $relay_vnc_auth_quoted", installer)
        self.assertNotIn('-storepasswd "$rdp_password"', installer)
        self.assertIn('property vncTunnelPort : 15922', macos_launcher)
        self.assertIn(
            '":127.0.0.1:" & (relayPort as text)',
            macos_launcher,
        )
        self.assertIn("/usr/bin/ssh -fn", macos_launcher)
        self.assertIn("ExitOnForwardFailure=yes", macos_launcher)
        self.assertIn(
            '~/.local/bin/uu-remote-console relay',
            macos_launcher,
        )
        self.assertIn('portIsOpen("localhost"', macos_launcher)
        self.assertIn('vnc://localhost:', macos_launcher)
        self.assertNotIn("[::1]:5900", macos_launcher)

        environment = os.environ | {"UURB_RELAY_VNC_PORT": "6022"}
        result = subprocess.run(
            [str(REPOSITORY / "scripts" / "uu-remote-console"), "relay-port"],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )
        self.assertEqual(result.stdout.strip(), "6022")

    def test_missing_or_uninjectable_uu_server_restarts_bridge(self):
        launcher = (REPOSITORY / "scripts" / "uu-remote-bridge").read_text()

        self.assertIn("missing_checks >= 40", launcher)
        self.assertIn("UU server was absent for 10 seconds", launcher)
        self.assertIn("Could not re-inject UU server process", launcher)

    def test_private_display_keeps_desktop_relay_focused(self):
        launcher = (REPOSITORY / "scripts" / "uu-remote-bridge").read_text()

        self.assertIn("relay_window_id=", launcher)
        self.assertIn("/usr/bin/xdotool getactivewindow", launcher)
        self.assertIn(
            'active_window_id" != "$relay_window_id"',
            launcher,
        )
        self.assertIn(
            '/usr/bin/xdotool windowactivate "$relay_window_id"',
            launcher,
        )
        bootstrap = launcher[
            launcher.index("bootstrap_account()") : launcher.index(
                "# UU's GUI sends the account-login IPC message"
            )
        ]
        self.assertNotIn("windowminimize", bootstrap)
        self.assertIn("terminate the GUI IPC client", bootstrap)

    def test_wine_launcher_exit_does_not_trigger_a_restart_storm(self):
        launcher = (REPOSITORY / "scripts" / "uu-remote-bridge").read_text()
        unit = (REPOSITORY / "systemd" / "uu-remote-bridge.service").read_text()
        readiness = launcher[
            launcher.index("relay_ready=false") : launcher.index(
                "bootstrap_account()"
            )
        ]

        self.assertIn("for _ in {1..300}", readiness)
        self.assertNotIn('kill -0 "$freerdp_pid"', readiness)
        self.assertIn("launcher may exit", readiness)
        self.assertIn("StartLimitIntervalSec=300", unit)
        self.assertIn("StartLimitBurst=5", unit)
        self.assertIn("RestartSec=30", unit)

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
        self.assertIn("raise_open_file_limit", launcher)
        self.assertIn("target_limit=65536", launcher)
        self.assertIn('ulimit -Sn "$target_limit"', launcher)
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

    def test_verifier_waits_for_the_real_relay_and_selected_input_route(self):
        verifier = (REPOSITORY / "scripts" / "verify.sh").read_text()

        readiness_loop = verifier.index("for _ in {1..180}; do")
        first_service_check = verifier.index(
            "bridge_service_active &&",
            readiness_loop,
        )
        first_relay_check = verifier.index(
            "relay_listener_ready",
            first_service_check,
        )
        first_x11_check = verifier.index(
            "x11_route_ready",
            first_service_check,
        )
        first_wait_end = verifier.index("done", readiness_loop)

        self.assertLess(first_service_check, first_relay_check)
        self.assertLess(first_relay_check, first_wait_end)
        self.assertLess(first_x11_check, first_wait_end)
        self.assertIn('[[ "$keyboard_route" != x11 ]]', verifier)
        self.assertIn("private UU canvas matches the saved relay size", verifier)
        self.assertIn("live X11 desktop matches the UU relay size", verifier)
        self.assertIn("align --resolution to avoid black space or clipping", verifier)

    def test_verifier_supports_the_application_profile_network_namespace(self):
        verifier = (REPOSITORY / "scripts" / "verify.sh").read_text()

        self.assertIn(
            "AstrillLazyRouter.ApplicationProfile@uuremote.service",
            verifier,
        )
        self.assertIn("bridge_service_active", verifier)
        self.assertIn("process_namespace_listener_ready", verifier)
        self.assertIn('"/proc/$pid/net/tcp6"', verifier)
        self.assertIn('$4 == "0A"', verifier)

    def test_user_service_starts_from_default_target(self):
        unit = (REPOSITORY / "systemd" / "uu-remote-bridge.service").read_text()
        self.assertIn("WantedBy=default.target", unit)
        self.assertNotIn("WantedBy=graphical-session.target", unit)

    def test_bridge_resource_runaway_is_contained(self):
        unit = (REPOSITORY / "systemd" / "uu-remote-bridge.service").read_text()

        self.assertIn("MemoryHigh=3G", unit)
        self.assertIn("MemoryMax=4G", unit)
        self.assertIn("MemorySwapMax=2G", unit)
        self.assertIn("TasksMax=1024", unit)
        self.assertIn("OOMPolicy=stop", unit)
        self.assertIn("Restart=on-failure", unit)

    def test_freerdp_cache_is_checksum_backed(self):
        builder = (REPOSITORY / "scripts" / "build-winpr.sh").read_text()
        self.assertIn(".build-recipe", builder)
        self.assertIn("sha256sum -c .build-sha256", builder)

    def test_freerdp_runtime_uses_the_retained_matching_revision(self):
        builder = (REPOSITORY / "scripts" / "build-winpr.sh").read_text()
        verifier = (REPOSITORY / "scripts" / "verify.sh").read_text()

        self.assertIn("168925dac792142f6d0b66e7e2d568a3d439521c", builder)
        self.assertIn("/2064/artifact/install/bin/sdl-freerdp.exe", builder)
        expected = "b384347b6d0dd1e0c9912d18f5993b4e30643470e2a627e112debb34e8710762"
        self.assertIn(expected, builder)
        self.assertIn(expected, verifier)

    def test_winpr_shim_uses_numeric_package_identity(self):
        shim = (REPOSITORY / "src" / "winpr_sspi_shim.c").read_text()

        self.assertIn("SSPI_PACKAGE_NEGOTIATE_ID 3u", shim)
        self.assertIn("~((ULONG_PTR)SSPI_PACKAGE_NEGOTIATE_ID)", shim)
        self.assertNotIn("static const char negotiate_name", shim)

    def test_clipboard_channel_is_enabled(self):
        launcher = (REPOSITORY / "scripts" / "uu-remote-bridge").read_text()

        self.assertIn("+clipboard", launcher)
        self.assertNotIn("-clipboard", launcher)

    def test_opt_in_cursor_guard_uses_absolute_ungrabbed_mouse(self):
        launcher = (REPOSITORY / "scripts" / "uu-remote-bridge").read_text()

        options = launcher.index("freerdp_mouse_options=()")
        guard = launcher.index(
            'if [[ "$cursor_guard_setting" == on ]]; then',
            options,
        )
        mouse = launcher.index(
            "freerdp_mouse_options+=(/mouse:relative:off,grab:off)",
            guard,
        )
        relay = launcher.index('"${freerdp_mouse_options[@]}"', mouse)
        self.assertLess(options, guard)
        self.assertLess(guard, mouse)
        self.assertLess(mouse, relay)
        self.assertEqual(launcher.count("/mouse:relative:off,grab:off"), 1)
        self.assertNotIn("+mouse-relative", launcher)

    def test_hidden_cursor_guard_is_opt_in_and_process_scoped(self):
        guard = (REPOSITORY / "src" / "uu_cursor_guard.c").read_text()
        builder = (REPOSITORY / "scripts" / "build-compat.sh").read_text()
        installer = (REPOSITORY / "install.sh").read_text()
        launcher = (REPOSITORY / "scripts" / "uu-remote-bridge").read_text()
        verifier = (REPOSITORY / "scripts" / "verify.sh").read_text()
        digest = (REPOSITORY / "scripts" / "runtime-source-digest").read_text()

        self.assertIn('"SetCursor"', guard)
        self.assertIn('"GetCursorInfo"', guard)
        self.assertIn('"GetIconInfo"', guard)
        self.assertIn("if (cursor == NULL)", guard)
        self.assertIn("IDC_ARROW", guard)
        self.assertIn("CopyImage(", guard)
        self.assertIn('L"UURB_CURSOR_SIZE"', guard)
        self.assertIn("cursor_dimensions", guard)
        self.assertIn("fallback_cursor_width != requested_size", guard)
        self.assertIn("cursor->flags = CURSOR_SHOWING", guard)
        self.assertNotIn("cursor->flags |= CURSOR_SHOWING", guard)
        self.assertNotIn('"ClipCursor"', guard)
        self.assertNotIn('"ShowCursor"', guard)
        self.assertIn("open_log(process_name)", guard)
        self.assertIn(
            '_wcsicmp(process_name, L"GameViewerServer.exe") != 0',
            guard,
        )
        for source in (builder, installer, launcher, verifier):
            self.assertIn("uu-cursor-guard.dll", source)
        self.assertIn("src/uu_cursor_guard.c", digest)
        self.assertIn(
            'cursor_guard_setting="${UURB_CURSOR_GUARD:-off}"',
            launcher,
        )
        self.assertIn('[[ "$cursor_guard_setting" == on ]]', launcher)
        self.assertIn(
            "optional cursor guard is disabled and not loaded",
            verifier,
        )
        self.assertIn(
            "opt-in relay and UU cursor guards are active",
            verifier,
        )
        injection = launcher.index(
            '"$cursor_guard_windows_path" sdl-freerdp.exe'
        )
        reader_injection = launcher.index(
            '"$cursor_guard_windows_path" GameViewerServer.exe'
        )
        bootstrap = launcher.index("\nbootstrap_account\n", injection)
        self.assertLess(reader_injection, injection)
        self.assertLess(injection, bootstrap)
        self.assertIn("pgrep -n -u \"$UID\" -x 'sdl-freerdp.exe'", verifier)
        guard_enabled = verifier.index(
            'if [[ "$cursor_guard_setting" == on ]]; then'
        )
        guard_wait = verifier.index("for _ in {1..100}; do", guard_enabled)
        guard_result = verifier.index(
            "opt-in relay and UU cursor guards are active", guard_wait
        )
        self.assertLess(guard_enabled, guard_wait)
        self.assertLess(guard_wait, guard_result)
        self.assertIn("sleep 0.05", verifier[guard_wait:guard_result])

    def test_phone_ime_unicode_input_is_normalized(self):
        bridge = (REPOSITORY / "src" / "uu_input_bridge.c").read_text()
        broker = (REPOSITORY / "src" / "uu_input_broker.c").read_text()
        helper = (REPOSITORY / "src" / "uu_x11_input.c").read_text()
        protocol = (REPOSITORY / "src" / "x11_input_protocol.h").read_text()

        self.assertIn("contains_unicode_keyboard", bridge)
        self.assertIn("KEYEVENTF_UNICODE", bridge)
        self.assertIn("#define INPUT_BRIDGE_MAX_INPUTS 2048UL", bridge)
        self.assertIn("#define INPUT_BRIDGE_MAX_INPUTS 2048UL", broker)
        self.assertIn("UURB_X11_INPUT_MAX_EVENTS UINT32_C(2048)", protocol)
        self.assertIn("ERROR_INSUFFICIENT_BUFFER", bridge)
        self.assertIn("key_mapping_for_character", broker)
        self.assertIn("VkKeyScanW", broker)
        self.assertIn('normalized_unicode ? "normalized"', broker)
        self.assertIn("request_relay_focus", broker)
        self.assertIn("INPUT_BRIDGE_FOCUS_TIMEOUT_MS", broker)
        self.assertIn("Sleep(text_key_delay_ms)", broker)
        self.assertIn('L"UURB_TEXT_KEY_DELAY_MS"', broker)
        self.assertIn('"x11-text"', broker)
        self.assertIn('"x11-clipboard-text"', broker)
        self.assertIn("phone_text_uses_clipboard", broker)
        self.assertIn("UURB_X11_INPUT_TEXT", broker)
        self.assertIn('L"UURB_PHONE_TEXT_MODE"', broker)
        self.assertIn("inject_clipboard_text", helper)
        self.assertIn('execl("/usr/bin/xclip"', helper)
        self.assertIn('"XGetSelectionOwner"', helper)
        self.assertIn("current_owner != previous_owner", helper)
        self.assertIn("text_events_to_utf8", helper)
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

    def test_direct_x11_input_route_is_opt_in_and_fail_safe(self):
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
        self.assertIn("release_pressed_inputs", helper)
        self.assertIn("minimum_hold_ms", helper)
        self.assertIn("XKeysymToKeycode", helper)
        self.assertIn("extended_scan_to_keysym", helper)
        self.assertIn("0xff52UL; /* XK_Up */", helper)
        self.assertIn("0xff54UL; /* XK_Down */", helper)
        self.assertIn("0xff51UL; /* XK_Left */", helper)
        self.assertIn("0xff53UL; /* XK_Right */", helper)
        self.assertNotIn("return 104; /* Down */", helper)
        self.assertIn("XTestFakeButtonEvent", helper)
        self.assertIn("XTestFakeMotionEvent", helper)
        self.assertIn("XTestFakeRelativeMotionEvent", helper)
        self.assertIn("valid_mouse_event", helper)
        self.assertIn('route = "x11-mouse"', broker)
        self.assertTrue(
            (REPOSITORY / "scripts" / "test-x11-mouse.sh").exists()
        )

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

    def test_uu_terminal_uses_authenticated_native_pty_bridge(self):
        builder = (REPOSITORY / "scripts" / "build-compat.sh").read_text()
        installer = (REPOSITORY / "install.sh").read_text()
        uninstaller = (REPOSITORY / "uninstall.sh").read_text()
        launcher = (REPOSITORY / "scripts" / "uu-remote-bridge").read_text()
        verifier = (REPOSITORY / "scripts" / "verify.sh").read_text()
        digest = (REPOSITORY / "scripts" / "runtime-source-digest").read_text()
        native = (REPOSITORY / "src" / "uu_terminal_bridge.c").read_text()
        proxy = (REPOSITORY / "src" / "uu_terminal_proxy.c").read_text()

        self.assertIn("uu-terminal-bridge", builder)
        self.assertIn("uu-terminal-proxy.exe", builder)
        self.assertIn("-lutil", builder)
        self.assertIn("-lws2_32", builder)
        self.assertIn("Refusing to replace an unknown", installer)
        self.assertIn("bin/powershell.exe", installer)
        self.assertIn("Refusing to remove an unknown", uninstaller)
        self.assertIn("start_terminal_bridge", launcher)
        self.assertIn("UURB_TERMINAL_BRIDGE_TOKEN", launcher)
        self.assertIn("uu-terminal-bridge.runtime", launcher)
        self.assertIn("authenticated native Ubuntu PTY bridge", verifier)
        self.assertIn("terminal_config_mode", verifier)
        self.assertIn("src/uu_terminal_bridge.c", digest)
        self.assertIn("src/uu_terminal_proxy.c", digest)
        self.assertIn("INADDR_LOOPBACK", native)
        self.assertIn("constant_time_equal", native)
        self.assertIn("forkpty", native)
        self.assertIn("MAX_SESSIONS 4", native)
        self.assertIn("UURB_TERMINAL_FRAME_RESIZE", native)
        self.assertIn('setenv("TERM", "xterm-256color", 1)', native)
        self.assertIn('execl(shell, shell, "-l"', native)
        self.assertIn("UURB_TERMINAL_BRIDGE_TOKEN", proxy)
        self.assertIn("load_runtime_configuration", proxy)
        self.assertIn("UURB_TERMINAL_CONFIG_FILENAME", proxy)
        self.assertIn("INADDR_LOOPBACK", proxy)
        self.assertIn("GetConsoleScreenBufferInfo", proxy)
        self.assertTrue(
            (REPOSITORY / "scripts" / "test-terminal-bridge.sh").exists()
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
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
                    str(root / "uu-terminal-bridge"),
                    str(REPOSITORY / "src" / "uu_terminal_bridge.c"),
                    "-lutil",
                ],
                check=True,
                cwd=REPOSITORY,
            )
            subprocess.run(
                [
                    "x86_64-w64-mingw32-gcc",
                    "-std=c11",
                    "-O2",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-I",
                    str(REPOSITORY / "src"),
                    "-Wl,--no-insert-timestamp",
                    "-o",
                    str(root / "uu-terminal-proxy.exe"),
                    str(REPOSITORY / "src" / "uu_terminal_proxy.c"),
                    "-lws2_32",
                ],
                check=True,
                cwd=REPOSITORY,
            )

    def test_ci_installs_the_terminal_proxy_cross_compiler(self):
        workflow = (
            REPOSITORY / ".github" / "workflows" / "validate.yml"
        ).read_text()

        self.assertIn("gcc-mingw-w64-x86-64-win32", workflow)

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
