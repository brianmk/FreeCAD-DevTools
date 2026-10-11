"""Toggle the wireframe and points overlays and save the viewport after each
state, proving the edge/point overlay re-draws work and that switching back
restores the filled view.

Images via view.saveImage(); exit via os._exit(0).
"""

import os
import traceback

import FreeCAD
import FreeCADGui as Gui
from PySide import QtCore

OUT = os.environ.get("PROBE_OUT", "/tmp/opencode/gui-probes")
os.makedirs(OUT, exist_ok=True)
LOG = os.path.join(OUT, "edges.log")


def log(msg):
    with open(LOG, "a") as fh:
        fh.write(msg + "\n")
    try:
        os.write(1, ("PROBE " + msg + "\n").encode())
    except Exception:
        pass


open(LOG, "w").close()

prefs = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/View")
prefs.SetBool("UseVulkanRenderer", True)
prefs.SetInt("VulkanRenderMode", 1)
prefs.SetBool("VulkanWireframe", False)
prefs.SetBool("VulkanShowPoints", False)
log("prefs VulkanRenderMode=1 Wireframe=False Points=False")

doc = None
box = None


def make():
    global doc, box
    doc = FreeCAD.newDocument("EdgeDoc")
    box = doc.addObject("Part::Box", "Box")
    box.Length = 50
    box.Width = 30
    box.Height = 20
    doc.recompute()
    v = Gui.activeDocument().ActiveView
    v.viewIsometric()
    v.fitAll()
    Gui.updateGui()
    log("doc created")


def save(tag):
    v = Gui.activeDocument().ActiveView
    path = os.path.join(OUT, "edges_%s.png" % tag)
    v.saveImage(path, 900, 700, "White")
    log("save %-9s mode=%s path=%s" % (tag, v.getRenderMode(), path))


def set_state(wire, points):
    prefs.SetBool("VulkanWireframe", wire)
    prefs.SetBool("VulkanShowPoints", points)
    Gui.activeDocument().ActiveView.redraw()
    Gui.updateGui()


def step():
    step.i += 1
    try:
        if step.i == 1:
            make()
        elif step.i == 2:
            save("normal")
        elif step.i == 3:
            set_state(True, False)
            save("wireframe")
        elif step.i == 4:
            set_state(False, True)
            save("points")
        elif step.i == 5:
            set_state(False, False)
            save("restored")
        elif step.i == 6:
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
