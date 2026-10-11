#!/usr/bin/env python3
"""Retained replay must not serve a stale camera to annotation commands.

Every PartDesign preview (Draft, Fillet/Chamfer, Thickness, Pattern, Boolean,
datum labels, transform draggers -- anything drawn through Gui::So3DAnnotation)
is recorded inline and then promoted to the OVERLAY render pass while staying in
the retained main list.  On a camera-only frame that list is replayed with the
view restamped into each command; the restamp used to skip OVERLAY-pass
commands, so those annotations kept the *previous* camera and a preview was
drawn where the old camera had put it.

The renderer reports the counts on every replayed frame when the backend debug
log is on:

  [RTDBG] retained=<n> retainedOverlay=<n> staleOverlayBefore=<n> \
          staleOverlayAfter=<n> restamped=<n>

This probe opens a preview and moves the camera between phases; the adjacent
check asserts `staleOverlayAfter` stays 0 while annotations are present.

Markers on stdout (fd 1):
  PREVIEWRESTAMP phase=<name> preview=<draft|fillet>

Run (the debug log is required for the counters):
  FC_VULKAN_DUMP_FRAME= COIN_VULKAN_BACKEND_DEBUG=1 \\
  build-freecad/bin/FreeCAD vk_annotation_restamp_probe.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import FreeCAD
import FreeCADGui as Gui
import Part
import Sketcher
from PySide import QtCore
from freecad_probe import Session


def emit(line):
    try:
        os.write(1, (line + "\n").encode())
    except OSError:
        pass


def rectangle(sketch):
    sketch.addGeometry(
        [
            Part.LineSegment(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(40, 0, 0)),
            Part.LineSegment(FreeCAD.Vector(40, 0, 0), FreeCAD.Vector(40, 30, 0)),
            Part.LineSegment(FreeCAD.Vector(40, 30, 0), FreeCAD.Vector(0, 30, 0)),
            Part.LineSegment(FreeCAD.Vector(0, 30, 0), FreeCAD.Vector(0, 0, 0)),
        ],
        False,
    )
    sketch.addConstraint(
        [
            Sketcher.Constraint("Coincident", 0, 2, 1, 1),
            Sketcher.Constraint("Coincident", 1, 2, 2, 1),
            Sketcher.Constraint("Coincident", 2, 2, 3, 1),
            Sketcher.Constraint("Coincident", 3, 2, 0, 1),
        ]
    )


def pose():
    cam = Gui.activeView().getCameraNode()
    pos = cam.position.getValue()
    quat = cam.orientation.getValue().getValue()
    return (pos[0], pos[1], pos[2]) + quat


def move_camera():
    view = Gui.activeView()
    view.viewIsometric()
    view.fitAll()
    Gui.updateGui()
    QtCore.QCoreApplication.processEvents()


def phase(name, preview):
    Gui.updateGui()
    QtCore.QCoreApplication.processEvents()
    p = pose()
    emit("PREVIEWRESTAMP phase=%s preview=%s camera=%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f"
         % ((name, preview) + p))


def run(session):
    doc = FreeCAD.newDocument("AnnotationRestamp")
    body = doc.addObject("PartDesign::Body", "Body")
    sketch = body.newObject("Sketcher::SketchObject", "Sketch")
    rectangle(sketch)
    doc.recompute()

    pad = body.newObject("PartDesign::Pad", "Pad")
    pad.Profile = sketch
    pad.Length = 20.0
    doc.recompute()

    Gui.activateView("Gui::View3DInventor", True)
    Gui.activeView().viewIsometric()
    Gui.activeView().fitAll()

    # A Draft preview (dress-up) and a Fillet preview (dress-up): both draw
    # through PartGui::SoPreviewShape -> Gui::So3DAnnotation.
    draft = body.newObject("PartDesign::Draft", "Draft")
    draft.Base = (pad, ["Face6"])
    draft.Angle = 10.0
    doc.recompute()
    Gui.ActiveDocument.setEdit(draft.Name)
    QtCore.QCoreApplication.processEvents()
    phase("draft_pose_a", "draft")
    move_camera()
    phase("draft_pose_b", "draft")
    Gui.Control.closeDialog()
    QtCore.QCoreApplication.processEvents()

    fillet = body.newObject("PartDesign::Fillet", "Fillet")
    fillet.Base = (draft, ["Edge1", "Edge2"])
    fillet.Radius = 3.0
    doc.recompute()
    Gui.ActiveDocument.setEdit(fillet.Name)
    QtCore.QCoreApplication.processEvents()
    phase("fillet_pose_a", "fillet")
    move_camera()
    phase("fillet_pose_b", "fillet")
    Gui.Control.closeDialog()
    QtCore.QCoreApplication.processEvents()

    session.finish()
    session.close()


Session.deferred("annotation_restamp", run)
