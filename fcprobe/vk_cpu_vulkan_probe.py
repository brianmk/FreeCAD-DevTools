#!/usr/bin/env python3
"""CPU-only render probe: the fork's Vulkan viewport on a software device.

Run under the ``cpu-xcb`` profile, which points ``VK_ICD_FILENAMES`` at Mesa's
lavapipe ICD (a ``VK_PHYSICAL_DEVICE_TYPE_CPU`` device) and forces software GL,
so no GPU is touched.  Software Vulkan has no Wayland WSI in the lavapipe
build, so the run uses xcb/XWayland.

The probe enables the Vulkan renderer in raster mode and renders a box.  The
host check asserts the SELECTED device is a CPU device (``[VK-DEVICE] ...
type=4``) and that a real frame was dumped -- i.e. the fork rendered with no
GPU.

Run:
  python3 tools/fcprobe/freecad_probe.py run \\
      tools/fcprobe/vk_cpu_vulkan_probe.py --profile cpu-xcb \\
      --env FC_VULKAN_BREADCRUMBS=1 \\
      --env FC_VULKAN_DUMP_FRAME=1 --env FC_VULKAN_DUMP_START=0 \\
      --env FC_VULKAN_DUMP_END=400
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
    print("CPU-VULKAN " + msg, flush=True)


s = Session(name="cpu-vulkan")
steps = [0]


def build_scene():
    FreeCADGui.activateWorkbench("PartWorkbench")
    doc = FreeCAD.newDocument("CpuVulkan")
    box = doc.addObject("Part::Box", "Box")
    box.Length = box.Width = box.Height = 10
    doc.recompute()
    view = FreeCADGui.ActiveDocument.ActiveView
    view.viewIsometric()
    view.fitAll()


def step():
    steps[0] += 1
    k = steps[0]
    if k == 1:
        for name in list(FreeCAD.listDocuments()):
            FreeCAD.closeDocument(name)
        # The view reads these at creation; enable Vulkan raster before the doc.
        s.set_pref(VIEW, "UseVulkanRenderer", True)
        s.set_pref(VIEW, "VulkanRenderMode", 1)  # RasterVulkan
        build_scene()
        s.frame_phase("cpu-vulkan")
        log("built; rendering on the software Vulkan device")
    elif k == 8:
        s.snapshot()
        s.finish()
        FreeCADGui.getMainWindow().close()
        return
    # Keep the demand-driven widget presenting so frames are dumped.
    s.vulkan_render()
    QtCore.QTimer.singleShot(300, step)


QtCore.QTimer.singleShot(500, step)
