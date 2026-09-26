#!/usr/bin/env python3
"""Verify the Vulkan/IR navigation cube is drawn and interactive.

The fork re-implements the nav cube for the Vulkan retained-render pipeline in
``SoNaviCubeVulkan`` (the upstream ``SoNaviCube`` is a pure OpenGL node).  This
probe exercises the *live* view:

  1. control: with the nav cube disabled, a click sweep over all four viewport
     corners must NOT change the camera (so an unrelated navigation path can't
     satisfy the test);
  2. nav cube: with it enabled (the default), the same sweep must change the
     camera orientation/position at some point -- i.e. clicking the Vulkan nav
     cube actually performs the standard-view navigation.

The per-click outcome is emitted as
``[HARNESS] navicube phase=<control|cube> changed=<0|1> x=.. y=..`` so the host
check can assert the signal independently of the in-probe verdict.

Run:
  FC_VULKAN_BREADCRUMBS=1 python3 tools/fcprobe/freecad_probe.py run \\
      tools/fcprobe/vk_navicube_probe.py --profile vulkan
"""

import os
import sys

import FreeCAD
import FreeCADGui
from PySide import QtCore

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from freecad_probe import Session  # noqa: E402

VIEW = "User parameter:BaseApp/Preferences/View"
# The nav cube is 132 logical px (NaviCube::getNaviCubeSize / CubeSize default);
# it sits ~0.55*size from its corner, so a 170 px square covers it on all sides.
SPAN = 170
INSET = 10
GRID = 4


def log(msg):
    print("NAVICUBE " + msg, flush=True)


def settle(ms):
    timer = QtCore.QElapsedTimer()
    timer.start()
    while timer.elapsed() < ms:
        QtCore.QCoreApplication.processEvents()
        QtCore.QThread.msleep(10)


def cam_state(view):
    rot = (0.0, 0.0, 0.0, 1.0)
    pos = (0.0, 0.0, 0.0)
    try:
        rot = tuple(view.getCameraOrientation().getValue())
    except Exception:
        pass
    try:
        pos = tuple(view.getCameraNode().position.getValue())
    except Exception:
        pass
    return rot, pos


def cam_changed(a, b):
    if any(abs(x - y) > 1e-5 for x, y in zip(a[0], b[0])):
        return True
    if any(abs(x - y) > 1e-6 for x, y in zip(a[1], b[1])):
        return True
    return False


def corner_points(w, h):
    """4x4 grid inside each viewport corner square (logical container px),
    top-right first (the default NaviCube corner)."""
    step = (SPAN - 2 * INSET) / (GRID - 1)
    x_lo = [INSET + i * step for i in range(GRID)]
    x_hi = [w - INSET - i * step for i in range(GRID)]
    y_lo = [INSET + i * step for i in range(GRID)]
    y_hi = [h - INSET - i * step for i in range(GRID)]
    for (xs, ys) in ((x_hi, y_lo), (x_lo, y_lo), (x_lo, y_hi), (x_hi, y_hi)):
        for y in ys:
            for x in xs:
                yield x, y


s = Session(name="navicube")
steps = [0]
view = [None]
result = {"control": False, "cube": False}


def build_scene():
    FreeCADGui.activateWorkbench("PartWorkbench")
    doc = FreeCAD.newDocument("NaviCube")
    box = doc.addObject("Part::Box", "Box")
    box.Length = box.Width = box.Height = 10
    doc.recompute()
    v = FreeCADGui.ActiveDocument.ActiveView
    v.viewIsometric()
    v.fitAll()
    return v


def sweep(phase):
    v = view[0]
    before = cam_state(v)
    for x, y in corner_points(s.width, s.height):
        s.click(x, y)
        settle(160)
        after = cam_state(v)
        hit = cam_changed(before, after)
        s.emit("navicube", phase=phase, changed=(1 if hit else 0),
               x=int(x), y=int(y))
        if hit:
            log("phase=%s NAVIGATED at (%d,%d)" % (phase, x, y))
            return True
    log("phase=%s no navigation" % phase)
    return False


def step():
    steps[0] += 1
    k = steps[0]
    if k == 1:
        for name in list(FreeCAD.listDocuments()):
            FreeCAD.closeDocument(name)
        s.set_pref(VIEW, "UseVulkanRenderer", True)
        view[0] = build_scene()
        s.frame_phase("built")
    elif k == 3:
        # -- control: nav cube off --
        view[0].getViewer().setEnabledNaviCube(False)
        s.frame_phase("control")
        settle(400)
        result["control"] = sweep("control")
    elif k == 4:
        # -- nav cube on (default) --
        view[0].getViewer().setEnabledNaviCube(True)
        s.frame_phase("cube")
        settle(400)
        result["cube"] = sweep("cube")
    elif k == 5:
        s.expect("nav cube off: clicks do not navigate the camera",
                 not result["control"], "changed=%s" % result["control"])
        s.expect("nav cube on: a corner click navigates the camera",
                 result["cube"], "changed=%s" % result["cube"])
        s.snapshot()
        s.finish()
        FreeCADGui.getMainWindow().close()
        return
    QtCore.QTimer.singleShot(400, step)


QtCore.QTimer.singleShot(500, step)
