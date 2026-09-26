#!/usr/bin/env python3
"""Per-material optics (IOR / Beer-Lambert absorption) acceptance test.

Exercises the global-override guard end-to-end: the same glass box is rendered
twice with only its authored optics changed (same geometry, camera, lights and
global viewer glass setting).  Replacing the viewer default with a distinct
index of refraction plus absorption must change the rendered pane; if the
consumer-side global glass setting clobbered the material's own values the two
phases would be pixel-identical.

  phase clear : TransmissionIor 1.1, TransmissionAbsorption 0.0
  phase tinted: TransmissionIor 2.0, TransmissionAbsorption 3.0

Each phase is marked with frame_phase() and the host check compares the dumped
frames (FC_VULKAN_DUMP_FRAME=1, provided by the suite entry).

Run:
  FC_VULKAN_DUMP_FRAME=1 FC_VULKAN_DUMP_START=0 FC_VULKAN_DUMP_END=400 \\
  python3 tools/fcprobe/freecad_probe.py run \\
      tools/fcprobe/vk_material_optics_probe.py --profile vulkan
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
    print("OPTICS " + msg, file=sys.stderr)


s = Session(name="material-optics")
steps = [0]


def build():
    for name in list(FreeCAD.listDocuments()):
        FreeCAD.closeDocument(name)
    doc = FreeCAD.newDocument("MaterialOptics")

    floor = doc.addObject("Part::Box", "Floor")
    floor.Length = 40
    floor.Width = 40
    floor.Height = 1
    fm = FreeCAD.Material()
    fm.AmbientColor = (0.0, 0.0, 0.0)
    fm.DiffuseColor = (0.5, 0.5, 0.5)
    fm.SpecularColor = (0.1, 0.1, 0.1)
    fm.Shininess = 0.1
    floor.ViewObject.ShapeAppearance = fm

    backdrop = doc.addObject("Part::Box", "Backdrop")
    backdrop.Length = 8
    backdrop.Width = 8
    backdrop.Height = 8
    backdrop.Placement.Base = FreeCAD.Vector(0, 14, 3)
    bm = FreeCAD.Material()
    bm.DiffuseColor = (0.8, 0.15, 0.1)  # red, visible through the glass
    bm.AmbientColor = (0.0, 0.0, 0.0)
    backdrop.ViewObject.ShapeAppearance = bm

    cube = doc.addObject("Part::Box", "Glass")
    cube.Length = 6
    cube.Width = 6
    cube.Height = 6
    cube.Placement.Base = FreeCAD.Vector(0, 0, 4)
    cube.ViewObject.Transparency = 40
    apply_optics(cube, 1.1, 0.0)
    doc.recompute()

    FreeCADGui.Selection.clearSelection()
    view = FreeCADGui.ActiveDocument.ActiveView
    view.setAnimationEnabled(False)
    view.viewIsometric()
    view.fitAll()
    return doc


def apply_optics(obj, ior, absorption):
    mat = FreeCAD.Material()
    mat.AmbientColor = (0.0, 0.0, 0.0)
    mat.DiffuseColor = (0.4, 0.7, 0.9)
    mat.SpecularColor = (0.2, 0.2, 0.2)
    mat.Shininess = 0.4
    mat.UsePhysicalMaterial = True
    mat.Metallic = 0.0
    mat.Roughness = 0.05
    mat.TransmissionIor = ior
    mat.TransmissionAbsorption = absorption
    obj.ViewObject.ShapeAppearance = mat


def measure(label, ior, absorption):
    doc = FreeCAD.ActiveDocument
    cube = doc.getObject("Glass")
    apply_optics(cube, ior, absorption)
    doc.recompute()
    s.vulkan_render()
    log("phase=%s ior=%.2f abso=%.2f" % (label, ior, absorption))
    s.frame_phase("optics-%s" % label)


def step():
    steps[0] += 1
    k = steps[0]
    if k == 1:
        s.set_pref(VIEW, "VulkanRenderMode", 4)  # PathTracing (+ dielectrics)
        s.set_pref(VIEW, "VulkanPathTracingBounces", 3)
        s.set_pref(VIEW, "VulkanPathTracingSettle", 4)
        FreeCADGui.activateWorkbench("PartWorkbench")
        build()
        log("built glass scene")
        s.vulkan_render()
    elif k == 20:
        measure("clear", 1.1, 0.0)
    elif k == 50:
        measure("tinted", 2.0, 3.0)
    elif k == 80:
        s.snapshot()
        s.finish()
        FreeCADGui.getMainWindow().close()
        return
    # The viewport is demand-driven and goes idle once converged, so pump a
    # frame every tick or the path tracer never accumulates.
    s.vulkan_render()
    QtCore.QTimer.singleShot(250, step)


QtCore.QTimer.singleShot(500, step)
