#!/usr/bin/env python3
"""CPU-only smoke probe: run headless under ``FreeCADCmd`` (no GUI, no GPU).

Unlike the other probes this one does not import ``FreeCADGui`` at all, so no
OpenGL/Vulkan context is ever created.  It exercises CPU-side work -- OCC
boolean modelling and BRep tessellation -- and prints a unified verdict.

Run:
  python3 tools/fcprobe/freecad_probe.py run \\
      tools/fcprobe/vk_cpu_cmd_probe.py --binary <build>/bin/FreeCADCmd

The host check asserts the CPU work markers were produced and that no GPU
context/breadcrumb appears in the log.
"""

import sys

import FreeCAD


def out(msg):
    # sys.__stdout__: FreeCADCmd redirects sys.stdout to its console, so a
    # plain print() may not reach the harness.
    sys.__stdout__.write(msg + "\n")
    sys.__stdout__.flush()


def main():
    ok = True
    try:
        doc = FreeCAD.newDocument("CpuCmd")
        box = doc.addObject("Part::Box", "Box")
        box.Length = box.Width = box.Height = 10

        cyl = doc.addObject("Part::Cylinder", "Cyl")
        cyl.Radius = 3
        cyl.Height = 20
        cyl.Placement.Base = FreeCAD.Vector(5, 5, -5)

        cut = doc.addObject("Part::Cut", "Cut")
        cut.Base = box
        cut.Tool = cyl
        doc.recompute()

        shape = cut.Shape
        volume = shape.Volume
        faces = len(shape.Faces)
        vertices, triangles = shape.tessellate(0.5)
        out("[CPU-CMD] volume=%.3f faces=%d tris=%d"
            % (volume, faces, len(triangles)))

        if not (0.0 < volume < 1000.0):
            ok = False
            out("[CPU-CMD] unexpected cut volume %.3f" % volume)
        if faces < 7:
            ok = False
            out("[CPU-CMD] unexpected face count %d" % faces)
        if not triangles:
            ok = False
            out("[CPU-CMD] tessellation produced no triangles")
    except Exception as exc:  # noqa: BLE001
        ok = False
        out("[CPU-CMD] error: %s" % exc)

    out("[VERDICT] cpu-cmd %s" % ("PASS" if ok else "FAIL"))


main()
