#!/usr/bin/env python3
"""Regression: hovering the Vulkan nav cube must present a frame.

The nav cube lives in the viewer's *decoration* overlay
(``View3DInventorViewer::decorationroot`` -> ``naviCubeAnnotation``), which is
deliberately not part of the render manager's scene graph.  The Vulkan adapter
watches that scene graph with an ``SoNodeSensor``, so a nav cube field write is
invisible to it, and the display-only Vulkan widget owns no sensors of its own:
the ONLY way a hover highlight reaches the swapchain is
``View3DInventorViewer::requestNaviCubeRedraw()``.

Pre-fix, ``NaviCubeImplementation::setHilite()`` and the ``mouseMoved()``
hovering transition called ``SoRenderManager::scheduleRedraw()`` directly,
which wakes the hidden GL render manager and nothing else -- so the highlight
state was set but no frame was ever presented (a nav cube *click* still worked
because it moves the camera, which the adapter's camera sensor does wake).

This probe hovers the pointer over the nav cube with NO button pressed and
watches the *presented* frame ordinal (``getVulkanFrameCount()``).  It also
records, best effort, whether the hover state itself changed, using
``saveImage()`` -- that is a Coin/GL offscreen render of the same nav cube
node (it shares the node, not the swapchain), so it witnesses *state* only.
Reading both is what separates "the hover state never updated" from "the state
updated but no frame was presented".

Emitted per hover move::

    [HARNESS] navicube_hover phase=<off|entry|sweep|repeat> x=.. y=.. frames=<n>

``frames`` is the number of presented Vulkan frames the move caused.
``phase=repeat`` re-hovers the point of the last sweep move: that changes
nothing, so it must present 0 frames -- the control proving the deltas above
are caused by the hover state change and not by unrelated/refining frames.

Run::

  FC_FREECAD_BIN=... FREECAD_SRC=... python3 fcprobe/freecad_probe.py run \\
      fcprobe/vk_navicube_hover_probe.py --profile vulkan-xcb --name nav-hover
"""

import hashlib
import os
import sys

import FreeCAD
import FreeCADGui
from PySide import QtCore

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from freecad_probe import Session  # noqa: E402

VIEW = "User parameter:BaseApp/Preferences/View"

# NaviCube::getNaviCubeSize() default (cubeWidgetSize) and its placement math:
# NaviCubeImplementation::handleResize() insets the placement area by
# size * 0.55 from the corner, and the cube sits on the far edge of that area,
# so for corner 1 (top-right) its centre is (viewW - inset, inset) in Qt coords.
CUBE_SIZE = 132
CORNER = 1  # 0=top-left, 1=top-right, 2=bottom-left, 3=bottom-right

# Hover grid around the cube centre, in logical px: the projected silhouette is
# about CUBE_SIZE across, so a +-40 px grid covers every visible face and the
# vertex they share.  Ordered to jump between faces.
GRID_OFFSETS = [
    (0, 0), (40, -40), (-40, -40), (0, -40), (40, 40),
    (-40, 40), (40, 0), (-40, 0), (0, 40),
]

# Frames are presented asynchronously; a phase is considered settled when the
# ordinal has not moved for QUIET_MS, capped at MAX_MS.
QUIET_MS = 500
MAX_MS = 6000

s = Session(name="navicube-hover")
view = [None]
steps = [0]
data = {"off": [], "entry": [], "sweep": [], "repeat": [], "guard": []}


def log(msg):
    print("NAVICUBE-HOVER " + msg, flush=True)


def pump(ms):
    timer = QtCore.QElapsedTimer()
    timer.start()
    while timer.elapsed() < ms:
        QtCore.QCoreApplication.processEvents()
        QtCore.QThread.msleep(5)


def frames():
    """Presented-frame ordinal of the Vulkan viewport (-1: no Vulkan API)."""
    try:
        v = FreeCADGui.activeView() or FreeCADGui.ActiveDocument.ActiveView
        return int(v.getVulkanFrameCount())
    except Exception:
        return -1


def wait_quiet(quiet_ms=QUIET_MS, max_ms=MAX_MS):
    """Pump until the presented-frame ordinal stops moving; return it."""
    timer = QtCore.QElapsedTimer()
    timer.start()
    last = frames()
    last_change = 0
    while timer.elapsed() < max_ms:
        pump(20)
        now = frames()
        if now != last:
            last = now
            last_change = timer.elapsed()
        elif timer.elapsed() - last_change >= quiet_ms:
            break
    return last


