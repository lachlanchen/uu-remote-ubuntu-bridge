#!/usr/bin/env python3
"""Isolated-test clipboard-restoration race, without reading any text.

Run only on the disposable display allocated by test-x11-clipboard-text.sh.
Models a desktop manager restoring its cached selection after owner=None.
The sentinel owner need not serve data: a correct handoff never triggers it.
"""
import ctypes as C
import os
import time

display_name = os.environ.get('DISPLAY', '')
if (os.environ.get('UURB_DISPOSABLE_SELECTION_TEST') != '1' or
        display_name not in {f':{n}' for n in range(88, 100)}):
    raise SystemExit('refusing a non-test display')

x = C.CDLL('libX11.so.6')
fixes = C.CDLL('libXfixes.so.3')
x.XOpenDisplay.argtypes = [C.c_char_p]
x.XOpenDisplay.restype = C.c_void_p
x.XDefaultRootWindow.argtypes = [C.c_void_p]
x.XDefaultRootWindow.restype = C.c_ulong
x.XCreateSimpleWindow.argtypes = [C.c_void_p, C.c_ulong, C.c_int, C.c_int,
                                 C.c_uint, C.c_uint, C.c_uint, C.c_ulong, C.c_ulong]
x.XCreateSimpleWindow.restype = C.c_ulong
x.XInternAtom.argtypes = [C.c_void_p, C.c_char_p, C.c_int]
x.XInternAtom.restype = C.c_ulong
x.XPending.argtypes = [C.c_void_p]
x.XNextEvent.argtypes = [C.c_void_p, C.c_void_p]
x.XSync.argtypes = [C.c_void_p, C.c_int]
x.XSetSelectionOwner.argtypes = [C.c_void_p, C.c_ulong, C.c_ulong, C.c_ulong]
fixes.XFixesQueryExtension.argtypes = [C.c_void_p, C.POINTER(C.c_int), C.POINTER(C.c_int)]
fixes.XFixesSelectSelectionInput.argtypes = [C.c_void_p, C.c_ulong, C.c_ulong, C.c_ulong]

class SelectionEvent(C.Structure):
    _fields_ = [('type', C.c_int), ('serial', C.c_ulong), ('send_event', C.c_int),
                ('display', C.c_void_p), ('window', C.c_ulong), ('subtype', C.c_int),
                ('owner', C.c_ulong), ('selection', C.c_ulong),
                ('timestamp', C.c_ulong), ('selection_timestamp', C.c_ulong)]

d = x.XOpenDisplay(None)
if not d:
    raise SystemExit('test display unavailable')
event_base, error_base = C.c_int(), C.c_int()
if not fixes.XFixesQueryExtension(d, C.byref(event_base), C.byref(error_base)):
    raise SystemExit('XFixes unavailable')
window = x.XCreateSimpleWindow(d, x.XDefaultRootWindow(d), 0, 0, 1, 1, 0, 0, 0)
selection = x.XInternAtom(d, b'CLIPBOARD', 0)
fixes.XFixesSelectSelectionInput(d, window, selection, 7)
x.XSync(d, 0)
print('ready', flush=True)
observed_owner = False
restore_at = None
deadline = time.monotonic() + 90
while time.monotonic() < deadline:
    while x.XPending(d):
        raw = (C.c_long * 24)()
        x.XNextEvent(d, C.byref(raw))
        event = C.cast(C.byref(raw), C.POINTER(SelectionEvent)).contents
        if event.type != event_base.value or event.selection != selection:
            continue
        if event.owner:
            observed_owner = True
        elif observed_owner:
            print('gap', flush=True)
            # Do not cancel when a new owner appears: that is exactly the
            # delayed restoration which used to displace the replacement.
            restore_at = time.monotonic() + .010
    if restore_at is not None and time.monotonic() >= restore_at:
        x.XSetSelectionOwner(d, selection, window, 0)
        x.XSync(d, 0)
        restore_at = None
    time.sleep(.001)
raise SystemExit('test guard deadline exceeded')
