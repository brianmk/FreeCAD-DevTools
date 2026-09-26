#!/usr/bin/env python3
"""Host-side assertions for vk_cpu_cmd_probe.py (headless CPU-only run).

Asserts the CPU modelling/tessellation markers were produced and that no GPU
code path ran: a GUI/Vulkan bring-up would emit a `[VK-DEVICE]` selection
breadcrumb or a Vulkan renderer line, which must not appear in a FreeCADCmd
run.
"""

import re

WORK = re.compile(r"\[CPU-CMD\] volume=([\d.]+) faces=(\d+) tris=(\d+)")
GPU_MARKERS = ("[VK-DEVICE]", "[VK-PRESENT]", "initialized (Vulkan ray tracing)")


def check(lines, report):
    def err(msg):
        report.add_error(msg)

    works = [m for line in lines for m in [WORK.search(line)] if m]
    if not works:
        err("no [CPU-CMD] work marker (probe did not run its CPU work)")
    else:
        vol, faces, tris = works[-1].groups()
        report.session["cpu_cmd"] = {
            "volume": float(vol), "faces": int(faces), "tris": int(tris),
        }
        if int(tris) <= 0:
            err("tessellation produced 0 triangles")

    for marker in GPU_MARKERS:
        if any(marker in line for line in lines):
            err("GPU marker %r appeared in a CPU-only (FreeCADCmd) run"
                % marker)
