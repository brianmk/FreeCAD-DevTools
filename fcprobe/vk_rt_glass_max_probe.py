#!/usr/bin/env python3
"""Dielectric-glass (Path Tracing Max) material-optics test.

Scene: a gray floor, a red backdrop, and a translucent cyan cube.  The cube is
rendered first in thin-glass mode (VulkanRenderMode 4) and then in Path
Tracing Max (mode 6), whose dielectric BSDF refracts and Beer-Lambert tints
the transmitted light using the per-material optics carried by
SoRenderIR::SoMaterialBlock::optical.

If the dielectric path is wired to the material record the two frames differ
(refraction + tint change the transmitted image); if the optical slot were lost
(IOR clamped to 1, no absorption) mode 6 would degenerate to a flat transparent
pane and read like thin glass.

Run:
  FC_VULKAN_RT_DEBUG=1 FC_VULKAN_DUMP_FRAME=1 FC_VULKAN_DUMP_START=0 \\
      FC_VULKAN_DUMP_END=400 python3 tools/fcprobe/freecad_probe.py run \\
      tools/fcprobe/vk_rt_glass_max_probe.py --profile vulkan
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
    print("GLASSMAX " + msg, flush=True)


s = Session(name="rt-glass-max")
steps = [0]


def build():
    for name in list(FreeCAD.listDocuments()):
        FreeCAD.closeDocument(name)
    doc = FreeCAD.newDocument("GlassMax")

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

    cube = doc.addObject("Part::Box", "Glass")
    cube.Length = 3
    cube.Width = 3
    cube.Height = 3
    cube.Placement.Base = FreeCAD.Vector(0, 0, 3)
    cm = FreeCAD.Material()
    cm.AmbientColor = (0.0, 0.0, 0.0)
    cm.DiffuseColor = (0.4, 0.7, 0.9)  # cyan -> Beer-Lambert tint
    cm.SpecularColor = (0.2, 0.2, 0.2)
    cm.Shininess = 0.4
    cube.ViewObject.ShapeAppearance = cm
    cube.ViewObject.Transparency = 50
    doc.recompute()

    FreeCADGui.Selection.clearSelection()
    view = FreeCADGui.ActiveDocument.ActiveView
    view.setAnimationEnabled(False)
    view.viewIsometric()
    view.fitAll()
    return doc


def step():
    steps[0] += 1
    k = steps[0]
    if k == 1:
        for name in list(FreeCAD.listDocuments()):
            FreeCAD.closeDocument(name)
        s.set_pref(VIEW, "UseVulkanRenderer", True)
        s.set_pref(VIEW, "VulkanRenderMode", 4)
        s.set_pref(VIEW, "VulkanPathTracingBounces", 3)
        s.set_pref(VIEW, "VulkanPathTracingSettle", 4)
        FreeCADGui.activateWorkbench("PartWorkbench")
        build()
        log("phase=thin-glass")
    elif k == 6:
        s.frame_phase("thin-glass")
        log("phase=thin-glass settled")
    elif k == 8:
        s.set_pref(VIEW, "VulkanRenderMode", 6)
        log("phase=dielectric-glass")
    elif k == 14:
        s.frame_phase("dielectric-glass")
        log("phase=dielectric-glass settled")
    elif k == 16:
        log("snapshot + finish")
        s.snapshot()
        s.finish()
        FreeCADGui.getMainWindow().close()
        return
    QtCore.QTimer.singleShot(700, step)


QtCore.QTimer.singleShot(500, step)
