#!/usr/bin/env python3
"""Measure how much of an edge highlight is really visible (Vulkan vs GL).

A committed edge selection is drawn with depth test LEQUAL at depth range
(0, 1).  A decorated edge is coplanar with the two faces it separates, so at a
90 degree seam the line rasterizes to the same depth as the faces and only the
fragments that win the comparison survive: the highlight is drawn but looks
almost invisible.  FreeCAD commit "Part/Gui: keep a selected edge visible at a
90 degree seam" adds a depth-range decal (far end 0.9999) for that state; this
probe measures the effect and the sibling .check.py asserts it.

The probe builds a 20 mm Part box in an isometric view and walks a plan of
selection/preselection states.  For every state it grabs the viewport into

    $EDGEHL_OUT/<mode>_<case>.png

and prints one marker per state:

    EDGEHL_VIEW mode=<mode> rect=<x>,<y>,<w>,<h> dpr=<f> vulkan_widget=<0|1>
    EDGEHL_CASE mode=<mode> case=<label> file=<png>
    EDGEHL_WARN mode=<mode> case=<label> no_frame_dump
    EDGEHL_DONE mode=<mode> cases=<n>

Vulkan frames must come from the presented swapchain: the native child window
cannot be grabbed with QWidget/QScreen grabs, so this needs a build with
FREECAD_USE_VULKAN_DEBUG_HOOKS=ON and FC_VULKAN_DUMP_FRAME=1 (both are set for
the `edge-highlight` case of vk_ci_raster_suite.json).  The GL mode uses a
window grab and works on any build.

Env:
  EDGEHL_MODE=vulkan|gl      render backend to exercise (default vulkan)
  EDGEHL_OUT=<dir>           where the PNGs are written (default /tmp/edgehl)
  EDGEHL_DOC=<file.FCStd>    use a document instead of the built-in box
  EDGEHL_OBJECT=<name>       object whose edges are selected (with EDGEHL_DOC)
  EDGEHL_EDGES=1,2,3         edge names to walk (default: 1..12 of the box)

Run:
  FC_VULKAN_DUMP_FRAME=1 python3 fcprobe/freecad_probe.py run \
      fcprobe/edge_highlight_probe.py --binary <build>/bin/FreeCAD \
      --profile vulkan-xcb --timeout 300 --env FC_VULKAN_DUMP_FRAME=1
"""


import glob
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/home/phantom/dev/FreeCAD-DevTools/fcprobe")

import FreeCAD  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from PySide import QtCore, QtWidgets  # noqa: E402
from freecad_probe import Session  # noqa: E402

MODE = os.environ.get("EDGEHL_MODE", "vulkan")
OUT = os.environ.get("EDGEHL_OUT", "/tmp/edgehl")
DOC_PATH = os.environ.get("EDGEHL_DOC", "")
DOC_OBJECT = os.environ.get("EDGEHL_OBJECT", "")
DOC_EDGES = [int(x) for x in os.environ.get("EDGEHL_EDGES", "").split(",") if x.strip()]
VIEW = "User parameter:BaseApp/Preferences/View"
os.makedirs(OUT, exist_ok=True)

BOX_EDGES = list(range(1, 13))
EDGE_IDS = DOC_EDGES if (DOC_PATH and DOC_EDGES) else BOX_EDGES
PLAN = [("none", None)]
PLAN += [("sel_Edge%d" % i, ("sel", "Edge%d" % i)) for i in EDGE_IDS]
PLAN += [("none_mid", None)]
PLAN += [("pre_Edge%d" % i, ("pre", "Edge%d" % i)) for i in EDGE_IDS]
if not DOC_PATH:
    PLAN += [("sel_Face1", ("sel", "Face1")), ("sel_Face2", ("sel", "Face2"))]


def emit(line):
    try:
        os.write(1, (line + "\n").encode())
    except OSError:
        pass


s = Session(name="edgehl")
state = {
    "ready": False, "idx": 0, "pending": None, "settle": 0,
    "doc": None, "box": None, "rect": None, "dpr": 1.0, "fitted": False,
}


def viewport_rect():
    _win, container, _stack = s.find_viewport()
    if container is None:
        return (0, 0, 1600, 1200), 1.0
    dpr = float(container.devicePixelRatioF() or 1.0)
    tl = container.mapToGlobal(QtCore.QPoint(0, 0))
    return (tl.x(), tl.y(), container.width(), container.height()), dpr


