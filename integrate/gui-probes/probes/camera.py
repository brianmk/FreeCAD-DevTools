"""Exercise the camera commands (isometric/top/front/fitAll) and save an image
after each, to prove the camera path does not crash and renders content.

Images via view.saveImage(); exit via os._exit(0) (close()/quit() block).
"""

import os
import traceback

import FreeCAD
import FreeCADGui as Gui
from PySide import QtCore

OUT = os.environ.get("PROBE_OUT", "/tmp/opencode/gui-probes")
os.makedirs(OUT, exist_ok=True)
LOG = os.path.join(OUT, "camera.log")


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
log("prefs UseVulkanRenderer=True VulkanRenderMode=1")

doc = None
box = None


def make():
    global doc, box
    doc = FreeCAD.newDocument("CamDoc")
    box = doc.addObject("Part::Box", "Box")
    box.Length = 50
    box.Width = 30
    box.Height = 20
    doc.recompute()
    log("doc created")


def snap(view_call, tag):
    v = Gui.activeDocument().ActiveView
    view_call()
    Gui.updateGui()
    path = os.path.join(OUT, "cam_%s.png" % tag)
    v.saveImage(path, 900, 700, "White")
    log("snap %-9s mode=%s path=%s" % (tag, v.getRenderMode(), path))


def step():
    step.i += 1
    try:
        if step.i == 1:
            make()
        elif step.i == 2:
            snap(Gui.activeDocument().ActiveView.viewIsometric, "isometric")
        elif step.i == 3:
            snap(Gui.activeDocument().ActiveView.viewTop, "top")
        elif step.i == 4:
            snap(Gui.activeDocument().ActiveView.viewFront, "front")
        elif step.i == 5:
            snap(Gui.activeDocument().ActiveView.fitAll, "fitall")
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
