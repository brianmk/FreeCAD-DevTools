#!/usr/bin/env python3
"""GPU ray-query picking parity with the CPU pick (Vulkan RTX viewports).

``SoBrepFaceSet::rayPick`` consults ``GpuPickService`` when a Vulkan/RTX
viewport has registered a picker; the picker answers only once hardware ray
tracing is active, so in the raster Vulkan mode the unchanged CPU
``SoRayPickAction`` path runs and in PathTracing mode a single GPU ray query
against the TLAS replaces the CPU traversal.

The probe samples ``getObjectInfo`` at fixed screen points in both modes and
asserts the picked object/component and world position agree: if the GPU path
mis-picks (wrong shape, wrong face, or misses), the two disagree.  The host
check independently asserts the RT backend actually initialized (so the GPU
path, not a silent CPU fallback, was in play).

Run:
  FC_VULKAN_RT_DEBUG=1 python3 tools/fcprobe/freecad_probe.py run \\
      tools/fcprobe/vk_gpupick_probe.py --profile vulkan
"""

import os
import sys

import FreeCAD
import FreeCADGui
from PySide import QtCore

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from freecad_probe import Session  # noqa: E402

VIEW = "User parameter:BaseApp/Preferences/View"
MODE_RASTER = 1   # RasterVulkan (CPU pick path)
MODE_RT = 4       # PathTracing  (GPU pick path)
POS_TOL = 0.5     # mm; CPU triangle intersection vs GPU TLAS hit


def log(msg):
    print("GPUPICK " + msg, flush=True)


s = Session(name="gpupick")
steps = [0]
view = [None]
record = {"raster": [], "rt": []}


def sample_points(w, h):
    return [
        ("center", w / 2.0, h / 2.0),
        ("top", w / 2.0, h * 0.12),
        ("left", w * 0.12, h / 2.0),
        ("right", w * 0.88, h / 2.0),
        ("bottom", w / 2.0, h * 0.88),
    ]


def sample(mode):
    rows = []
    for name, x, y in sample_points(s.width, s.height):
        info = s.get_object_info(x, y)
        if info:
            row = (name, info.get("Object", ""), info.get("Component", ""),
                   float(info["x"]), float(info["y"]), float(info["z"]))
        else:
            row = (name, "", "", 0.0, 0.0, 0.0)
        rows.append(row)
        s.emit("gpick", mode=mode, point=name, hit=(1 if info else 0),
               ob=row[1], comp=row[2], x=round(row[3], 4),
               y=round(row[4], 4), z=round(row[5], 4))
        log("mode=%s point=%s hit=%d ob=%s comp=%s" %
            (mode, name, 1 if info else 0, row[1], row[2]))
    return rows


def build_scene():
    FreeCADGui.activateWorkbench("PartWorkbench")
    doc = FreeCAD.newDocument("GpuPick")
    box = doc.addObject("Part::Box", "Box")
    box.Length = box.Width = box.Height = 10
    doc.recompute()
    v = FreeCADGui.ActiveDocument.ActiveView
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
        s.set_pref(VIEW, "VulkanRenderMode", MODE_RASTER)
        view[0] = build_scene()
        s.frame_phase("raster")
    elif k == 5:
        record["raster"] = sample("raster")
    elif k == 6:
        # Live switch to path tracing: the RTX picker becomes available and
        # SoBrepFaceSet::rayPick now takes the GPU path.
        s.set_pref(VIEW, "VulkanRenderMode", MODE_RT)
        s.frame_phase("rt")
    elif k == 25:
        record["rt"] = sample("rt")
    elif k == 26:
        compare()
        s.snapshot()
        s.finish()
        FreeCADGui.getMainWindow().close()
        return
    s.vulkan_render()
    QtCore.QTimer.singleShot(300, step)


def compare():
    raster, rt = record["raster"], record["rt"]
    if not raster or not rt:
        s.expect("both modes sampled", False,
                 "raster=%d rt=%d" % (len(raster), len(rt)))
        return
    raster_hits = sum(1 for r in raster if r[1])
    rt_hits = sum(1 for r in rt if r[1])
    s.expect("raster mode picks the box at the sampled points",
             raster_hits > 0, "hits=%d" % raster_hits)
    s.expect("RT mode picks the box at the sampled points",
             rt_hits > 0, "hits=%d" % rt_hits)
    for r, t in zip(raster, rt):
        name = r[0]
        if bool(r[1]) != bool(t[1]):
            s.expect("GPU/CPU pick hit parity at %s" % name, False,
                     "raster=%r rt=%r" % (r[1:3], t[1:3]))
            continue
        if not r[1]:
            continue
        s.expect("GPU/CPU picked object parity at %s" % name,
                 r[1] == t[1], "raster=%s rt=%s" % (r[1], t[1]))
        s.expect("GPU/CPU picked component parity at %s" % name,
                 r[2] == t[2], "raster=%s rt=%s" % (r[2], t[2]))
        d = max(abs(r[3] - t[3]), abs(r[4] - t[4]), abs(r[5] - t[5]))
        s.expect("GPU/CPU hit position parity at %s" % name,
                 d <= POS_TOL, "max delta=%.4f" % d)


QtCore.QTimer.singleShot(500, step)
