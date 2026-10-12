#!/usr/bin/env python3
"""Probe: Coin renderer -> Vulkan mode switch.

Reproduces the user's report "can't change from coin renderer to vulkan".

The probe:
  * Opens a document with a box (PartWorkbench).
  * Handles the active-view carefully (view may exist only after a doc+window).
  * Drives the switch through the status-bar render-mode combo
    (`QComboBox "viewModeCombo"`, see MainWindow::addStatusBarItem).  A missing
    combo is a FAIL: falling back to `view.setRenderMode()` would exercise the
    Python API while never touching the control the user actually uses, which is
    how a "the combo changes the label but nothing else happens" bug survived
    this probe before.
  * Phase 1 (fresh config): leaves `UseVulkanRenderer` off, so the view is
    created without a Vulkan adapter, then selects RasterVulkan in the combo and
    requires the Vulkan frame counter to advance -- the status-bar selector must
    create the viewport, not merely record the mode.
  * Phase 2: turns `UseVulkanRenderer` on and steps through
    RasterCoin(0) -> RasterVulkan(1) -> back -> forward, logging the effective
    renderMode and the QStackedWidget currentWidget.
  * Verdict PASS if after selecting RasterVulkan the effective renderMode is
    RasterVulkan AND forcing a frame advances the Vulkan frame counter.

Run:
  FreeCAD vk_modelswitch_probe.py
"""

import os
import sys
import time

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtWidgets

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from freecad_probe import Session  # noqa: E402

VIEW = "User parameter:BaseApp/Preferences/View"

# The status-bar render-mode selector.  MainWindow creates the QComboBox with
# object name "ViewRenderingMode" and then hands it to addStatusBarItem(), which
# overwrites the object name with the spec id ("viewModeCombo"): look it up by
# what the widget actually ends up named.
VIEW_MODE_COMBO = "viewModeCombo"


def log(msg):
    print("MODESW " + msg, file=sys.stderr)


s = Session(name="modelswitch")
steps = [0]


def combo():
    mw = FreeCADGui.getMainWindow()
    if mw is None:
        return None
    return mw.findChild(QtWidgets.QComboBox, VIEW_MODE_COMBO)


def active_view():
    doc = FreeCADGui.ActiveDocument
    if doc is None:
        return None
    try:
        return doc.ActiveView
    except Exception:
        return None


def report(tag, expect_mode=None, expect_vulkan=None):
    view = active_view()
    if view is None:
        log(f"[{tag}] no active view")
        s.error(f"{tag}: no active view")
        return
    mode = int(view.getRenderMode())
    frame = 0
    try:
        frame = view.getVulkanFrameCount()
    except Exception:
        pass
    mw = FreeCADGui.getMainWindow()
    stack = mw.findChild(QtWidgets.QStackedWidget) if mw else None
    cur = "none"
    if stack and stack.currentWidget():
        cur = stack.currentWidget().__class__.__name__
    c = combo()
    if c is None:
        cstr = "combo=ABSENT"
        s.error(
            f"{tag}: status-bar render-mode combo (QComboBox "
            f"'{VIEW_MODE_COMBO}') is absent - the render-mode selector is not "
            f"in the status bar, so there is no user-facing way to switch"
        )
    else:
        cstr = f"combo=present(idx={c.currentIndex()})"
    log(f"[{tag}] renderMode={mode} frame={frame} stackCur={cur} {cstr}")

    # The report was "can't change from the Coin renderer to Vulkan"; without these
    # assertions the case passed as long as the probe did not crash.
    if expect_mode is not None:
        if mode != expect_mode:
            s.error(f"{tag}: renderMode={mode}, expected {expect_mode}")
        else:
            s.expect(True, f"{tag}: renderMode={mode}")
    if expect_vulkan is not None:
        # The stack found above may belong to a dock (property view), so assert on what
        # actually matters: forcing a frame must advance the Vulkan frame counter in
        # Vulkan mode, and must not in Coin mode.  (The frame count is exposed by the
        # fork's View3DInventor; requestVulkanRender() is a no-op in Coin mode.)
        before = int(frame)
        try:
            view.requestVulkanRender()
        except Exception:
            pass
        after = before
        for _ in range(60):
            FreeCADGui.updateGui()
            QtCore.QCoreApplication.processEvents()
            try:
                after = int(view.getVulkanFrameCount())
            except Exception:
                break
            if after != before:
                break
            time.sleep(0.02)
        log(f"[{tag}] forced frame: {before} -> {after} (stackCur={cur})")
        if expect_vulkan and after <= before:
            s.error(f"{tag}: renderMode is {mode} but forcing a frame did not "
                    f"advance the Vulkan frame counter ({before} -> {after}): no "
                    f"rendering Vulkan viewport was created for the selected mode")
        elif not expect_vulkan and after != before:
            s.error(f"{tag}: Coin/GL page is current but the Vulkan frame counter "
                    f"advanced ({before} -> {after})")
        else:
            s.expect(True, f"{tag}: frame counter {before} -> {after}")


