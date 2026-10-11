#!/usr/bin/env python3
"""Dock context menus must not warn about a non-top-level transient parent.

Right-clicking the Report view (or the Python console) makes Qt resolve the
popup QMenu's transient parent from the parent widget's native window
(QMenuPrivate::transientParentWindow()).  A dock that owns a native, non-top
level QWidgetWindow -- which happens once a Vulkan viewport made its ancestors
native, or after a float/re-dock cycle -- makes QWindow::setTransientParent()
reject that window with

    QWidgetWindow(0x..., name="Report viewWindow") must be a top level window.

and the popup loses its transient parent.  The probe docks the two views,
forces the dock to own a native window (the state that triggers it), opens the
real context menu on each and reports whether the warning appeared.

Markers on stdout (fd 1; FreeCAD redirects Python's stdout):
  DOCKMENU_RESULT reportview=<0|1> pythonconsole=<0|1> opened=<0|1> found=<0|1>

Run:
  HOME=<writable dir> DM_OUT=<writable dir> QT_QPA_PLATFORM=xcb \
  QT_STYLE_OVERRIDE=fusion FC_SKIP_UNSAVED_PROMPT=1 \
  build-freecad/bin/FreeCAD dock_contextmenu_probe.py
"""

import os

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtGui, QtWidgets

OUT = os.environ.get("DM_OUT", "/tmp/dm")
os.makedirs(OUT, exist_ok=True)
LOG = open(os.path.join(OUT, "probe.log"), "w")
WARN = "must be a top level window"
_seen = {"len": 0, "menu": False}


def log(*args):
    LOG.write(" ".join(str(a) for a in args) + "\n")
    LOG.flush()


def emit(line):
    log(line)
    try:
        os.write(1, (line + "\n").encode())
    except OSError:
        pass


def new_log_text():
    try:
        with open(os.environ.get("DM_LOG", os.path.join(OUT, "freecad.log")),
                  errors="replace") as fh:
            data = fh.read()
    except OSError:
        return ""
    new = data[_seen["len"]:]
    _seen["len"] = len(data)
    return new


def dock(name):
    win = FreeCADGui.getMainWindow()
    return win.findChild(QtWidgets.QDockWidget, name)


def text_widget(dock_widget):
    content = dock_widget.widget() if dock_widget else None
    if isinstance(content, (QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit)):
        return content
    return None


def make_native(dock_widget):
    """Give the dock a native window while docked (non-top level)."""
    if dock_widget is None:
        return None
    handle = dock_widget.windowHandle()
    if handle is None:
        dock_widget.winId()
        QtCore.QCoreApplication.processEvents()
        handle = dock_widget.windowHandle()
    return handle


def close_menus():
    # Runs inside the popup's nested event loop: proves the context menu opened.
    for widget in QtWidgets.QApplication.topLevelWidgets():
        if isinstance(widget, QtWidgets.QMenu) and widget.isVisible():
            _seen["menu"] = True
            log("closing visible menu")
            widget.close()


def open_context_menu(widget):
    """Right-click semantics: the event arrives at the scroll area's viewport."""
    viewport = getattr(widget, "viewport", lambda: None)()
    target = viewport if viewport is not None else widget
    target.setMouseTracking(True)
    widget.setFocus()
    local = QtCore.QPoint(max(1, target.width() // 2), max(1, target.height() // 2))
    event = QtGui.QContextMenuEvent(QtGui.QContextMenuEvent.Mouse, local,
                                    target.mapToGlobal(local))
    QtWidgets.QApplication.sendEvent(target, event)


steps = [0]
results = {}


def phase_for_dock(name):
    widget = text_widget(dock(name))
    if widget is None:
        log("%s: no text widget" % name)
        return False
    handle = make_native(dock(name))
    log("%s: dock handle=%s topLevel=%s"
        % (name, handle, handle.isTopLevel() if handle else None))
    _seen["menu"] = False
    QtCore.QTimer.singleShot(600, close_menus)
    open_context_menu(widget)
    text = new_log_text()
    warned = WARN in text
    log("%s: warning=%s menu_opened=%s" % (name, warned, _seen["menu"]))
    results[name] = warned
    results["opened"] = results.get("opened", False) or bool(_seen["menu"])
    if warned:
        for line in text.splitlines():
            if WARN in line:
                log("%s: WARNING LINE: %s" % (name, line))
    return True


def step():
    steps[0] += 1
    k = steps[0]
    try:
        if k == 1:
            FreeCAD.newDocument("DockMenuProbe").recompute()
            FreeCADGui.activateWorkbench("PartWorkbench")
            FreeCADGui.updateGui()
            for name in ("Report view", "Python console"):
                d = dock(name)
                if d is not None:
                    d.show()
                    d.raise_()
            QtCore.QCoreApplication.processEvents()
            results["found"] = (dock("Report view") is not None
                                and text_widget(dock("Report view")) is not None)
            log("docks ready; report view found=%s" % results["found"])
        elif k == 2:
            phase_for_dock("Report view")
        elif k == 3:
            phase_for_dock("Python console")
        elif k >= 5:
            emit("DOCKMENU_RESULT reportview=%d pythonconsole=%d opened=%d found=%d"
                 % (results.get("Report view", 0),
                    results.get("Python console", 0),
                    results.get("opened", 0),
                    results.get("found", 0)))
            ok = (results.get("found") and results.get("opened")
                  and not results.get("Report view")
                  and not results.get("Python console"))
            emit("[VERDICT] dock_contextmenu %s" % ("PASS" if ok else "FAIL"))
            LOG.close()
            os._exit(0)
    except Exception:  # noqa: BLE001
        import traceback

        log("EXCEPTION:\n%s" % traceback.format_exc())
        LOG.close()
        os._exit(1)
    QtCore.QTimer.singleShot(700, step)


QtCore.QTimer.singleShot(120000, lambda: os._exit(4))
QtCore.QTimer.singleShot(2500, step)
