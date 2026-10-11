#!/usr/bin/env python3
"""Interaction-LOD vs. the Sketcher grid's division ("bold") lines.

Reported symptom (RasterVulkan only): while the pointer keeps moving -- and
also while the camera is being navigated -- the Sketcher grid's every-nth
division lines lose their extra width; they come back once the viewport goes
idle.  Only the division lines are affected; the 1px subdivision lines stay.

The grid is built by PartGui::ViewProviderGridExtension: subdivision lines with
GridLineWidth (1) and division lines with GridDivLineWidth (2).  A width > 1
line is drawn through the Vulkan wide-line path, whose `isWideLine()` predicate
downgrades it to a plain 1px line while the backend's interaction LOD is
latched.  This probe drives both frame producers (hover input and camera
motion) and records which frames are rendered in which state.

Phases (each emits a [HARNESS] grid record + saves viewport captures):
  idle          viewport settled, nothing moving
  hover_vertex  pointer parked on a shared vertex, fresh move each tick
  hover_edge    pointer alternating vertex <-> edge
  hover_stop    no input for a while
  camera_move   camera nudged every tick (the interaction-LOD path)
  camera_stop   camera left alone

Captures are attempted with three backends because which one shows the Vulkan
swapchain depends on the platform plugin: the viewport widget grab, a screen
grab cropped to the main window, and view.saveImage() (the Coin offscreen
render, i.e. the GL reference).

Run (from the workspace):

  cd /home/phantom/dev/FreeCAD-Integrate
  HOME=<private> QT_QPA_PLATFORM=<wayland|xcb> \
  FREECAD_DEVTOOLS=<DevTools root> \
  build-freecad/bin/FreeCAD .scratch/grid/vk_grid_lod_probe.py
"""

import os
import sys
import time

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtGui

DEVTOOLS = os.environ.get(
    "FREECAD_DEVTOOLS", "/home/phantom/dev/FreeCAD-DevTools")
sys.path.insert(0, os.path.join(DEVTOOLS, "fcprobe"))
from freecad_probe import Session  # noqa: E402

try:
    from pivy import coin
except Exception:  # pragma: no cover - pivy is present in the FreeCAD build
    coin = None

VIEW = "User parameter:BaseApp/Preferences/View"
SKETCHER = "User parameter:BaseApp/Preferences/Mod/Sketcher/General"
OUTDIR = os.environ.get("FC_GRID_OUT", "/tmp/opencode/gridlod")

s = Session(name="grid_lod")
steps = [0]


def log(msg):
    sys.stderr.write("GRID %s\n" % msg)
    sys.stderr.flush()


def world_to_screen(view, wx, wy, wz):
    """World -> normalized viewport coordinates."""
    cam = view.getCameraNode()
    vv = cam.getViewVolume()
    pr = vv.projectToScreen(coin.SbVec3f(wx, wy, wz))
    return pr[0], pr[1]


def grab_container(phase):
    s._relocate_viewport()
    if s.container is None:
        return None
    path = os.path.join(OUTDIR, "%s_widget.png" % phase)
    s.container.grab().save(path)
    return path


def grab_screen(phase):
    win = FreeCADGui.getMainWindow()
    scr = QtGui.QGuiApplication.primaryScreen()
    geo = win.frameGeometry()
    pm = scr.grabWindow(0, geo.x(), geo.y(), geo.width(), geo.height())
    path = os.path.join(OUTDIR, "%s_screen.png" % phase)
    pm.save(path)
    return path


def grab_saveimage(phase):
    # Offscreen Coin/GL render (saveImage): a *GL* reference image, not the
    # Vulkan swapchain.  It also forces a GL render, whose auto-clipping
    # rewrites the camera's near/far and therefore perturbs the very state
    # under test, so it is opt-in only.
    if os.environ.get("FC_GRID_GL_CAPTURE") != "1":
        return None
    view = FreeCADGui.ActiveDocument.ActiveView
    path = os.path.join(OUTDIR, "%s_saveimage.png" % phase)
    view.saveImage(path, 1200, 900, "Current")
    return path


def mark(phase, note="", **fields):
    """Emit the end-of-phase marker the host checker attributes draws to.

    The marker is written *after* the phase has run, so every record since the
    previous marker belongs to this phase.
    """
    frame = 0
    try:
        frame = int(FreeCADGui.ActiveDocument.ActiveView.getVulkanFrameCount())
    except Exception:
        pass
    s.emit("grid", phase=phase, frame=frame, note=note, **fields)
    sys.stderr.write("GRID phase=%s frame=%d note=%s\n" % (phase, frame, note))
    sys.stderr.flush()
    return frame


def capture(phase, note=""):
    os.makedirs(OUTDIR, exist_ok=True)
    results = {}
    for name, fn in (("widget", grab_container), ("screen", grab_screen),
                     ("saveimage", grab_saveimage)):
        try:
            results[name] = fn(phase)
        except Exception as exc:
            results[name] = "ERR %s" % exc
    frame = mark(phase, note, **{("img_" + k): v for k, v in results.items()})
    log("phase=%s frame=%d %s" % (phase, frame, results))


