#!/usr/bin/env python3
"""Ray-traced material base-colour texture sampling.

Authors a box whose material has a pure-green base-colour image and a red
diffuse colour, then renders it with the Vulkan path tracer.  If the RT backend
samples the embedded texture (sampler2DArray layer + per-triangle UV pool) the
visible surface reads green; if the texture is dropped it reads the red diffuse.
The host check analyses a dumped frame for the two colours.

Run:
  FC_VULKAN_DUMP_FRAME=1 FC_VULKAN_DUMP_START=0 FC_VULKAN_DUMP_END=400 \\
      python3 tools/fcprobe/freecad_probe.py run \\
      tools/fcprobe/vk_rt_texture_probe.py --profile vulkan
"""

import os
import sys

import FreeCAD
import FreeCADGui
from PySide import QtCore

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from freecad_probe import Session  # noqa: E402

VIEW = "User parameter:BaseApp/Preferences/View"

# 2x2 solid-green PNG -- distinct from the material's red diffuse so the
# rendered colour alone proves whether the texture was sampled.
GREEN_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAE0lEQVR4nGNk+M/AwMDABCIYGAAMHgED"
    "rNiLpwAAAABJRU5ErkJggg=="
)

# 2x2 flat normal map (128,128,255) = tangent-space +Z, i.e. no perturbation.
FLAT_NORMAL_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEklEQVR4nGNsaPjPwMDAxAAGABefAgM4"
    "5HnVAAAAAElFTkSuQmCC"
)


def log(msg):
    print("RTTEX " + msg, flush=True)


s = Session(name="rt-texture")
steps = [0]


def build_scene():
    FreeCADGui.activateWorkbench("PartWorkbench")
    doc = FreeCAD.newDocument("RtTexture")
    box = doc.addObject("Part::Box", "Box")
    box.Label = "TexBox"
    box.Length = 20
    box.Width = 20
    box.Height = 20

    mat = FreeCAD.Material()
    mat.AmbientColor = (0.0, 0.0, 0.0)
    mat.DiffuseColor = (0.9, 0.05, 0.05)  # red
    mat.SpecularColor = (0.1, 0.1, 0.1)
    mat.Shininess = 0.2
    mat.Image = GREEN_PNG
    # Also author the roughness and normal maps so all four texture channels
    # (base, roughness, normal, emissive) resolve through the shared
    # sampler2DArray.  Zero strength disables their effect; the normal map must
    # be a flat (0,0,1) map so that even with the normal-map path active a
    # strength of 0 leaves the geometric normal unchanged.
    mat.RoughnessImage = GREEN_PNG
    mat.NormalImage = FLAT_NORMAL_PNG
    mat.RoughnessStrength = 0.0
    mat.NormalStrength = 0.0
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
        s.set_pref(VIEW, "VulkanRenderMode", 1)  # raster gate first
        build_scene()
        s.frame_phase("raster-open")
        log("phase=raster-open")
    elif k == 4:
        log("phase=pt-on")
        s.set_pref(VIEW, "VulkanRenderMode", 4)  # path tracing
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
