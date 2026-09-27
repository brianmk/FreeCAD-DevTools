#!/usr/bin/env python3
"""Metalness/roughness sweep for the physical (PBR) material, raster Vulkan.

Builds a white metal sphere and sweeps roughness over a fixed list.  Under the
viewport headlight a smooth (low-roughness) metal shows a tight, saturated
specular highlight; as roughness rises the lobe spreads and dims, so the count
of near-saturated pixels falls.  Each phase is marked with frame_phase() and
the host check analyses the dumped frames (FC_VULKAN_DUMP_FRAME=1, provided by
the suite entry) asserting the count falls monotonically with roughness.

Run:
  FC_VULKAN_DUMP_FRAME=1 FC_VULKAN_DUMP_START=0 FC_VULKAN_DUMP_END=400 \\
  python3 tools/fcprobe/freecad_probe.py run \\
      tools/fcprobe/vk_physical_material_probe.py --profile vulkan
"""

import os
import sys

import FreeCAD
import FreeCADGui
from PySide import QtCore

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from freecad_probe import Session  # noqa: E402

VIEW = "User parameter:BaseApp/Preferences/View"

# Ascending metalness at a fixed roughness: metal reflectance rises, so the
# specular highlight must brighten/spread monotonically.
METALNESS = [0.0, 0.25, 0.5, 0.75, 1.0]
ROUGHNESS = 0.3


def log(msg):
    print("PHYSMAT " + msg, file=sys.stderr)


s = Session(name="physical-material")
steps = [0]
index = [0]


def build():
    for name in list(FreeCAD.listDocuments()):
        FreeCAD.closeDocument(name)
    doc = FreeCAD.newDocument("PhysicalMaterial")

    # A sphere viewed from the standard isometric: the viewport headlight
    # always produces a visible specular highlight, whose strength tracks the
    # metalness.
    sphere = doc.addObject("Part::Sphere", "Sphere")
    sphere.Radius = 10
    apply_metalness(sphere, METALNESS[0])
    doc.recompute()

    FreeCADGui.Selection.clearSelection()
    view = FreeCADGui.ActiveDocument.ActiveView
    view.setAnimationEnabled(False)
    view.viewIsometric()
    view.fitAll()
    return doc


def apply_metalness(obj, metalness):
    mat = FreeCAD.Material()
    mat.AmbientColor = (0.0, 0.0, 0.0)
    mat.DiffuseColor = (0.9, 0.9, 0.9)
    mat.SpecularColor = (1.0, 1.0, 1.0)
    mat.Shininess = 1.0
    mat.UsePhysicalMaterial = True
    mat.Metallic = metalness
    mat.Roughness = ROUGHNESS
    obj.ViewObject.ShapeAppearance = mat


def step():
    steps[0] += 1
    k = steps[0]
    if k == 1:
        s.set_pref(VIEW, "UseVulkanRenderer", True)
        s.set_pref(VIEW, "VulkanRenderMode", 1)  # raster Vulkan
        # The suite runs this case after points/prefs, which leave the Vulkan
        # edge/points overlays ON in the shared user config.  A red overlay is
        # re-drawn over the fill geometry and covers the material, so reset
        # them: the metalness/roughness response must be measured on the lit
        # fill, not under an overlay.
        s.set_pref(VIEW, "VulkanEdgeOverlay", False)
        s.set_pref(VIEW, "VulkanShowPoints", False)
        FreeCADGui.activateWorkbench("PartWorkbench")
        build()
        log("built sphere")
        s.vulkan_render()
    elif k >= 3 and (k - 3) % 8 == 0:
        i = index[0]
        if i >= len(METALNESS):
            s.snapshot()
            s.finish()
            FreeCADGui.getMainWindow().close()
            return
        doc = FreeCAD.ActiveDocument
        sphere = doc.getObject("Sphere")
        metalness = METALNESS[i]
        apply_metalness(sphere, metalness)
        doc.recompute()
        s.vulkan_render()
        log("metalness=%.3f" % metalness)
        s.frame_phase("phys-m%.2f" % metalness)
        index[0] += 1
    QtCore.QTimer.singleShot(250, step)


QtCore.QTimer.singleShot(500, step)
