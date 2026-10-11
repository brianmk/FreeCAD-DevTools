#!/usr/bin/env python3
"""A sketch tool's cursor must reach the visible viewport surface.

With the Vulkan viewport the GL widget is hidden and what the user sees (and
what the cursor is over) is the Vulkan widget's native container.  Cursor
changes are therefore routed through
``View3DInventorViewer::getCursorWidget()``: the container while the Vulkan page
is current, the viewer's own GL widget otherwise.  Every caller that used
``viewer->getWidget()`` instead sent the cursor to the hidden GL widget, so the
sketcher tool cursor (crosshair plus the tool icon, a bitmap cursor) was
invisible under Vulkan while it worked with Coin/GL.

The probe enters sketch edit mode, starts ``Sketcher_CreateLine`` and reports
which of the two widgets carries the tool's bitmap cursor.

Markers on stdout (fd 1; FreeCAD redirects Python's stdout):
  TOOLCURSOR_MODE mode=<vulkan|gl> container=<0|1>
  TOOLCURSOR_RESULT visible_bitmap=<0|1> container_bitmap=<0|1> viewer_bitmap=<0|1>

Run:
  HOME=<writable dir> build-freecad/bin/FreeCAD vk_tool_cursor_probe.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets
from freecad_probe import Session

RESULT = {"container": None, "viewer": None}


def emit(line):
    try:
        os.write(1, (line + "\n").encode())
    except OSError:
        pass


def widgets():
    """The Vulkan container (when there is one) and the GL viewer widget."""
    main = Gui.getMainWindow()
    container = None
    for widget in main.findChildren(QtWidgets.QWidget):
        if "WindowContainer" in widget.metaObject().className():
            container = widget
            break
    viewer = None
    for widget in main.findChildren(QtWidgets.QWidget):
        if "View3DInventorViewer" in widget.metaObject().className():
            viewer = widget
            break
    return container, viewer


def is_bitmap_cursor(widget):
    if widget is None:
        return False
    cursor = widget.cursor()
    return cursor.shape() == QtCore.Qt.BitmapCursor and not cursor.pixmap().isNull()


def run(session):
    import Part

    doc = FreeCAD.newDocument("ToolCursorProbe")
    body = doc.addObject("PartDesign::Body", "Body")
    sketch = body.newObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry(
        [Part.LineSegment(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(20, 0, 0))],
        False,
    )
    doc.recompute()

    Gui.activateWorkbench("SketcherWorkbench")
    Gui.ActiveDocument.setEdit(sketch.Name)
    QtCore.QCoreApplication.processEvents()

    container, viewer = widgets()
    mode = "vulkan" if container is not None else "gl"
    emit("TOOLCURSOR_MODE mode=%s container=%d" % (mode, container is not None))

    # Start a geometry tool; runCommand() has no usable return value, so the
    # tool cursor appearing is what proves the handler is running.
    Gui.runCommand("Sketcher_CreateLine", 1)
    QtCore.QCoreApplication.processEvents()
    session.move(200, 200)
    session.move(260, 240)
    QtCore.QCoreApplication.processEvents()

    container, viewer = widgets()
    container_bitmap = is_bitmap_cursor(container)
    viewer_bitmap = is_bitmap_cursor(viewer)
    visible = container if container is not None else viewer
    visible_bitmap = is_bitmap_cursor(visible)

    emit(
        "TOOLCURSOR_RESULT visible_bitmap=%d container_bitmap=%d viewer_bitmap=%d"
        % (visible_bitmap, container_bitmap, viewer_bitmap)
    )
    session.expect(
        "tool cursor reaches the visible surface",
        visible_bitmap,
        "mode=%s container_bitmap=%s viewer_bitmap=%s"
        % (mode, container_bitmap, viewer_bitmap),
    )
    session.finish()
    session.close()


Session.deferred("tool_cursor", run)
