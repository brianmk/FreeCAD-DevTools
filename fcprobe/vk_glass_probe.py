#!/usr/bin/env python3
"""Decisive translucent-glass test for the RT path tracer.

Scene: a gray floor, a RED backdrop box far behind, and a cyan glass cube in
front (DiffuseColor (0.4,0.7,0.9)).  The cube is rendered first OPAQUE
(Transparency 0) and then TRANSLUCENT (Transparency 50).  If thin-glass
transmission works, the same centre pixels change from solid cyan toward a
red/cyan blend as the red backdrop shows through.

The host check compares the centre region of the two phases; a broken
transmission path leaves the two frames identical (or the cube opaque).

Run:
  FC_VULKAN_RT_DEBUG=1 FC_VULKAN_DUMP_FRAME=1 FC_VULKAN_DUMP_START=0 \\
      FC_VULKAN_DUMP_END=400 FreeCAD vk_glass_probe.py
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
    print("GLASS " + msg, flush=True)


s = Session(name="glass")
steps = [0]
cube = [None]


def build(transparency):
    for name in list(FreeCAD.listDocuments()):
        FreeCAD.closeDocument(name)
    doc = FreeCAD.newDocument("Glass")

    floor = doc.addObject("Part::Box", "Floor")
    floor.Length = 30
    floor.Width = 30
    floor.Height = 1
    fm = FreeCAD.Material()
    fm.AmbientColor = (0.0, 0.0, 0.0)
    fm.DiffuseColor = (0.5, 0.5, 0.5)
    fm.SpecularColor = (0.1, 0.1, 0.1)
    fm.Shininess = 0.1
    floor.ViewObject.ShapeAppearance = fm

    backdrop = doc.addObject("Part::Box", "Backdrop")
    backdrop.Length = 6
    backdrop.Width = 6
    backdrop.Height = 6
    backdrop.Placement.Base = FreeCAD.Vector(0, 12, 2)
    bm = FreeCAD.Material()
    bm.DiffuseColor = (0.8, 0.1, 0.1)  # red
    bm.AmbientColor = (0.0, 0.0, 0.0)
    backdrop.ViewObject.ShapeAppearance = bm

    box = doc.addObject("Part::Box", "Glass")
    box.Length = 3
    box.Width = 3
    box.Height = 3
    box.Placement.Base = FreeCAD.Vector(0, 0, 3)
    cm = FreeCAD.Material()
    cm.AmbientColor = (0.0, 0.0, 0.0)
    cm.DiffuseColor = (0.4, 0.7, 0.9)
    cm.SpecularColor = (0.2, 0.2, 0.2)
    cm.Shininess = 0.4
    box.ViewObject.ShapeAppearance = cm
    box.ViewObject.Transparency = transparency
    doc.recompute()

    FreeCADGui.Selection.clearSelection()
    view = FreeCADGui.ActiveDocument.ActiveView
    view.setAnimationEnabled(False)
    view.viewIsometric()
    view.fitAll()
    return box


def step():
    steps[0] += 1
    k = steps[0]
    if k == 1:
        s.set_pref(VIEW, "UseVulkanRenderer", True)
        s.set_pref(VIEW, "VulkanRenderMode", 4)
        s.set_pref(VIEW, "VulkanPathTracingBounces", 3)
        s.set_pref(VIEW, "VulkanPathTracingSettle", 4)
        FreeCADGui.activateWorkbench("PartWorkbench")
        cube[0] = build(0)  # opaque
        s.frame_phase("glass-opaque")
        log("phase=opaque (Transparency=0)")
    elif k == 12:
        # Same geometry/camera; only the opacity changes.
        cube[0].ViewObject.Transparency = 50
        cube[0].Document.recompute()
        s.frame_phase("glass-trans50")
        log("phase=transparent (Transparency=50)")
    elif k == 24:
        s.snapshot()
        s.finish()
        FreeCADGui.getMainWindow().close()
        return
    s.vulkan_render()
    QtCore.QTimer.singleShot(600, step)


QtCore.QTimer.singleShot(500, step)
