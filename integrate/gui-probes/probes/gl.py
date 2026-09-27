"""Render a box with the classic Coin/GL raster path (VulkanRenderMode=0, the
GL fallback) and save the viewport image.

Set RT_USE_VK=0 to fully disable the Vulkan backend (renders through the
classic Coin/GL viewer); the default keeps the Vulkan-enabled view and selects
the RasterCoin render mode (0), which is the fork's GL fallback.

Exit via os._exit(0).
"""

import os
import traceback

import FreeCAD
import FreeCADGui as Gui
from PySide import QtCore

OUT = os.environ.get("PROBE_OUT", "/tmp/opencode/gui-probes")
os.makedirs(OUT, exist_ok=True)
LOG = os.path.join(OUT, "gl.log")


def log(msg):
    with open(LOG, "a") as fh:
        fh.write(msg + "\n")
    try:
        os.write(1, ("PROBE " + msg + "\n").encode())
    except Exception:
        pass


open(LOG, "w").close()

use_vk = os.environ.get("RT_USE_VK", "1") == "1"
tag = "mode0_usevk%d" % (1 if use_vk else 0)

prefs = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/View")
prefs.SetBool("UseVulkanRenderer", use_vk)
prefs.SetInt("VulkanRenderMode", 0)
log("prefs UseVulkanRenderer=%s VulkanRenderMode=0 tag=%s" % (use_vk, tag))

doc = None
box = cyl = sph = None


def make():
    global doc, box, cyl, sph
    doc = FreeCAD.newDocument("GLDoc")
    box = doc.addObject("Part::Box", "Box")
    box.Length = 40
    box.Width = 30
    box.Height = 20
    cyl = doc.addObject("Part::Cylinder", "Cylinder")
    cyl.Radius = 12
    cyl.Height = 35
    cyl.Placement.Base = FreeCAD.Vector(70, 0, 0)
    sph = doc.addObject("Part::Sphere", "Sphere")
    sph.Radius = 16
    sph.Placement.Base = FreeCAD.Vector(140, 0, 0)
    doc.recompute()
    v = Gui.activeDocument().ActiveView
    v.viewIsometric()
    v.fitAll()
    Gui.updateGui()
    log("doc created mode=%s" % v.getRenderMode())


def snap():
    v = Gui.activeDocument().ActiveView
    path = os.path.join(OUT, "gl_%s.png" % tag)
    v.saveImage(path, 900, 700, "White")
    log("save mode=%s path=%s" % (v.getRenderMode(), path))


def step():
    step.i += 1
    try:
        if step.i == 1:
            make()
        elif step.i == 2:
            snap()
        elif step.i == 3:
            log("done")
            QtCore.QTimer.singleShot(300, app_quit)
            return
    except Exception as exc:
        log("ERROR step=%d %r\n%s" % (step.i, exc, traceback.format_exc()))
        QtCore.QTimer.singleShot(300, app_quit)
        return
    QtCore.QTimer.singleShot(1200, step)


def app_quit():
    os._exit(0)


step.i = 0
QtCore.QTimer.singleShot(3000, step)
