#!/usr/bin/env python3
"""Host-side assertions for vk_prefs_probe.py (Vulkan display prefs read+render).

The probe cycles the Vulkan-only View prefs (VulkanEdgeOverlay / VulkanShowPoints
/ VulkanEdgeColor) while rendering a Part::Box, emitting a `[HARNESS] frame_phase`
per phase and dumping frames.  Two invariants:

  - Code path: the `[VK-TRACE] View3DInventorViewer::applyVulkanSettings` breadcrumb
    must have recorded the edgeOverlay=0->1 (and points=1) transitions the probe made.
  - Render: with the wireframe overlay on, at least one dumped frame must contain
    >= `MIN_PX` red-dominant edge pixels (the overlays actually drew); with it off
    (baseline) some frame must have none (so a stuck-on overlay is caught).

Run via the suite with FC_VULKAN_BREADCRUMBS=1 (so the applyVulkanSettings
breadcrumb is emitted into the trace log, which the harness folds into the run
events) and FC_VULKAN_DUMP_FRAME=1 (so frames are dumped).
"""

import glob
import os
import re

EDGE_LINE = re.compile(
    r"\[VK-TRACE\] View3DInventorViewer::applyVulkanSettings "
    r"edgeOverlay=(\d+) points=(\d+)")
PHASE_LINE = re.compile(r"\[HARNESS\] frame_phase phase=(\S+) frame=(\d+)")
MIN_PX = 50


def _breadcrumbs(lines):
    # [(edgeOverlay, points)] for every applyVulkanSettings record.
    return [(int(m.group(1)), int(m.group(2)))
            for line in lines for m in [EDGE_LINE.search(line)] if m]


def _edge_counts(frames_dir):
    """[(frame_ordinal, red_dominant_px)] for every dumped frame, by ordinal."""
    try:
        from PIL import Image
    except ImportError:
        return None
    import numpy as np
    out = []
    for p in glob.glob(os.path.join(frames_dir, "*.png")):
        m = re.search(r"(\d+)", os.path.basename(p))
        if not m:
            continue
        ordv = int(m.group(1))
        a = np.asarray(Image.open(p).convert("RGB"), dtype=np.int32)
        # The overlay draws 1px lines, which the rasterizer anti-aliases, so a
        # partial-coverage edge pixel blends toward the dark background (e.g.
        # (199,8,8) or (185,44,46)) and is not exactly (255,0,0).  Count
        # red-dominant pixels instead.
        r, g, b = a[..., 0], a[..., 1], a[..., 2]
        out.append((ordv, int(((r >= 120) & (r >= g + 40) & (r >= b + 40)).sum())))
    return sorted(out)


def check(lines, report):
    def err(msg):
        report.add_error(msg)

    crumbs = _breadcrumbs(lines)
    if not crumbs:
        err("no applyVulkanSettings breadcrumb (code path never ran; "
            "is FC_VULKAN_BREADCRUMBS=1 set?)")
        return

    edge_on = [e for e in crumbs if e[0] == 1]
    edge_off = [e for e in crumbs if e[0] == 0]
    points_on = [p for p in crumbs if p[1] == 1]
    if not edge_on:
        err("applyVulkanSettings never recorded edgeOverlay=1")
    if not edge_off:
        err("applyVulkanSettings never recorded edgeOverlay=0 (baseline)")
    if not points_on:
        err("applyVulkanSettings never recorded points=1")

    frames_dir = os.path.join(report.artifact_dir, "frames")
    counts = _edge_counts(frames_dir)
    if counts is None:
        err("edge-count check skipped: PIL/numpy not available")
        return
    if not counts:
        err("no frame dumps to analyze (is FC_VULKAN_DUMP_FRAME=1 set?)")
        return

    # Attribute each dumped frame to a phase.  The baseline is NOT assumed to be
    # strictly zero: the 3D scene itself may draw a few red-dominant pixels
    # (e.g. the origin/axis cross), so the invariant is a DELTA -- the edge-on
    # frames must add edge pixels over the edge-off baseline.
    marks = [(int(m.group(2)), m.group(1))
             for line in lines for m in [PHASE_LINE.search(line)] if m]
    if not marks:
        err("no [HARNESS] frame_phase markers (cannot attribute dumps to phases)")
        return

    # The probe stamps each phase marker at the END of the phase (after its
    # frames are rendered), so a dumped frame belongs to the FIRST marker whose
    # ordinal is >= the frame ordinal -- the phase it was rendered for.
    ordered_marks = sorted(marks)

    def phase_of(ford):
        for ordv, name in ordered_marks:
            if ordv >= ford:
                return name
        return ordered_marks[-1][1] if ordered_marks else "boot"

    bucketed = {}
    for ford, c in counts:
        bucketed.setdefault(phase_of(ford), []).append(c)

    off = max(bucketed.get("baseline", [0]), default=0)
    on = [c for name, cs in bucketed.items() if name != "baseline" for c in cs]
    on_max = max(on, default=0)
    report.session["prefs_edge_px"] = {
        "baseline_max": off, "edge_on_max": on_max,
        "by_phase": {k: max(v) for k, v in bucketed.items()},
    }
    if on_max < MIN_PX:
        err(f"no edge-on frame renders red edge pixels"
            f" (max {on_max} px, need >= {MIN_PX})")
    if on_max <= off:
        err(f"edge-on frames (max {on_max} px) did not exceed the edge-off "
            f"baseline ({off} px): edge overlay not drawn or stuck on")
