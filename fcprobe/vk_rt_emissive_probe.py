#!/usr/bin/env python3
"""Ray-traced emissive-map sampling.

Authors a box with a black diffuse and a solid-red emissive image (emissive
intensity 1.0), then renders it with the Vulkan path tracer.  The only light
the surface can emit is the emissive map, so a red frame proves the RT backend
sampled the emissive map through the shared sampler2DArray.

Run:
  FC_VULKAN_DUMP_FRAME=1 python3 tools/fcprobe/freecad_probe.py run \\
      tools/fcprobe/vk_rt_emissive_probe.py --profile vulkan
"""

import os
import sys

import FreeCAD
import FreeCADGui
from PySide import QtCore

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from freecad_probe import Session  # noqa: E402

VIEW = "User parameter:BaseApp/Preferences/View"

# 2x2 solid-red PNG.
RED_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEklEQVR4nGO8IyfHwMDAxAAGAA4IARwN"
    "j/i7AAAAAElFTkSuQmCC"
)


def log(msg):
    print("RTEMI " + msg, flush=True)


s = Session(name="rt-emissive")
steps = [0]


def build_scene():
    FreeCADGui.activateWorkbench("PartWorkbench")
    doc = FreeCAD.newDocument("RtEmissive")
    box = doc.addObject("Part::Box", "Box")
    box.Label = "EmiBox"
    box.Length = 20
    box.Width = 20
    box.Height = 20

    mat = FreeCAD.Material()
    mat.AmbientColor = (0.0, 0.0, 0.0)
    mat.DiffuseColor = (0.0, 0.0, 0.0)  # black: no diffuse response
    mat.SpecularColor = (0.0, 0.0, 0.0)
    mat.Shininess = 0.0
    # A base image is required for the texture-coordinate graph to carry a
    # texgen function (an emissive-only material trips a Coin IR assertion), and
    # with a black diffuse it contributes nothing to the shaded colour.
    mat.Image = RED_PNG
    mat.EmissiveImage = RED_PNG
    mat.EmissiveIntensity = 1.0
    mat.UsePhysicalMaterial = True
    mat.Metallic = 0.0
    mat.Roughness = 1.0
    box.ViewObject.ShapeAppearance = [mat]
    doc.recompute()

    view = FreeCADGui.ActiveDocument.ActiveView
    view.viewTop()
    view.fitAll()
    return box


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
