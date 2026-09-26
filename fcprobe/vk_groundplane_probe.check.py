#!/usr/bin/env python3
"""Host-side assertions for vk_groundplane_probe.py (SoGroundPlane grid).

Asserts:
  - the ``hasGroundPlane()`` state flipped 0 -> 1 when ShowGroundPlane was set;
  - the frame dumped with the grid on differs from the frame with it off (the
    grid actually rendered, not just the flag flipping).

Requires FC_VULKAN_DUMP_FRAME=1.
"""

import glob
import os
import re

from PIL import Image

PHASE = re.compile(r"\[HARNESS\] frame_phase phase=(\S+) frame=(\d+)")
GP = re.compile(r"\[HARNESS\] groundplane phase=(\S+) on=(\d+) has=(\d+)")
MIN_MEAN_DIFF = 0.3


def _frame_path(frames_dir, ordinal):
    files = glob.glob(os.path.join(frames_dir, "vk_frame_*.png"))
    best = None
    best_score = None
    for path in files:
        try:
            n = int(os.path.basename(path)[len("vk_frame_"):-len(".png")])
        except ValueError:
            continue
        score = n if n <= ordinal else -(n - ordinal)
        if best is None or score > best_score:
            best, best_score = path, score
    return best


def _mean_abs_diff(a, b):
    pa, pb = a.getdata(), b.getdata()
    total = 0
    for (r1, g1, b1), (r2, g2, b2) in zip(pa, pb):
        total += abs(r1 - r2) + abs(g1 - g2) + abs(b1 - b2)
    return total / (3.0 * max(len(pa), 1))


def check(lines, report):
    def err(msg):
        report.add_error(msg)

    gp = {}
    for line in lines:
        m = GP.search(line)
        if m:
            gp[m.group(1)] = int(m.group(3))
    if gp.get("off") != 0:
        err("hasGroundPlane() was not False in the off phase (has=%s)"
            % gp.get("off"))
    if gp.get("on") != 1:
        err("hasGroundPlane() was not True after ShowGroundPlane was set "
            "(has=%s)" % gp.get("on"))

    phases = {}
    for line in lines:
        m = PHASE.search(line)
        if m:
            phases[m.group(1)] = int(m.group(2))
    if "ground-off" not in phases or "ground-on" not in phases:
        err("probe did not mark both ground-plane phases")
        return

    frames_dir = os.path.join(report.artifact_dir, "frames")
    off_path = _frame_path(frames_dir, phases["ground-off"])
    on_path = _frame_path(frames_dir, phases["ground-on"])
    if not off_path or not on_path:
        err("no frame dumps for the ground-plane phases "
            "(is FC_VULKAN_DUMP_FRAME=1 set?)")
        return

    off = Image.open(off_path).convert("RGB")
    on = Image.open(on_path).convert("RGB")
    diff = _mean_abs_diff(off, on)
    report.session["groundplane_frame_diff"] = round(diff, 4)
    if diff < MIN_MEAN_DIFF:
        err("grid-on frame is indistinguishable from grid-off "
            "(mean abs diff %.4f < %.2f); the grid did not render"
            % (diff, MIN_MEAN_DIFF))
