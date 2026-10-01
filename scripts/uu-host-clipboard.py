#!/usr/bin/python3
"""Opt-in X11 host -> private Wine text clipboard, without paste injection.

XFixes observes fresh copies only. XRes authenticates the local owner process;
bridge-owned selections (dictation or incoming clipboard) never echo back.
No clipboard contents are logged or persisted. Requires python3-xlib.
"""
import argparse
import os
from pathlib import Path
import selectors
import signal
import subprocess
import time

from Xlib import X, Xatom, display, error, protocol
from Xlib.ext import res, xfixes

MAX_BYTES = 60 * 1024  # One bounded X property; no partial/INCR transfer.


def external_owner(pid, bridge_pid, proc=Path('/proc')):
    """Require our UID and a live owner outside the bridge process tree."""
    try:
        if (proc / str(pid)).stat().st_uid != os.getuid():
            return False
        for _ in range(128):
            if pid == bridge_pid:
                return False
            if pid <= 1:
                return True
            # comm can contain spaces and parentheses.
            fields = (proc / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()
            pid = int(fields[1])
    except (OSError, ValueError, IndexError):
        return False
    return False


def owner_pid(connection, owner):
    try:
        reply = connection.res_query_client_ids([
            {'client': owner.id, 'mask': res.LocalClientPIDMask}])
        for entry in reply.ids:
            if entry.spec.mask & res.LocalClientPIDMask and entry.value:
                return int(entry.value[0])
    except (error.XError, AttributeError, IndexError):
        pass
    return 0


def read_text(env):
    child = subprocess.Popen(['/usr/bin/xclip', '-selection', 'clipboard',
                              '-target', 'UTF8_STRING', '-out'], env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    data = bytearray()
    try:
        with selectors.DefaultSelector() as ready:
            ready.register(child.stdout, selectors.EVENT_READ)
            deadline = time.monotonic() + 1.5
            while time.monotonic() < deadline:
                if not ready.select(max(0, deadline - time.monotonic())):
                    return None
                chunk = os.read(child.stdout.fileno(), min(8192, MAX_BYTES + 1 - len(data)))
                if not chunk:
                    if child.wait(timeout=.5) != 0 or not data or b'\0' in data:
                        return None
                    data.decode('utf-8', errors='strict')
                    return bytes(data)
                data.extend(chunk)
                if len(data) > MAX_BYTES:
                    return None
    except (UnicodeError, OSError, subprocess.TimeoutExpired):
        return None
    finally:
        if child.poll() is None:
            child.kill()
        child.wait()
        child.stdout.close()
    return None


def run(args):
    private = display.Display()  # Inherited private DISPLAY/XAUTHORITY.
    host_env = dict(os.environ, DISPLAY=args.host_display, XAUTHORITY=args.host_authority)
    os.environ.update(DISPLAY=args.host_display, XAUTHORITY=args.host_authority)
    host = display.Display()
    if not host.has_extension('X-Resource') or not host.has_extension('XFIXES'):
        raise RuntimeError('XRes and XFixes are required; no unsafe fallback')
    host.xfixes_query_version()
    host_clipboard = host.intern_atom('CLIPBOARD')
    host_window = host.screen().root.create_window(0, 0, 1, 1, 0, X.CopyFromParent)
    host.xfixes_select_selection_input(host_window, host_clipboard,
                                      xfixes.XFixesSetSelectionOwnerNotifyMask)
    private_window = private.screen().root.create_window(0, 0, 1, 1, 0, X.CopyFromParent)
    private_window.change_property(private.intern_atom('_NET_WM_PID'), Xatom.CARDINAL,
                                   32, [os.getpid()])
    clipboard, utf8, targets = (private.intern_atom(x) for x in
                                ('CLIPBOARD', 'UTF8_STRING', 'TARGETS'))
    text = b''
    last_text = None
    host.sync()
    private.sync()
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    print('Host clipboard ready; fresh external text copies only; no paste injection.', flush=True)
    try:
        with selectors.DefaultSelector() as ready:
            ready.register(host.fileno(), selectors.EVENT_READ)
            ready.register(private.fileno(), selectors.EVENT_READ)
            while not stopping:
                for connection in (host, private):
                    while connection.pending_events():
                        event = connection.next_event()
                        if connection is host and hasattr(event, 'selection_timestamp'):
                            owner = host.get_selection_owner(host_clipboard)
                            if not owner or owner != event.owner:
                                continue
                            pid = owner_pid(host, owner)
                            if not pid or not external_owner(pid, args.bridge_pid):
                                continue
                            content = read_text(host_env)
                            # Recheck ownership and PID after lazy selection conversion.
                            if (content is None or host.get_selection_owner(host_clipboard) != owner
                                    or owner_pid(host, owner) != pid):
                                continue
                            if (content == last_text and
                                    private.get_selection_owner(clipboard) == private_window):
                                continue
                            text = last_text = content
                            private_window.set_selection_owner(clipboard, X.CurrentTime)
                            private.flush()
                        elif connection is private and event.type == X.SelectionRequest:
                            prop = event.property or event.target
                            result = X.NONE
                            if event.selection == clipboard and text:
                                try:
                                    if event.target == targets:
                                        event.requestor.change_property(prop, Xatom.ATOM, 32,
                                                                        [targets, utf8, Xatom.STRING])
                                        result = prop
                                    elif event.target in (utf8, Xatom.STRING):
                                        payload = text if event.target == utf8 else text.decode('utf-8').encode('latin1')
                                        event.requestor.change_property(prop, event.target, 8, payload)
                                        result = prop
                                except (UnicodeError, error.XError):
                                    pass
                            event.requestor.send_event(protocol.event.SelectionNotify(
                                time=event.time, requestor=event.requestor, selection=event.selection,
                                target=event.target, property=result), propagate=False)
                            private.flush()
                ready.select(.25)
    finally:
        host_window.destroy()
        private_window.destroy()
        host.close()
        private.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host-display', required=True)
    parser.add_argument('--host-authority', required=True)
    parser.add_argument('--bridge-pid', required=True, type=int)
    run(parser.parse_args())
