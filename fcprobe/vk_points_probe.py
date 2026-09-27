#!/usr/bin/env python3
"""Verify Vulkan point rendering (VulkanShowPoints overlay).

Renders a tessellated Part::Sphere in a raster Vulkan view so vertex points are
numerous, then toggles VulkanShowPoints on.  The VulkanEdgeColor is pinned to red
so the frame dump pixel counts are deterministic; the host-side check asserts the
applyVulkanSettings breadcrumb recorded the points=0->1 transition and that the
run produced frame dumps.

Usage:
  FC_VULKAN_DUMP_FRAME=1 FC_VULKAN_DUMP_START=0 FC_VULKAN_DUMP_END=400 \\
      FC_VULKAN_BACKEND_DEBUG=1 FreeCAD vk_points_probe.py
"""

import os
import sys

import FreeCAD
import FreeCADGui
from PySide import QtCore

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from freecad_probe import Session  # noqa: E402

VIEW = "User parameter:BaseApp/Preferences/View"


def log(msg):
    print("POINTS " + msg, flush=True)


def settle(ms):
    timer = QtCore.QElapsedTimer()
    timer.start()
    while timer.elapsed() < ms:
        QtCore.QCoreApplication.processEvents()
        QtCore.QThread.msleep(10)


s = Session(name="points")
steps = [0]


def build_scene():
    FreeCADGui.activateWorkbench("PartWorkbench")
    doc = FreeCAD.newDocument("Points")
    sphere = doc.addObject("Part::Sphere", "Sphere")
    sphere.Radius = 6
    doc.recompute()
    view = FreeCADGui.ActiveDocument.ActiveView
    view.viewTop()
    view.fitAll()


def step():
    steps[0] += 1
    k = steps[0]
    if k == 1:
        for name in list(FreeCAD.listDocuments()):
            FreeCAD.closeDocument(name)
        # Force raster mode (1): the point overlay is only drawn by the raster
        # backend, not the RTX path tracer.
        s.set_pref(VIEW, "VulkanRenderMode", 1)
        # Edges off in BOTH phases so only points contribute edge-colored
        # (red) pixels -> a clean baseline (0) vs points (>0) comparison.
        s.set_pref(VIEW, "VulkanEdgeOverlay", False)
        s.set_pref(VIEW, "VulkanShowPoints", False)
        s.set_pref(VIEW, "VulkanEdgeColor", 0xFF0000FF)
        build_scene()
        # Force actual frames: the viewport is demand-driven and the scene alone
        # does not guarantee a present before the dump window closes.
        settle(300)
        s.vulkan_render()
        settle(700)
        s.frame_phase("baseline")
        log("phase=baseline (points off)")
    elif k == 3:
        # The point overlay reaches the renderer asynchronously via the pref
        # observer.  Pump the loop first so the push is delivered, THEN force a
        # frame, so a dump actually captures points=1 (otherwise the phase
        # reuses the baseline frame and the host check sees no change).
        s.set_pref(VIEW, "VulkanShowPoints", True)
        settle(300)
        s.vulkan_render()
        settle(700)
        s.frame_phase("points")
        log("phase=points (VulkanShowPoints on)")
    elif k == 5:
        log("snapshot + finish")
        s.snapshot()
        s.finish()
        FreeCADGui.getMainWindow().close()
        return
    QtCore.QTimer.singleShot(650, step)


QtCore.QTimer.singleShot(500, step)
