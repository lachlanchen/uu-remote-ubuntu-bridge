"""A minimal RFB client for tests: read the framebuffer and send pointer events.

It speaks just enough RFB 3.8 for an x11vnc server without a password: no
authentication, raw encoding, 32-bit true colour.
"""
import collections
import socket
import struct
import time


class RFBClient:
    def __init__(self, port, timeout=10):
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        self.sock.recv(12)
        self.sock.sendall(b"RFB 003.008\n")
        count = self.read(1)[0]
        self.read(count)
        self.sock.sendall(bytes([1]))  # security type None
        if struct.unpack(">I", self.read(4))[0] != 0:
            raise ConnectionError("security handshake refused")
        self.sock.sendall(bytes([1]))  # shared
        self.width, self.height = struct.unpack(">HH", self.read(4))
        self.read(16)
        self.read(struct.unpack(">I", self.read(4))[0])
        # 32 bits per pixel, little endian, red 16, green 8, blue 0.
        self.sock.sendall(
            struct.pack(">BxxxBBBBHHHBBBxxx", 0, 32, 24, 0, 1, 255, 255, 255, 16, 8, 0)
        )
        self.sock.sendall(struct.pack(">BxHi", 2, 1, 0))  # raw encoding only

    def read(self, count):
        data = b""
        while len(data) < count:
            chunk = self.sock.recv(count - len(data))
            if not chunk:
                raise EOFError("server closed the connection")
            data += chunk
        return data

    def frame(self):
        """Return the whole framebuffer as a Counter of (red, green, blue) colours."""
        self.sock.sendall(struct.pack(">BBHHHH", 3, 0, 0, 0, self.width, self.height))
        pixels = bytearray(self.width * self.height * 4)
        remaining = self.width * self.height
        while remaining > 0:
            kind = self.read(1)[0]
            if kind == 2:  # bell
                continue
            if kind == 3:  # server cut text
                self.read(3)
                self.read(struct.unpack(">I", self.read(4))[0])
                continue
            if kind != 0:
                raise RuntimeError(f"unexpected server message {kind}")
            self.read(1)
            for _ in range(struct.unpack(">H", self.read(2))[0]):
                x, y, width, height, encoding = struct.unpack(">HHHHi", self.read(12))
                if encoding != 0:
                    raise RuntimeError(f"unexpected encoding {encoding}")
                data = self.read(width * height * 4)
                for row in range(height):
                    start = ((y + row) * self.width + x) * 4
                    pixels[start:start + width * 4] = data[row * width * 4:(row + 1) * width * 4]
                remaining -= width * height
        return collections.Counter(zip(pixels[2::4], pixels[1::4], pixels[0::4]))

    def pointer(self, x, y, buttons=0):
        self.sock.sendall(struct.pack(">BBHH", 5, buttons, x, y))

    def click(self, x, y, pause=0.15):
        """Move, then press and release. x11vnc applies pointer events on its
        polling cycle, so a press sent right behind the move can land where the
        pointer used to be."""
        for buttons, wait in ((0, 2 * pause), (1, pause), (0, pause)):
            self.pointer(x, y, buttons)
            time.sleep(wait)

    def close(self):
        self.sock.close()
