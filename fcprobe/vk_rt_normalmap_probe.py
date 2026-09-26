#!/usr/bin/env python3
"""Ray-traced normal-map sampling.

Two identical green-textured boxes sit side by side under the ray tracer.  The
left box carries a flat normal map (128,128,255) and the right box a strongly
tangent-tilted one (255,128,180).  A headlight shades them, so if the RT
backend samples the normal map the right box's top face darkens while the left
stays bright; if normal mapping is ignored both halves read identically.

Run:
  FC_VULKAN_DUMP_FRAME=1 python3 tools/fcprobe/freecad_probe.py run \\
      tools/fcprobe/vk_rt_normalmap_probe.py --profile vulkan
"""

import os
import sys

import FreeCAD
import FreeCADGui
from PySide import QtCore

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from freecad_probe import Session  # noqa: E402

VIEW = "User parameter:BaseApp/Preferences/View"

GREEN_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAE0lEQVR4nGNk+M/AwMDABCIYGAAMHgED"
    "rNiLpwAAAABJRU5ErkJggg=="
)
FLAT_NORMAL_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEklEQVR4nGNsaPjPwMDAxAAGABefAgM4"
    "5HnVAAAAAElFTkSuQmCC"
)
TILT_NORMAL_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEklEQVR4nGP839DAwMDAxAAGABidAgO/"
    "Z9RmAAAAAElFTkSuQmCC"
)


def log(msg):
    print("RTNORM " + msg, flush=True)


s = Session(name="rt-normalmap")
steps = [0]


def _material(normal_png, strength):
    mat = FreeCAD.Material()
    mat.AmbientColor = (0.0, 0.0, 0.0)
    mat.DiffuseColor = (1.0, 1.0, 1.0)
    mat.SpecularColor = (0.0, 0.0, 0.0)
    mat.Shininess = 0.0
    mat.Image = GREEN_PNG
    mat.NormalImage = normal_png
    mat.NormalStrength = strength
    return mat


def build_scene():
    FreeCADGui.activateWorkbench("PartWorkbench")
    doc = FreeCAD.newDocument("RtNormalMap")

    left = doc.addObject("Part::Box", "Left")
    left.Label = "LeftFlat"
    left.Length = 20
    left.Width = 20
    left.Height = 20
    left.Placement.Base = FreeCAD.Vector(-12, 0, 0)
    left.ViewObject.ShapeAppearance = [_material(FLAT_NORMAL_PNG, 1.0)]

    right = doc.addObject("Part::Box", "Right")
    right.Label = "RightTilt"
    right.Length = 20
    right.Width = 20
    right.Height = 20
    right.Placement.Base = FreeCAD.Vector(12, 0, 0)
    right.ViewObject.ShapeAppearance = [_material(TILT_NORMAL_PNG, 1.0)]

    doc.recompute()

    view = FreeCADGui.ActiveDocument.ActiveView
    view.viewTop()
    view.fitAll()
    return left, right


def step():
    steps[0] += 1
    k = steps[0]
    if k == 1:
        for name in list(FreeCAD.listDocuments()):
            FreeCAD.closeDocument(name)
        s.set_pref(VIEW, "VulkanRenderMode", 1)
        build_scene()
        s.frame_phase("raster-open")
        log("phase=raster-open")
    elif k == 4:
        log("phase=pt-on")
        s.set_pref(VIEW, "VulkanRenderMode", 4)
        s.frame_phase("pt-on")
    elif k in (7, 10, 13):
        log("phase=pt-settle %d" % k)
        s.frame_phase("pt-settle-%d" % k)
    elif k == 16:
        log("snapshot + finish")
        s.snapshot()
        s.finish()
        FreeCADGui.getMainWindow().close()
        return
    QtCore.QTimer.singleShot(700, step)


QtCore.QTimer.singleShot(500, step)
