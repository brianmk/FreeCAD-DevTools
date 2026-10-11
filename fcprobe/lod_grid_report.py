#!/usr/bin/env python3
"""Analyze a vk_grid_lod_probe.py run log for interaction-LOD evidence.

Reports per probe phase:
  * cameraChangedCB notifications (`[LTRACE] cameraChangedCB`, the sensor on the
    camera node fires for *any* camera field write) and real pose changes
    (`[LODTRACE] cameraPose`, only with FC_VULKAN_LOD_TRACE=1) -- a phase with
    notifications but no pose change is a camera write that is not a move
    (auto-clipping rewrites near/far on ordinary frames).
  * interaction-LOD transitions (`[LODTRACE] interactionLod=`).
  * for line commands of a given width (default 2.00 = the Sketcher grid's
    division lines): draws recorded with wideLine=1 (full width) vs wideLine=0
    (interaction-LOD 1px downgrade).

Usage: analyze_lod.py <run.log> [--width 2.00]
"""

import argparse
import re
import sys
from collections import Counter, OrderedDict

PHASE_RE = re.compile(r"^GRID phase=(\S+)")
CAM_RE = re.compile(r"\[LTRACE\] cameraChangedCB")
POSE_RE = re.compile(r"\[LODTRACE\] cameraPose")
LOD_RE = re.compile(r"\[LODTRACE\] interactionLod=(\d)")
VKBE_RE = re.compile(
    r"\[VKBE\] line/point cmd=(0x[0-9a-f]+) pass=(\d+) topo=(\d+) verts=(\d+) "
    r"diffuse=\(([^)]*)\) colorKey=(\d+) shading=(\d+) lineWidth=([0-9.]+) "
    r"pattern=(0x[0-9a-f]+) fillMode=(\d+)")
PUSH_RE = re.compile(
    r"\[PUSH\] cmd=(0x[0-9a-f]+) pass=(\d+) topo=(\d+) .*?wideLine=(\d+)")

FIELDS = ("cam", "pose", "lod_on", "lod_off", "wide1", "wide0", "recorded")


def empty():
    return {k: 0 for k in FIELDS}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--width", type=float, default=2.00,
                    help="line width to track (default: 2.00)")
    args = ap.parse_args()

    lines = open(args.log, "r", errors="replace").read().splitlines()

    # Pass 1: every command ever recorded at the tracked width (the grid's
    # division-line command; the retained-IR slots are reused, so this is a set
    # of draw-list addresses, not stable object ids).
    tracked = set()
    for line in lines:
        m = VKBE_RE.search(line)
        if m and abs(float(m.group(8)) - args.width) < 1e-6:
            tracked.add(m.group(1))

    phases = OrderedDict()
    pending = empty()
    pending_name = "setup"

    for line in lines:
        m = PHASE_RE.match(line)
        if m:
            # The probe prints its marker *after* the phase ran, so everything
            # accumulated since the previous marker belongs to this phase.
            name = m.group(1)
            bucket = phases.setdefault(name, empty())
            for key in FIELDS:
                bucket[key] += pending[key]
            pending = empty()
            pending_name = name
            continue
        s = pending
        if CAM_RE.search(line):
            s["cam"] += 1
            continue
        if POSE_RE.search(line):
            s["pose"] += 1
            continue
        m = LOD_RE.search(line)
        if m:
            s["lod_on" if m.group(1) == "1" else "lod_off"] += 1
            continue
        m = PUSH_RE.search(line)
        if m and m.group(1) in tracked:
            s["wide1" if m.group(4) == "1" else "wide0"] += 1
            continue
        m = VKBE_RE.search(line)
        if m and m.group(1) in tracked:
            s["recorded"] += 1

    if any(pending.values()):
        # Trailing lines after the last marker (the probe exiting).
        for key in FIELDS:
            phases.setdefault(pending_name + "+tail", empty())[key] += pending[key]

    print("tracked width-%.2f commands: %d" % (args.width, len(tracked)))
    print()
    print("%-14s %6s %6s %6s %6s %8s %6s %6s"
          % ("phase", "camCB", "poseCh", "lodOn", "lodOff", "recorded",
             "wide=1", "wide=0"))
    for name, s in phases.items():
        print("%-14s %6d %6d %6d %6d %8d %6d %6d"
              % (name, s["cam"], s["pose"], s["lod_on"], s["lod_off"],
                 s["recorded"], s["wide1"], s["wide0"]))
    print()
    tot = Counter()
    for s in phases.values():
        tot.update(s)
    print("totals: camCB=%d poseChanged=%d lodOn=%d lodOff=%d "
          "gridDivDraws(wide=%d thin=%d)"
          % (tot["cam"], tot["pose"], tot["lod_on"], tot["lod_off"],
             tot["wide1"], tot["wide0"]))


if __name__ == "__main__":
    sys.exit(main())
