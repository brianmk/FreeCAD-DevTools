#!/usr/bin/env python3
"""Host-side assertions for edge_highlight_probe.py.

A committed edge selection is coplanar with the faces it separates, so without
the depth-range decal a 90 degree seam edge loses most of its highlight pixels
to the depth comparison: the line is drawn but only a fraction survives, and the
user sees "the highlight happens but is invisible".  The probe captures one PNG
per selection state; this check counts highlight pixels per state and compares
each selected edge against *its own* preselection capture, so the assertion
scales with window size, device pixel ratio, line length and driver instead of
resting on absolute pixel counts:

* ``none`` is the baseline (whatever chrome happens to be highlight-coloured).
* ``pre_EdgeN`` is the same edge drawn on top (the DrawOnTop path is unchanged
  by the fix): the "fully visible" reference for that edge.
* ``sel_EdgeN`` must be either clearly hidden (<= baseline + HIDDEN_SLACK, an
  edge occluded by the body, which must stay hidden) or keep at least
  COVERAGE_MIN of that edge's preselection count.  Above the hidden band but
  below the coverage floor is exactly the bug signature: drawn, but mostly lost
  to the depth test.
* at least MIN_COVERED selected edges must clear the floor, or the probe passed
  vacuously (nothing was selected, or the capture failed).
* every preselected edge must be drawn (>= PRESELECT_MIN px): this also proves
  the capture is not empty/black.
* a missing frame dump (``EDGEHL_WARN ... no_frame_dump``) fails the run: the
  Vulkan capture needs FREECAD_USE_VULKAN_DEBUG_HOOKS and FC_VULKAN_DUMP_FRAME.

Threshold derivation.  Measured on the probe's built-in 20 mm box, NVIDIA raster
Vulkan under Xvfb, ~1330x836 viewport, the same run with and without the decal
(revert ``SoBrepOverlayHelpers.h`` back to a 1.0 far depth range):

    state                     with decal     without decal
    none (baseline)                  84                 84
    pre_EdgeN                1623..1660         1623..1660
    sel_EdgeN (visible)       870..1656           531..1656
    sel_EdgeN / pre_EdgeN     0.52..1.00          0.33..1.00

An absolute pixel floor cannot separate those two: without the decal nine edges
still measure above 500 px (531, 575, 870, 870, 920, 941, 1475, 1610, 1656), so
a ">= 400..500 px, at least 6 edges" rule passes on a build that is missing the
fix.  The fraction of the same edge's preselection count does separate them: the
edges the decal does not touch stay at 0.52-1.00 either way, while the seam edges
it rescues fall to 0.33-0.35 without it.  COVERAGE_MIN = 0.45 is the midpoint of
that gap, leaving ~15% margin on the passing side and ~25% on the failing side.

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
# px above the baseline that still counts as "occluded by the body"; the
# measured occluded edges sit at baseline+0..1.
HIDDEN_SLACK = 80
# Fraction of the same edge's preselection count a selected edge must keep.
COVERAGE_MIN = 0.45
# Absolute floor for the preselection reference itself, so an empty/black
# capture fails loudly; the measured band is 1623..1660.
PRESELECT_MIN = 1200
# How many selected edges must clear the coverage floor.
MIN_COVERED = 6


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
        hidden_band = baseline + HIDDEN_SLACK

        covered = 0
        for case, px in sorted(selected.items()):
            if px <= hidden_band:
                continue  # edge occluded by the body: correctly invisible
            edge = case[len("sel_"):]
            reference_case = "pre_" + edge
            reference = preselected.get(reference_case)
            if reference is None:
                report.add_error(
                    "edge_highlight[%s]: no preselection reference %s for %s - the "
                    "probe must capture both states for every edge",
                    mode,
                    reference_case,
                    case,
                )
                continue
            if reference < PRESELECT_MIN:
                # A bad reference is reported by the preselection loop below; the
                # coverage test for this edge would be meaningless.
                continue
            coverage = px / reference
            if coverage < COVERAGE_MIN:
                report.add_error(
                    "edge_highlight[%s]: %s keeps only %.2f of its preselection "
                    "reference (%d/%d px) - above the hidden band (<= %d) but below "
                    "the %.2f floor: the highlight is drawn but mostly lost to the "
                    "depth test",
                    mode,
                    case,
                    coverage,
                    px,
                    reference,
                    hidden_band,
                    COVERAGE_MIN,
                )
                continue
            covered += 1

        if covered < MIN_COVERED:
            report.add_error(
                "edge_highlight[%s]: only %d selected edge(s) keep >= %.2f of their "
                "preselection reference (need >= %d): nothing was measured",
                mode,
                covered,
                COVERAGE_MIN,
                MIN_COVERED,
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

        report.session.setdefault("edge_highlight", {})[mode] = {
            "baseline": baseline,
            "covered": covered,
            "coverage_min": COVERAGE_MIN,
            "min_coverage": min(
                (
                    px / preselected["pre_" + c[len("sel_"):]]
                    for c, px in selected.items()
                    if px > hidden_band and "pre_" + c[len("sel_"):] in preselected
                    and preselected["pre_" + c[len("sel_"):]] >= PRESELECT_MIN
                ),
                default=0.0,
            ),
        }