def hover(phase, x, y):
    """Move the pointer to (x, y) and count the frames it presented."""
    before = wait_quiet()
    s.move(x, y)
    timer = QtCore.QElapsedTimer()
    timer.start()
    peak = before
    while timer.elapsed() < 600:
        pump(10)
        peak = max(peak, frames())
    peak = max(peak, wait_quiet())
    delta = max(peak - before, 0)
    s.emit("navicube_hover", phase=phase, x=int(x), y=int(y), frames=delta)
    log("phase=%s (%d,%d) frames=%d" % (phase, x, y, delta))
    return delta


def cube_state(tag, x0, y0, size):
    """Digest the nav cube region of the offscreen GL render (state only).

    saveImage() renders the viewer's Coin scene -- including the decoration
    overlay that carries the nav cube node -- offscreen.  It shares the nav
    cube *node* with the Vulkan overlay but is NOT the Vulkan swapchain, so it
    witnesses the hover *state* only.  (grabFramebuffer() is unusable here:
    under Vulkan the hidden GL widget is never repainted, so it returns a stale
    image with an identical digest for every pointer position -- verified by
    the nav_state_diag dumps.)

    Returns (sha1-ish digest, image) or (None, None).
    """
    path = "/tmp/navicube_hover_state_%s.png" % tag
    try:
        from PySide import QtGui
        view[0].saveImage(path)
        img = QtGui.QImage(path)
    except Exception as exc:
        log("saveImage state witness unavailable: %s" % exc)
        return None, None
    if img is None or img.isNull():
        log("saveImage produced no image for the state witness")
        return None, None
    rect = QtCore.QRect(int(x0), int(y0), int(size), int(size))
    crop = img.copy(rect.intersected(img.rect()))
    if crop.isNull() or crop.width() <= 0:
        return None, None
    try:
        digest = hashlib.sha1(bytes(crop.constBits())).hexdigest()[:16]
    except Exception:
        # Older/odd PySide builds: fall back to a sampled-pixel digest.
        samples = [
            crop.pixel(x, y)
            for y in range(0, crop.height(), 4)
            for x in range(0, crop.width(), 4)
        ]
        digest = hashlib.sha1(repr(samples).encode()).hexdigest()[:16]
    return digest, crop


def diff_pixels(a, b, step=3):
    if a is None or b is None or a.size() != b.size():
        return -1
    count = 0
    total = 0
    for y in range(0, a.height(), step):
        for x in range(0, a.width(), step):
            total += 1
            if a.pixel(x, y) != b.pixel(x, y):
                count += 1
    return count


def cube_center():
    dpr = s.dpr or 1.0
    inset = int(CUBE_SIZE * dpr * 0.55) / dpr
    return s.width - inset, inset


def build_scene():
    for name in list(FreeCAD.listDocuments()):
        FreeCAD.closeDocument(name)
    s.set_pref(VIEW, "UseVulkanRenderer", True)
    FreeCADGui.activateWorkbench("PartWorkbench")
    doc = FreeCAD.newDocument("NaviCubeHover")
    box = doc.addObject("Part::Box", "Box")
    box.Length = box.Width = box.Height = 10
    doc.recompute()
    v = FreeCADGui.ActiveDocument.ActiveView
    v.viewIsometric()
    v.fitAll()
    # Pull the camera back so the model stays clear of the nav cube corner: a
    # pick under a hover point would preselect geometry and produce frames of
    # its own, which would make the measurement meaningless.
    try:
        cam = v.getCameraNode()
        cam.height.setValue(cam.height.getValue() * 3.5)
    except Exception as exc:
        log("camera zoom-out skipped: %s" % exc)
    FreeCADGui.updateGui()
    return v


