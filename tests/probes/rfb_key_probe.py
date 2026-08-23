#!/usr/bin/env python3

"""Send a bounded printable-key sequence to a local RFB server."""

from __future__ import annotations

import argparse
import socket
import struct


def receive_exact(connection: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = connection.recv(remaining)
        if not chunk:
            raise RuntimeError("RFB server closed the connection")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def initialize_rfb(connection: socket.socket) -> None:
    version = receive_exact(connection, 12)
    if not version.startswith(b"RFB "):
        raise RuntimeError("invalid RFB protocol banner")
    connection.sendall(b"RFB 003.008\n")

    count = receive_exact(connection, 1)[0]
    if count == 0:
        reason_size = struct.unpack(">I", receive_exact(connection, 4))[0]
        reason = receive_exact(connection, reason_size).decode(errors="replace")
        raise RuntimeError(f"RFB server rejected the connection: {reason}")
    security_types = receive_exact(connection, count)
    if 1 not in security_types:
        raise RuntimeError("RFB server did not offer None authentication")
    connection.sendall(b"\x01")
    result = struct.unpack(">I", receive_exact(connection, 4))[0]
    if result != 0:
        raise RuntimeError(f"RFB authentication failed: {result}")

    connection.sendall(b"\x01")
    server_header = receive_exact(connection, 24)
    name_size = struct.unpack(">I", server_header[20:24])[0]
    receive_exact(connection, name_size)


def send_keys(connection: socket.socket, text: str) -> None:
    for character in text:
        codepoint = ord(character)
        keysym = codepoint if codepoint <= 0xFF else 0x01000000 | codepoint
        connection.sendall(struct.pack(">BBHI", 4, 1, 0, keysym))
        connection.sendall(struct.pack(">BBHI", 4, 0, 0, keysym))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("port", type=int)
    parser.add_argument("text")
    arguments = parser.parse_args()

    with socket.create_connection(("127.0.0.1", arguments.port), timeout=5) as connection:
        initialize_rfb(connection)
        send_keys(connection, arguments.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
