import subprocess
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
        self.assertIn(
            "OPENSSL_MODULES=/usr/lib/x86_64-linux-gnu/ossl-modules",
            launcher,
        )

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


if __name__ == "__main__":
    unittest.main()