def step():
    steps[0] += 1
    k = steps[0]
    if k == 1:
        view[0] = build_scene()
        s.frame_phase("built")
    elif k == 3:
        s._relocate_viewport()
        v = view[0]
        v.getViewer().setNaviCubeCorner(CORNER)
        v.getViewer().setEnabledNaviCube(True)
        FreeCADGui.updateGui()
        cx, cy = cube_center()
        log("viewport %dx%d dpr=%.2f cube centre (%.0f,%.0f)"
            % (s.width, s.height, s.dpr, cx, cy))
        # Nothing may be pickable under a hover point, or a frame could come
        # from preselection instead of the nav cube.
        for dx, dy in GRID_OFFSETS:
            x, y = min(max(cx + dx, 1), s.width - 2), min(max(cy + dy, 1), s.height - 2)
            info = s.get_object_info(x, y)
            data["guard"].append(bool(info))
            s.emit("navicube_hover_guard", x=int(x), y=int(y),
                   pick=(1 if info else 0))
        s.frame_phase("guards")
    elif k == 4:
        # Control: hover the lower-left background, well away from cube+model.
        x, y = s.width * 0.15, s.height * 0.85
        hover("off_settle", x, y)
        data["off"].append(hover("off", x + 6, y + 4))
    elif k == 5:
        cx, cy = cube_center()
        points = []
        for dx, dy in GRID_OFFSETS:
            points.append((min(max(cx + dx, 1), s.width - 2),
                           min(max(cy + dy, 1), s.height - 2)))
        s.frame_phase("entry")
        data["entry"].append(hover("entry", *points[0]))
        s.frame_phase("sweep")
        for x, y in points[1:]:
            data["sweep"].append(hover("sweep", x, y))
        s.frame_phase("repeat")
        data["repeat"].append(hover("repeat", *points[-1]))
        data["repeat"].append(hover("repeat", *points[-1]))
    elif k == 6:
        # State witness: background vs the nav cube centre -- the face the
        # reported bug hovers.  saveImage() is an offscreen Coin/GL render of
        # the same nav cube node (state only, never the swapchain).
        s.frame_phase("state")
        dpr = s.dpr or 1.0
        cx, cy = cube_center()
        x0 = (cx - CUBE_SIZE * 0.75) * dpr
        y0 = (cy - CUBE_SIZE * 0.75) * dpr
        size = CUBE_SIZE * 1.5 * dpr
        s.move(s.width * 0.15, s.height * 0.85)
        wait_quiet()
        before, img_before = cube_state("off", x0, y0, size)
        s.move(cx, cy)
        wait_quiet()
        after, img_after = cube_state("face", x0, y0, size)
        changed = bool(before and after and before != after)
        px = diff_pixels(img_before, img_after)
        s.emit("navicube_hover_state", state_before=(before or "none"),
               state_after=(after or "none"),
               changed=(1 if changed else 0), diff_px=px)
        data["state_changed"] = (1 if changed else 0) if before else None
        log("state before=%s after=%s changed=%s diff_px=%s"
            % (before, after, changed, px))
    elif k == 7:
        off_frames = sum(data["off"])
        entry_frames = sum(data["entry"])
        sweep_frames = sum(data["sweep"])
        repeat_frames = sum(data["repeat"])
        hover_frames = entry_frames + sweep_frames
        baseline = frames()
        s.expect("nav cube hover ran against the Vulkan viewport",
                 baseline > 0, "presented frames=%s" % baseline)
        s.expect("nothing pickable under a nav cube hover point",
                 not any(data["guard"]),
                 "picked=%s" % sum(1 for g in data["guard"] if g))
        s.expect("hovering the background presents no frame",
                 off_frames == 0, "frames=%d" % off_frames)
        s.expect("hovering onto the nav cube presents a frame",
                 entry_frames >= 1, "frames=%d" % entry_frames)
        s.expect("hovering across nav cube faces presents frames",
                 sweep_frames >= 1, "frames=%d" % sweep_frames)
        s.expect("re-hovering the same face presents no frame",
                 repeat_frames == 0, "frames=%d" % repeat_frames)
        s.expect("the nav cube hover highlight state changed",
                 data.get("state_changed") in (None, 1),
                 "state_changed=%s" % data.get("state_changed"))
        log("frames off=%d entry=%d sweep=%d repeat=%d (total hover=%d)"
            % (off_frames, entry_frames, sweep_frames, repeat_frames,
               hover_frames))
        s.snapshot()
        s.finish("hover frames=%d" % hover_frames)
        FreeCADGui.getMainWindow().close()
        return
    QtCore.QTimer.singleShot(400, step)


QtCore.QTimer.singleShot(500, step)