def build():
    for name in list(FreeCAD.listDocuments()):
        FreeCAD.closeDocument(name)
    doc = FreeCAD.newDocument("MSwitch")
    box = doc.addObject("Part::Box", "Box")
    box.Length = 50
    box.Width = 50
    box.Height = 50
    doc.recompute()
    FreeCADGui.updateGui()
    FreeCADGui.Selection.clearSelection()
    view = FreeCADGui.ActiveDocument.ActiveView
    view.setAnimationEnabled(False)
    view.viewIsometric()
    view.fitAll()
    FreeCADGui.updateGui()
    return view


def set_mode(mode):
    """Switch render mode through the status-bar combo.

    The combo is the product path under test.  If it is missing, fail: silently
    falling back to view.setRenderMode() would exercise the Python API and pass
    while the control the user actually drives stays broken.
    """
    c = combo()
    if c is None:
        s.error(
            f"set_mode({mode}): status-bar combo '{VIEW_MODE_COMBO}' is absent; "
            f"refusing to fall back to view.setRenderMode()"
        )
        return False
    c.setCurrentIndex(mode)
    FreeCADGui.updateGui()
    QtCore.QCoreApplication.processEvents()
    log(f"via combo index={mode}")
    return True


def step():
    steps[0] += 1
    k = steps[0]
    if k == 1:
        FreeCADGui.activateWorkbench("PartWorkbench")
        FreeCADGui.updateGui()
        # Phase 1: fresh-config state.  UseVulkanRenderer off means the view is
        # created in the classic Coin/OpenGL mode with no Vulkan adapter at all,
        # which is exactly what a user with default settings has.
        s.set_pref(VIEW, "UseVulkanRenderer", False)
        s.set_pref(VIEW, "VulkanRenderMode", 0)
        build()
        report("fresh-coin", expect_mode=0, expect_vulkan=False)
    elif k == 12:
        # Selecting Vulkan in the combo must bring up the Vulkan viewport, not
        # just record the mode: the frame counter has to advance.
        set_mode(1)
        report("fresh-coin->vulkan", expect_mode=1, expect_vulkan=True)
    elif k == 24:
        # Phase 2: a view whose new-view default is Vulkan.
        s.set_pref(VIEW, "UseVulkanRenderer", True)
        s.set_pref(VIEW, "VulkanRenderMode", 0)
        build()
        # Explicitly start in coin after the view exists.
        v = active_view()
        if v is not None:
            v.setRenderMode(0)
            FreeCADGui.updateGui()
        report("init-coin", expect_mode=0, expect_vulkan=False)
    elif k == 36:
        set_mode(1)
        report("coin->vulkan", expect_mode=1, expect_vulkan=True)
    elif k == 48:
        set_mode(0)
        report("vulkan->coin", expect_mode=0, expect_vulkan=False)
    elif k == 60:
        set_mode(1)
        report("coin->vulkan-2", expect_mode=1, expect_vulkan=True)
    elif k == 72:
        view = active_view()
        mode = int(view.getRenderMode()) if view is not None else -1
        log(f"final effective renderMode={mode}")
        if mode != 1:
            s.error(f"final effective renderMode={mode}, expected 1")
        s.snapshot()
        s.finish("effective renderMode after coin->vulkan")
        FreeCADGui.getMainWindow().close()
        return
    QtCore.QTimer.singleShot(350, step)


QtCore.QTimer.singleShot(600, step)
