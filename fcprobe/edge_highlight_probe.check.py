#!/usr/bin/env python3
"""Host-side assertions for edge_highlight_probe.py.

A committed edge selection is coplanar with the faces it separates, so without
the depth-range decal a 90 degree seam edge loses most of its highlight pixels
to the depth comparison: the line is drawn but only a fraction survives, and
the user sees "the highlight happens but is invisible".  The probe captures one
PNG per selection state; this check counts highlight pixels per state and
asserts the *shape* of the result rather than absolute numbers, so it stays
valid across GPUs, window sizes and drivers:

* ``none`` is the baseline (whatever chrome happens to be highlight-coloured).
* every selected edge must be either clearly visible (>= VISIBLE_MIN pixels,
  comfortably above the baseline) or clearly hidden (<= baseline + HIDDEN_SLACK,
  i.e. an edge occluded by the body, which must stay hidden).  The 400..1500
  band is exactly the bug signature and is rejected.
* at least MIN_VISIBLE edges must be in the visible band, otherwise the probe
  passed vacuously (nothing was selected, or the capture failed).
* every preselected edge must be drawn on top (DrawOnTop path, unchanged by the
  fix): this also proves the capture is not empty/black.
* a missing frame dump (``EDGEHL_WARN ... no_frame_dump``) fails the run: the
  Vulkan capture needs FREECAD_USE_VULKAN_DEBUG_HOOKS and FC_VULKAN_DUMP_FRAME.

The check needs the PNGs the probe wrote to ``$EDGEHL_OUT`` (default
/tmp/edgehl) and numpy/Pillow on the host; it only looks at files named by
markers from *this* run, so stale files from an earlier run are ignored.
"""

import os
import re

CASE = re.compile(r"EDGEHL_CASE mode=(\w+) case=(\S+) file=(\S+)")
WARN = re.compile(r"EDGEHL_WARN mode=(\w+) case=(\S+) no_frame_dump")
DONE = re.compile(r"EDGEHL_DONE mode=(\w+) cases=(\d+)")

BASELINE = "none"
HIDDEN_SLACK = 80
VISIBLE_MIN = 1500
PRESELECT_MIN = 1200
MIN_VISIBLE = 6


def _highlight_pixels(path):
    import numpy as np
    from PIL import Image

    a = np.asarray(Image.open(path).convert("RGB")).astype("int16")
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    # the overlay is emissive: clearly blue/cyan and clearly not grey background
    return int(np.count_nonzero((b >= 120) & ((b - r) >= 50)))


def check(lines, report):
    cases = {}
    for line in lines:
        m = CASE.search(line)
        if m:
            cases[(m.group(1), m.group(2))] = m.group(3)
        m = WARN.search(line)
        if m:
            report.add_error(
                "edge_highlight: no frame dump for %s/%s - build with "
                "FREECAD_USE_VULKAN_DEBUG_HOOKS=ON and set FC_VULKAN_DUMP_FRAME=1",
                m.group(1),
                m.group(2),
            )

    done = {m.group(1): int(m.group(2)) for m in (DONE.search(x) for x in lines) if m}
    if not done:
        report.add_error("edge_highlight: the probe did not finish (no EDGEHL_DONE)")
    if not cases:
        report.add_error("edge_highlight: no capture markers in the probe output")
        return

    try:
        counts = {key: _highlight_pixels(path) for key, path in cases.items()}
    except ImportError as exc:
        report.add_error("edge_highlight: numpy/Pillow unavailable on the host: %s", exc)
        return
    except OSError as exc:
        report.add_error("edge_highlight: could not read a capture: %s", exc)
        return

    for mode in sorted({key[0] for key in counts}):
        per_mode = {case: px for (m, case), px in counts.items() if m == mode}
        baseline = per_mode.get(BASELINE)
        if baseline is None:
            report.add_error("edge_highlight[%s]: no %s baseline case", mode, BASELINE)
            continue

        selected = {c: px for c, px in per_mode.items() if c.startswith("sel_Edge")}
        preselected = {c: px for c, px in per_mode.items() if c.startswith("pre_Edge")}
        visible = 0
        for case, px in sorted(selected.items()):
            if px <= baseline + HIDDEN_SLACK:
                continue  # edge occluded by the body: correctly invisible
            if px < VISIBLE_MIN:
                report.add_error(
                    "edge_highlight[%s]: %s has %d highlight px, between the hidden "
                    "band (<= %d) and the visible floor (%d): the highlight is drawn "
                    "but mostly lost to the depth test",
                    mode,
                    case,
                    px,
                    baseline + HIDDEN_SLACK,
                    VISIBLE_MIN,
                )
                continue
            visible += 1
        if visible < MIN_VISIBLE:
            report.add_error(
                "edge_highlight[%s]: only %d edge highlight(s) clearly visible "
                "(need >= %d): nothing was measured",
                mode,
                visible,
                MIN_VISIBLE,
            )
        for case, px in sorted(preselected.items()):
            if px < PRESELECT_MIN:
                report.add_error(
                    "edge_highlight[%s]: %s (preselection, drawn on top) has only %d px "
                    "- the capture looks empty or the scene was not rendered",
                    mode,
                    case,
                    px,
                )
