#!/usr/bin/env python3
"""Verify the Vulkan present-mode (V-Sync) preference is read and applied.

The ``VulkanPresentMode`` View pref (0 FIFO, 1 Mailbox, 2 Immediate) is a
window/swapchain property: ``VulkanViewportAdapter`` reads it when the view is
created and pushes it to ``QuarterVulkanWidget``, whose renderer resolves it
against the surface's advertised modes in ``preInitResources()`` (falling back
to FIFO when the request is unsupported).

That resolution is only logged through ``Base::Console().log`` (which the
harness cannot capture), so the renderer also emits a breadcrumb:

    [VK-PRESENT] requested=<N> using=<fifo|mailbox|immediate>

The probe sets the pref BEFORE the document (and therefore the 3D view) exists,
renders a box, and the host check asserts the breadcrumb matches the requested
mode -- or a FIFO fallback, which is a valid outcome on a surface that does not
advertise mailbox/immediate.

The requested mode comes from ``FC_TEST_PRESENT_MODE``.  The suite has one case
per mode (present-fifo / present-mailbox / present-immediate).

Run one mode:
  FC_TEST_PRESENT_MODE=1 python3 tools/fcprobe/freecad_probe.py run \\
      tools/fcprobe/vk_present_probe.py --profile vulkan \\
      --env FC_VULKAN_BREADCRUMBS=1
"""

import os
import sys

import FreeCAD
import FreeCADGui
from PySide import QtCore

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from freecad_probe import Session  # noqa: E402

VIEW = "User parameter:BaseApp/Preferences/View"
MODE = int(os.environ.get("FC_TEST_PRESENT_MODE", "0"))


def log(msg):
    print("PRESENT mode=%d %s" % (MODE, msg), flush=True)


s = Session(name="present-%d" % MODE)
steps = [0]

# Present mode persists in the real user config; save and restore it so a suite
# run does not leave every later run on Mailbox/Immediate.
_PRIOR = FreeCAD.ParamGet(VIEW).GetInt("VulkanPresentMode", 0)


def restore_pref():
    s.set_pref(VIEW, "VulkanPresentMode", _PRIOR)


def build_scene():
    FreeCADGui.activateWorkbench("PartWorkbench")
    doc = FreeCAD.newDocument("Present")
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
        # Both prefs are read when the view is constructed, so set them before
        # the document creates it.
        s.set_pref(VIEW, "UseVulkanRenderer", True)
        s.set_pref(VIEW, "VulkanPresentMode", MODE)
        build_scene()
        s.frame_phase("built")
        log("built; requested present mode")
    elif k == 5:
        s.snapshot()
        restore_pref()
        s.finish()
        FreeCADGui.getMainWindow().close()
        return
    # Keep the demand-driven widget presenting so the breadcrumb (emitted on
    # first expose) definitely lands and the run records a drawlist.
    s.vulkan_render()
    QtCore.QTimer.singleShot(350, step)


QtCore.QTimer.singleShot(500, step)
