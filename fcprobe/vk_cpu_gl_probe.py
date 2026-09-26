#!/usr/bin/env python3
"""CPU-only render probe: native Wayland with software OpenGL (llvmpipe).

Run under the ``cpu-gl`` profile, which puts Mesa's libEGL/libGL (llvmpipe)
ahead of the GPU driver on the loader path and sets ``LIBGL_ALWAYS_SOFTWARE=1``
/ ``MESA_LOADER_DRIVER_OVERRIDE=llvmpipe``.  The probe forces the OpenGL/Coin
viewport (``UseVulkanRenderer=False``), renders a box on the native Wayland
platform, and saves the viewport with ``view.saveImage()``.

The host check asserts the software-GL env was in force and that the saved
image is a real (non-uniform) render -- i.e. FreeCAD rendered on the CPU on
Wayland with no GPU.

Run:
  python3 tools/fcprobe/freecad_probe.py run \\
      tools/fcprobe/vk_cpu_gl_probe.py --profile cpu-gl
"""

import os
import sys

import FreeCAD
import FreeCADGui
from PySide import QtCore

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from freecad_probe import Session  # noqa: E402

VIEW = "User parameter:BaseApp/Preferences/View"
OUT = os.environ.get("FC_CPU_PNG", "/tmp/opencode/cpu_gl_probe.png")


def log(msg):
    print("CPU-GL " + msg, flush=True)


s = Session(name="cpu-gl")
steps = [0]


def build_scene():
    FreeCADGui.activateWorkbench("PartWorkbench")
    doc = FreeCAD.newDocument("CpuGL")
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
        # Force the GL/Coin viewport: this probe covers the CPU OpenGL path.
        s.set_pref(VIEW, "UseVulkanRenderer", False)
        build_scene()
        s.frame_phase("cpu-gl")
        log("built on the software GL (llvmpipe) path")
    elif k == 6:
        try:
            view = FreeCADGui.ActiveDocument.ActiveView
            view.saveImage(OUT)
            s.emit("cpugl", phase="save", path=OUT,
                   exists=int(os.path.exists(OUT)))
            log("saveImage -> %s exists=%s" % (OUT, os.path.exists(OUT)))
        except Exception as exc:  # noqa: BLE001
            s.error("saveImage failed: %s" % exc)
            return
        s.snapshot()
        s.finish()
        FreeCADGui.getMainWindow().close()
        return
    QtCore.QTimer.singleShot(400, step)


QtCore.QTimer.singleShot(500, step)
