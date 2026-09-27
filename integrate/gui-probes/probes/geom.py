"""Render a box, a cylinder and a sphere and save one viewport image each.

The image is written with view.saveImage() because screen capture is unusable
on this box (a fullscreen video owns the display).  The process exits with
os._exit(0): close()/quit() block while a 3D view is open.
"""

import os
import traceback

import FreeCAD
import FreeCADGui as Gui
from PySide import QtCore

OUT = os.environ.get("PROBE_OUT", "/tmp/opencode/gui-probes")
os.makedirs(OUT, exist_ok=True)
LOG = os.path.join(OUT, "geom.log")


def log(msg):
    with open(LOG, "a") as fh:
        fh.write(msg + "\n")
    try:
        os.write(1, ("PROBE " + msg + "\n").encode())
    except Exception:
        pass


open(LOG, "w").close()

# Preferences must be set before the 3D view is created.
prefs = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/View")
prefs.SetBool("UseVulkanRenderer", True)
prefs.SetInt("VulkanRenderMode", 1)
log("prefs UseVulkanRenderer=True VulkanRenderMode=1")

doc = None
box = cyl = sph = None


def make():
    global doc, box, cyl, sph
    import Part  # noqa: F401  (registers Part::* object types)

    doc = FreeCAD.newDocument("GeomDoc")
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
    log("doc created objects=%d" % len(doc.Objects))


def snap(name):
    v = Gui.activeDocument().ActiveView
    wanted = name or None
    for obj in (box, cyl, sph):
        obj.ViewObject.Visibility = wanted is None or obj.Name == wanted
    v.viewIsometric()
    v.fitAll()
    Gui.updateGui()
    path = os.path.join(OUT, "geom_%s.png" % (wanted or "all").lower())
    v.saveImage(path, 900, 700, "White")
    log("snap %s mode=%s path=%s" % (wanted or "all", v.getRenderMode(), path))


def step():
    step.i += 1
    try:
        if step.i == 1:
            make()
        elif step.i == 2:
            snap("")
        elif step.i == 3:
            snap("Box")
        elif step.i == 4:
            snap("Cylinder")
        elif step.i == 5:
            snap("Sphere")
        elif step.i == 6:
            log("done")
            QtCore.QTimer.singleShot(300, app_quit)
            return
    except Exception as exc:
        log("ERROR step=%d %r\n%s" % (step.i, exc, traceback.format_exc()))
        QtCore.QTimer.singleShot(300, app_quit)
        return
    QtCore.QTimer.singleShot(1000, step)


def app_quit():
    os._exit(0)


step.i = 0
QtCore.QTimer.singleShot(3000, step)
