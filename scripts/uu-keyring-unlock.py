#!/usr/bin/python3

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from gi.repository import Gio, GLib


SERVICE = "org.freedesktop.secrets"
SERVICE_PATH = "/org/freedesktop/secrets"
SERVICE_INTERFACE = "org.freedesktop.Secret.Service"
INTERNAL_INTERFACE = (
    "org.gnome.keyring.InternalUnsupportedGuiltRiddenInterface"
)


def call(
    bus: Gio.DBusConnection,
    path: str,
    interface: str,
    method: str,
    parameters: GLib.Variant | None,
    destination: str = SERVICE,
) -> GLib.Variant:
    return bus.call_sync(
        destination,
        path,
        interface,
        method,
        parameters,
        None,
        Gio.DBusCallFlags.NONE,
        10_000,
        None,
    )


def wait_for_service(bus: Gio.DBusConnection) -> None:
    # GDM autologin can start the user manager before GNOME Keyring has
    # acquired the Secret Service name. Keep the initial systemd transaction
    # alive through that bounded boot race so dependent units are not stranded.
    for _ in range(1200):
        owned = call(
            bus,
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "NameHasOwner",
            GLib.Variant("(s)", (SERVICE,)),
            destination="org.freedesktop.DBus",
        ).unpack()[0]
        if owned:
            return
        time.sleep(0.1)
    raise RuntimeError("GNOME Keyring did not publish the Secret Service")


def collection_is_locked(bus: Gio.DBusConnection, collection: str) -> bool:
    return call(
        bus,
        collection,
        "org.freedesktop.DBus.Properties",
        "Get",
        GLib.Variant("(ss)", ("org.freedesktop.Secret.Collection", "Locked")),
    ).unpack()[0]


def main() -> int:
    credentials_directory = os.environ.get("CREDENTIALS_DIRECTORY")
    if not credentials_directory:
        raise RuntimeError("CREDENTIALS_DIRECTORY is unavailable")

    credential = Path(credentials_directory) / "login-keyring-password"
    password = credential.read_bytes()
    if not password:
        raise RuntimeError("the TPM-backed keyring credential is empty")

    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    wait_for_service(bus)
    collection = call(
        bus,
        SERVICE_PATH,
        SERVICE_INTERFACE,
        "ReadAlias",
        GLib.Variant("(s)", ("login",)),
    ).unpack()[0]
    if collection == "/":
        raise RuntimeError("the GNOME login keyring does not exist")

    if not collection_is_locked(bus, collection):
        return 0

    session = call(
        bus,
        SERVICE_PATH,
        SERVICE_INTERFACE,
        "OpenSession",
        GLib.Variant("(sv)", ("plain", GLib.Variant("s", ""))),
    ).unpack()[1]
    try:
        secret = (session, bytes(), password, "text/plain")
        call(
            bus,
            SERVICE_PATH,
            INTERNAL_INTERFACE,
            "UnlockWithMasterPassword",
            GLib.Variant("(o(oayays))", (collection, secret)),
        )
    finally:
        try:
            call(
                bus,
                session,
                "org.freedesktop.Secret.Session",
                "Close",
                None,
            )
        except GLib.Error:
            pass

    if collection_is_locked(bus, collection):
        raise RuntimeError("the GNOME login keyring rejected the credential")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Failed to unlock GNOME Keyring: {error}", file=sys.stderr)
        raise SystemExit(1)
