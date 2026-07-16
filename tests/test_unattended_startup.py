from __future__ import annotations

import unittest
from pathlib import Path


REPO_DIR = Path(__file__).resolve().parent.parent


class UnattendedStartupTests(unittest.TestCase):
    def test_unlock_unit_orders_keyring_before_remote_desktop(self) -> None:
        unit = (
            REPO_DIR / "systemd" / "uu-keyring-unlock.service"
        ).read_text(encoding="utf-8")
        self.assertIn("Requires=gnome-keyring-daemon.service", unit)
        self.assertIn("After=gnome-keyring-daemon.service", unit)
        self.assertIn("Before=gnome-remote-desktop.service", unit)
        self.assertIn("LoadCredentialEncrypted=login-keyring-password:", unit)
        self.assertIn("WantedBy=default.target", unit)
        self.assertNotIn("RemainAfterExit", unit)

    def test_bridge_requires_successful_unlock_in_unattended_mode(self) -> None:
        dropin = (
            REPO_DIR / "systemd" / "uu-remote-bridge-unattended.conf"
        ).read_text(encoding="utf-8")
        self.assertIn("Requires=uu-keyring-unlock.service", dropin)
        self.assertIn("After=uu-keyring-unlock.service", dropin)

    def test_helper_reads_systemd_credential_and_uses_dbus(self) -> None:
        helper = (
            REPO_DIR / "scripts" / "uu-keyring-unlock.py"
        ).read_text(encoding="utf-8")
        self.assertIn('os.environ.get("CREDENTIALS_DIRECTORY")', helper)
        self.assertIn("UnlockWithMasterPassword", helper)
        self.assertNotIn("subprocess", helper)
        self.assertNotIn("secret-tool", helper)

    def test_configurator_has_enable_disable_and_tpm_rollback(self) -> None:
        configurator = (
            REPO_DIR / "scripts" / "configure-unattended.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("systemd-creds encrypt --with-key=tpm2", configurator)
        self.assertIn("restore_gdm_state", configurator)
        self.assertIn('setfacl -x "u:$bridge_user"', configurator)
        self.assertIn("--replace-credential", configurator)
        self.assertIn("DBUS_SESSION_BUS_ADDRESS=unix:path=", configurator)


if __name__ == "__main__":
    unittest.main()
