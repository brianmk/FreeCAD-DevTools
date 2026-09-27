"""Hover and click-select the box in the Vulkan viewport with synthetic mouse
events, and verify the pick returns the object.

The viewport is located by walking the main window for the Quarter Vulkan
widget, so it works with both the MDI and the Ribbon UI.  If the synthetic
click does not select (event routing is Qt-style dependent), the probe falls
back to a programmatic selection so the pick result is still checked.

Exit via os._exit(0).
"""

import os
import traceback

import FreeCAD
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets
from pivy import coin

OUT = os.environ.get("PROBE_OUT", "/tmp/opencode/gui-probes")
os.makedirs(OUT, exist_ok=True)
LOG = os.path.join(OUT, "mouse.log")


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


def find_viewport():
    mw = Gui.getMainWindow()
    found = []

    def walk(w, depth=0):
        if depth > 10 or found:
            return
        try:
            cls = w.metaObject().className()
        except Exception:
            cls = ""
        if cls == "SIM::Coin3D::Quarter::QuarterVulkanWidget":
            for kid in w.children():
                if isinstance(kid, QtWidgets.QWidget) and kid is not w:
                    found.append(kid)
                    return
            found.append(w)
            return
        for c in w.children():
            walk(c, depth + 1)

    walk(mw)
    return found[0] if found else None


def world_to_screen(view, wx, wy, wz):
    cam = view.getCameraNode()
    vv = cam.getViewVolume()
    # projectToScreen returns (x, y[, z]) depending on the pivy build.
    pr = vv.projectToScreen(coin.SbVec3f(wx, wy, wz))
    return pr[0], pr[1]


def send_mouse(container, etype, pos, btn, btns):
    target = container.childAt(pos) or container
    target.setMouseTracking(True)
    tpos = target.mapFrom(container, pos)
    ev = QtGui.QMouseEvent(etype, tpos, target.mapToGlobal(tpos), btn, btns,
                           QtCore.Qt.NoModifier)
    QtWidgets.QApplication.sendEvent(target, ev)
    QtWidgets.QApplication.processEvents()
    return target


def sel():
    return [o.Name for o in Gui.Selection.getSelection()]


def make():
    global doc, box
    doc = FreeCAD.newDocument("MouseDoc")
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


def step():
    step.i += 1
    try:
        if step.i == 1:
            make()
        elif step.i == 2:
            container = find_viewport()
            if container is None:
                log("ERROR no QuarterVulkanWidget found")
                QtCore.QTimer.singleShot(200, app_quit)
                return
            v = Gui.activeDocument().ActiveView
            dpr = container.devicePixelRatioF()
            nx, ny = world_to_screen(v, 25.0, 15.0, 10.0)
            sx = int(nx * container.width())
            sy = int((1.0 - ny) * container.height())
            info = v.getObjectInfo((int(sx * dpr), int(sy * dpr)))
            log("pick screen=(%d,%d) dpr=%.2f size=%dx%d -> %s"
                % (sx, sy, dpr, container.width(), container.height(), info))
            step.pt = (container, v, sx, sy)
        elif step.i == 3:
            container, _v, sx, sy = step.pt
            target = send_mouse(container, QtCore.QEvent.MouseMove,
                                QtCore.QPoint(sx, sy), QtCore.Qt.NoButton,
                                QtCore.Qt.NoButton)
            log("hover target=%s selection=%s"
                % (target.metaObject().className(), sel()))
        elif step.i == 4:
            container, _v, sx, sy = step.pt
            target = send_mouse(container, QtCore.QEvent.MouseButtonPress,
                                QtCore.QPoint(sx, sy), QtCore.Qt.LeftButton,
                                QtCore.Qt.LeftButton)
            send_mouse(container, QtCore.QEvent.MouseButtonRelease,
                       QtCore.QPoint(sx, sy), QtCore.Qt.LeftButton,
                       QtCore.Qt.NoButton)
            log("click target=%s selection=%s"
                % (target.metaObject().className(), sel()))
            if not sel():
                Gui.Selection.clearSelection()
                Gui.Selection.addSelection(doc.Name, "Box")
                Gui.updateGui()
                log("fallback addSelection selection=%s" % sel())
        elif step.i == 5:
            v = Gui.activeDocument().ActiveView
            v.saveImage(os.path.join(OUT, "mouse_after_click.png"),
                        900, 700, "White")
            log("save after_click selection=%s" % sel())
        elif step.i == 6:
            log("done")
            QtCore.QTimer.singleShot(200, app_quit)
            return
    except Exception as exc:
        log("ERROR step=%d %r\n%s" % (step.i, exc, traceback.format_exc()))
        QtCore.QTimer.singleShot(200, app_quit)
        return
    QtCore.QTimer.singleShot(1200, step)


def app_quit():
    os._exit(0)


step.i = 0
QtCore.QTimer.singleShot(3000, step)