def make_sketch():
    for name in list(FreeCAD.listDocuments()):
        FreeCAD.closeDocument(name)
    # Grid prefs before the Sketch ViewProvider is created: the observer reads
    # them at init.  Explicit values so the probe does not depend on whatever
    # the developer last configured.
    s.set_pref(SKETCHER, "GridLineWidth", 1, emit=False)
    s.set_pref(SKETCHER, "GridDivLineWidth", 2, emit=False)
    s.set_pref(SKETCHER, "GridNumberSubdivision", 10, emit=False)
    s.set_pref(SKETCHER, "GridLinePattern", 0xFFFF, emit=False)
    s.set_pref(SKETCHER, "GridDivLinePattern", 0xFFFF, emit=False)
    s.set_pref(SKETCHER, "GridSizePixelThreshold", 15, emit=False)
    FreeCADGui.activateWorkbench("SketcherWorkbench")
    doc = FreeCAD.newDocument("GridLod")
    import Part

    sk = doc.addObject("Sketcher::SketchObject", "Sketch")
    sk.addGeometry(
        Part.LineSegment(FreeCAD.Vector(-20, 0, 0), FreeCAD.Vector(20, 0, 0)),
        False)
    sk.addGeometry(
        Part.LineSegment(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 20, 0)),
        False)
    doc.recompute()
    FreeCADGui.ActiveDocument.setEdit(sk.Name)
    view = FreeCADGui.ActiveDocument.ActiveView
    view.viewTop()
    view.fitAll()
    try:
        sk.ViewObject.ShowGrid = True
        sk.ViewObject.GridAuto = True
    except Exception as exc:
        log("ShowGrid/GridAuto set failed: %s" % exc)
    s.vulkan_render()
    s._relocate_viewport()
    log("viewport %dx%d dpr=%.2f grid=%s/%s/%s" % (
        s.width, s.height, s.dpr,
        getattr(sk.ViewObject, "ShowGrid", "?"),
        getattr(sk.ViewObject, "GridAuto", "?"),
        getattr(sk.ViewObject, "GridSize", "?")))
    # Hover targets: the shared vertex at the origin and the midpoint of the
    # horizontal edge.
    vx, vy = world_to_screen(view, 0.0, 0.0, 0.0)
    ex, ey = world_to_screen(view, 10.0, 0.0, 0.0)
    return (view,
            (int(vx * s.width), int((1.0 - vy) * s.height)),
            (int(ex * s.width), int((1.0 - ey) * s.height)))


def pump(seconds, force_camera=False):
    deadline = time.monotonic() + seconds
    i = 0
    view = FreeCADGui.ActiveDocument.ActiveView
    cam = None
    if force_camera:
        try:
            cam = view.getCameraNode()
        except Exception:
            cam = None
    while time.monotonic() < deadline:
        if cam is not None:
            try:
                pos = cam.position.getValue()
                sign = 1.0 if (i % 2 == 0) else -1.0
                cam.position.setValue(pos[0] + 0.25 * sign, pos[1], pos[2])
            except Exception:
                pass
        QtGui.QGuiApplication.processEvents()
        time.sleep(0.02)
        i += 1


def step():
    steps[0] += 1
    k = steps[0]
    try:
        if k == 1:
            s.set_pref(VIEW, "UseVulkanRenderer", True)
            s.set_pref(VIEW, "VulkanRenderMode", 1)  # RasterVulkan
            s.set_pref(VIEW, "VulkanInteractionLod", True)
            s.set_pref(VIEW, "NavigationStyle", "Gui::CADNavigationStyle")
            step.view, step.vertex, step.edge = make_sketch()
            log("setup: vertex=%s edge=%s" % (step.vertex, step.edge))
            mark("setup")
        elif k == 3:
            pump(0.6)
            capture("idle")
        elif k == 4:
            # Park on the vertex, then keep issuing moves so frames keep coming.
            s.move(*step.vertex)
            deadline = time.monotonic() + 1.2
            i = 0
            while time.monotonic() < deadline:
                s.move(step.vertex[0] + (i % 3), step.vertex[1])
                QtGui.QGuiApplication.processEvents()
                time.sleep(0.04)
                i += 1
            capture("hover_vertex", note="moves=%d" % i)
        elif k == 5:
            # Vertex -> edge transitions: the reported second trigger.
            for i in range(12):
                s.move(*(step.vertex if i % 2 == 0 else step.edge))
                QtGui.QGuiApplication.processEvents()
                time.sleep(0.05)
            capture("hover_edge", note="vertex<->edge transitions")
        elif k == 6:
            pump(0.6)
            capture("hover_stop")
        elif k == 7:
            pump(1.2, force_camera=True)
            capture("camera_move")
        elif k == 8:
            pump(0.6)
            capture("camera_stop")
        elif k >= 10:
            mark("done")
            s.finish()
            s.close()
            return
    except Exception:
        import traceback

        traceback.print_exc()
        s.error("grid probe step %d failed", k)
        return
    QtCore.QTimer.singleShot(300, step)


QtCore.QTimer.singleShot(1500, step)