def setup():
    # UseVulkanRenderer decides which widget the view is built with.
    s.set_pref(VIEW, "UseVulkanRenderer", MODE == "vulkan")
    Gui.activateWorkbench("PartWorkbench")
    if DOC_PATH:
        doc = FreeCAD.openDocument(DOC_PATH)
        box = doc.getObject(DOC_OBJECT) if DOC_OBJECT else None
        if box is None:
            raise RuntimeError("object %r not found in %s" % (DOC_OBJECT, DOC_PATH))
    else:
        doc = FreeCAD.newDocument("EdgeHL")
        box = doc.addObject("Part::Box", "Box")
        box.Length = 20.0
        box.Width = 20.0
        box.Height = 20.0
        doc.recompute()
    view = Gui.activeDocument().ActiveView
    view.viewIsometric()
    view.fitAll()
    state["doc"] = doc
    state["box"] = box
    inside = any(
        "WindowContainer" in w.metaObject().className()
        for w in Gui.getMainWindow().findChildren(QtWidgets.QWidget)
    )
    state["rect"], state["dpr"] = viewport_rect()
    emit("EDGEHL_OBJ mode=%s doc=%s object=%s edges=%s" % (
        MODE, DOC_PATH or "(box)", state["box"].Name,
        ",".join(str(i) for i in EDGE_IDS)))
    emit("EDGEHL_VIEW mode=%s rect=%d,%d,%d,%d dpr=%.2f vulkan_widget=%d" % (
        MODE, state["rect"][0], state["rect"][1], state["rect"][2], state["rect"][3],
        state["dpr"], 1 if inside else 0))


def refresh():
    Gui.updateGui()
    s.vulkan_render()


def clear_dumps():
    for f in glob.glob("/tmp/vk_frame_*.png"):
        try:
            os.remove(f)
        except OSError:
            pass


def apply(action):
    if MODE == "vulkan":
        clear_dumps()
    Gui.Selection.clearSelection()
    if action is None:
        pass
    elif action[0] == "sel":
        Gui.Selection.addSelection(state["doc"].Name, state["box"].Name, action[1])
    elif action[0] == "pre":
        Gui.Selection.setPreselection(state["box"], action[1])
    refresh()


def grab(case):
    path = os.path.join(OUT, "%s_%s.png" % (MODE, case))
    if MODE == "vulkan":
        # The native Vulkan child window cannot be grabbed with QWidget/QScreen
        # grabs (they return the stale GL widget or a partly unpainted area), so
        # use the presented-frame dump written by the debug hook
        # (FC_VULKAN_DUMP_FRAME, FREECAD_USE_VULKAN_DEBUG_HOOKS build).
        frames = sorted(glob.glob("/tmp/vk_frame_*.png"), key=os.path.getmtime)
        if not frames:
            emit("EDGEHL_WARN mode=%s case=%s no_frame_dump" % (MODE, case))
            return
        shutil.copy(frames[-1], path)
    else:
        rect, dpr = viewport_rect()
        state["rect"], state["dpr"] = rect, dpr
        screen = QtWidgets.QApplication.instance().primaryScreen()
        pix = screen.grabWindow(0)
        x, y, w, h = rect
        crop = QtCore.QRect(int(x * dpr), int(y * dpr), int(w * dpr), int(h * dpr))
        if crop.width() > 0 and crop.height() > 0:
            pix = pix.copy(crop)
        pix.save(path, "PNG")
    emit("EDGEHL_CASE mode=%s case=%s file=%s" % (MODE, case, path))


def step():
    try:
        _step()
    except Exception as exc:  # never leave the harness waiting on a dead probe
        import traceback
        emit("EDGEHL_ERROR mode=%s exc=%s" % (MODE, exc))
        traceback.print_exc()
        s.finish()
        Gui.getMainWindow().close()


def _step():
    if not state["ready"]:
        setup()
        state["ready"] = True
        QtCore.QTimer.singleShot(800, step)
        return

    if not state["fitted"]:
        # The first fitAll() can run before the widget has its final size; fit
        # again now that the window is shown and laid out, so GL and Vulkan see
        # the same camera and the whole box is inside the captured view.
        view = Gui.activeDocument().ActiveView
        view.viewIsometric()
        view.fitAll()
        refresh()
        state["fitted"] = True
        QtCore.QTimer.singleShot(800, step)
        return

    if state["pending"] is not None:
        if state["settle"] > 0:
            state["settle"] -= 1
            refresh()
            QtCore.QTimer.singleShot(350, step)
            return
        grab(state["pending"])
        state["pending"] = None
        QtCore.QTimer.singleShot(150, step)
        return

    if state["idx"] >= len(PLAN):
        emit("EDGEHL_DONE mode=%s cases=%d" % (MODE, len(PLAN)))
        s.finish()
        Gui.getMainWindow().close()
        return

    case, action = PLAN[state["idx"]]
    state["idx"] += 1
    apply(action)
    state["pending"] = case
    state["settle"] = 3
    QtCore.QTimer.singleShot(350, step)


QtCore.QTimer.singleShot(1500, step)
