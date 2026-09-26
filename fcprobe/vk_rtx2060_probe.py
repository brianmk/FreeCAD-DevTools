#!/usr/bin/env python3
"""Simulated NVIDIA RTX 2060 (Turing) capability test.

Runs the path tracer under the ``rtx-2060`` device profile, which hides the
Ada/Blackwell-era optional extensions (VK_EXT_opacity_micromap,
VK_NV_cluster/partitioned acceleration structures, VK_NV_ray_tracing_linear_
swept_spheres) so the device looks like a lower-tier RTX 20-series part while
still advertising ray tracing.

The probe opens in raster, switches to PathTracing (lazy RTX bring-up, which
emits the ``[RTDBG] caps`` self-probe), lets it accumulate, and dumps frames.
The host check asserts ray tracing still initialized and path-traced, and that
the four post-Turing caps read 0 -- i.e. the renderer degrades gracefully on a
2060-class device instead of assuming Ada/Blackwell features.

Run:
  python3 tools/fcprobe/freecad_probe.py run tools/fcprobe/vk_rtx2060_probe.py \\
      --profile vulkan --device-profile rtx-2060 \\
      --env FC_VULKAN_RT_DEBUG=1 \\
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
    print("RTX2060 " + msg, flush=True)


s = Session(name="rtx-2060")
steps = [0]


def build_scene():
    FreeCADGui.activateWorkbench("PartWorkbench")
    doc = FreeCAD.newDocument("Rtx2060")
    box = doc.addObject("Part::Box", "Box")
    box.Length = box.Width = box.Height = 10
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
        # Vulkan raster first, so the RTX backend (and its caps probe) is
        # brought up lazily at the mode switch below.
        s.set_pref(VIEW, "UseVulkanRenderer", True)
        s.set_pref(VIEW, "VulkanRenderMode", 1)  # RasterVulkan
        s.set_pref(VIEW, "VulkanPathTracingBounces", 3)
        s.set_pref(VIEW, "VulkanPathTracingSettle", 2)
        s.set_pref(VIEW, "VulkanPathTracingMaxSamples", 64)
        build_scene()
        s.frame_phase("raster-open")
        log("phase=raster-open")
    elif k == 4:
        # Lazy RTX bring-up + the caps self-probe.
        s.set_pref(VIEW, "VulkanRenderMode", 4)  # PathTracing
        s.frame_phase("pt-on")
        log("phase=pt-on")
    elif k in (7, 10, 13):
        s.frame_phase("pt-settle-%d" % k)
        log("phase=pt-settle %d" % k)
    elif k == 16:
        s.snapshot()
        s.finish()
        FreeCADGui.getMainWindow().close()
        return
    QtCore.QTimer.singleShot(700, step)


QtCore.QTimer.singleShot(500, step)
