#!/usr/bin/env python3
"""A solid-colour X window that logs the pointer events it receives.

usage: window_region_fixture.py TAG X Y WIDTH HEIGHT RRGGBB [WM_CLASS]

The window is override-redirect, so it sits exactly where it is asked to and
needs no window manager. Its events are appended to the file named by
FX_LOG, one "TAG press|motion X Y" line each (root coordinates). FX_TITLE
sets a window title. It prints "ready XID" once it is on screen.
"""
import os
import sys

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("GdkX11", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkX11, Gtk  # noqa: E402

tag = sys.argv[1]
x, y, width, height = map(int, sys.argv[2:6])
color = tuple(int(sys.argv[6][i:i + 2], 16) / 255 for i in (0, 2, 4))
wm_class = sys.argv[7] if len(sys.argv) > 7 else "gameviewer.exe"
log = open(os.environ["FX_LOG"], "a", buffering=1)

window = Gtk.Window(type=Gtk.WindowType.POPUP)
window.set_wmclass(wm_class, wm_class)
if os.environ.get("FX_TITLE"):
    window.set_title(os.environ["FX_TITLE"])
window.set_default_size(width, height)
window.move(x, y)
area = Gtk.DrawingArea()
area.add_events(
    Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.POINTER_MOTION_MASK
)
area.connect("draw", lambda widget, cr: (cr.set_source_rgb(*color), cr.paint(), False)[2])
area.connect(
    "button-press-event",
    lambda widget, event: log.write(f"{tag} press {int(event.x_root)} {int(event.y_root)}\n"),
)
area.connect(
    "motion-notify-event",
    lambda widget, event: log.write(f"{tag} motion {int(event.x_root)} {int(event.y_root)}\n"),
)
window.add(area)
window.show_all()
print("ready", GdkX11.X11Window.get_xid(window.get_window()), flush=True)
Gtk.main()
