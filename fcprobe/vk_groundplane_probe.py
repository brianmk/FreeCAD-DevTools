#!/usr/bin/env python3
"""Verify the world-space ground-plane grid renders and is pref-driven.

``SoGroundPlane`` is a new fork node: an adaptive drafting grid on the world
Z = 0 plane, kept in the per-frame decoration scene so a camera-only frame
re-records it (important for the retained Vulkan draw list).  It is exposed by
``ShowGroundPlane`` / ``GroundPlaneOpacity`` and by ``View.setGroundPlane()``.

The probe renders a box on the ground, dumps a frame with the grid OFF, turns
``ShowGroundPlane`` on live (exercising the pref -> View3DSettings ->
setGroundPlane path), dumps a frame with it ON, and records ``hasGroundPlane()``
at each phase.  The host check asserts the API state and that the ON frame
differs from the OFF frame (the grid actually drew).

Run:
  FC_VULKAN_DUMP_FRAME=1 FC_VULKAN_DUMP_START=0 FC_VULKAN_DUMP_END=400 \\
      python3 tools/fcprobe/freecad_probe.py run \\
      tools/fcprobe/vk_groundplane_probe.py --profile vulkan
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
    print("GROUNDPLANE " + msg, flush=True)


s = Session(name="groundplane")
steps = [0]
view = [None]

# These prefs persist in the real user config; a suite run must not leave the
# ground plane on (and half-transparent) for every later probe.
_p = FreeCAD.ParamGet(VIEW)
_PRIOR = {
    "ShowGroundPlane": _p.GetBool("ShowGroundPlane", False),
    "GroundPlaneOpacity": _p.GetFloat("GroundPlaneOpacity", 0.15),
}


def restore_prefs():
    for key, value in _PRIOR.items():
        s.set_pref(VIEW, key, value)


def build_scene():
    FreeCADGui.activateWorkbench("PartWorkbench")
    doc = FreeCAD.newDocument("GroundPlane")
    box = doc.addObject("Part::Box", "Box")
    box.Length = box.Width = box.Height = 10
    doc.recompute()
    v = FreeCADGui.ActiveDocument.ActiveView
    # Top view looks straight down at Z = 0, so the whole grid is face-on and
    # only the box footprint occludes it.
    v.viewTop()
    v.fitAll()
    return v


def step():
    steps[0] += 1
    k = steps[0]
    if k == 1:
        for name in list(FreeCAD.listDocuments()):
            FreeCAD.closeDocument(name)
        s.set_pref(VIEW, "UseVulkanRenderer", True)
        # A faint grid is hard to detect in a frame dump; make it clearly
        # visible (0.5) before the grid is created.
        s.set_pref(VIEW, "GroundPlaneOpacity", 0.5)
        s.set_pref(VIEW, "ShowGroundPlane", False)
        view[0] = build_scene()
        s.frame_phase("ground-off")
        s.emit("groundplane", phase="off", on=0,
               has=int(bool(view[0].hasGroundPlane())))
        log("phase=off")
    elif k == 6:
        # Live pref toggle: ParameterObserver -> View3DSettings::OnChange ->
        # setGroundPlane().  hasGroundPlane() proves the node was created.
        s.set_pref(VIEW, "ShowGroundPlane", True)
        s.frame_phase("ground-on")
        s.emit("groundplane", phase="on", on=1,
               has=int(bool(view[0].hasGroundPlane())))
        log("phase=on has=%s" % view[0].hasGroundPlane())
    elif k == 12:
        s.expect("ground plane node created when ShowGroundPlane is on",
                 bool(view[0].hasGroundPlane()))
        s.snapshot()
        restore_prefs()
        s.finish()
        FreeCADGui.getMainWindow().close()
        return
    s.vulkan_render()
    QtCore.QTimer.singleShot(300, step)


QtCore.QTimer.singleShot(500, step)
