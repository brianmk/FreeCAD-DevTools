#!/usr/bin/env python3
"""Host-side assertions for vk_grid_lod_probe.py (interaction LOD vs. wide grid lines).

The probe enters Sketcher edit mode (grid division lines are 2px by default),
drives both frame producers -- synthetic hover moves and a camera nudge -- and
marks each phase.  This check asserts:

  * the Sketcher grid's division-line command (the line command recorded at
    lineWidth 2.00) was rendered with the wide-line path (``wideLine=1``) in
    every hover phase and in the camera phase.  Interaction LOD must not
    downgrade it: a small wide line set is cheap to expand, and downgrading it
    makes the configured width vanish while the pointer moves (the reported
    bug).
  * interaction LOD itself still engages on real navigation (``lodOn >= 1``
    when the harness ran with FC_VULKAN_LOD_TRACE=1), so the assertions above
    cannot pass because the feature was switched off.

Requires COIN_VULKAN_BACKEND_DEBUG=1 (draw records).  Run with
FC_VULKAN_LOD_TRACE=1 to include the LOD-state assertions.
"""

import re

# Phases whose frames must keep the grid's wide lines.  `setup` is excluded:
# framing the view legitimately navigates the camera and may downgrade before
# the first settled frame.
WIDE_PHASES = ("hover_vertex", "hover_edge", "hover_stop", "camera_move")

PHASE = re.compile(r"^GRID phase=(\S+)")
VKBE = re.compile(
    r"\[VKBE\] line/point cmd=(0x[0-9a-f]+) .*?lineWidth=([0-9.]+) ")
PUSH = re.compile(r"\[PUSH\] cmd=(0x[0-9a-f]+) .*?wideLine=(\d)")
LOD = re.compile(r"\[LODTRACE\] interactionLod=(\d)")
POSE = re.compile(r"\[LODTRACE\] cameraPose")

TRACKED_WIDTH = 2.00
MIN_HOVER_DRAWS = 3

_COUNTERS = ("recorded", "wide", "thin", "lodOn", "poses")


def _bucket(lines):
    """Bucket draw records per probe phase.

    A phase marker is written *after* its phase ran, so records accumulate into
    the phase named by the next marker.  A command's width is taken from the
    [VKBE] record that immediately precedes each [PUSH] record: the retained-IR
    command slots are reused, so an address is not a stable command id.
    """
    buckets = {}
    pending = dict.fromkeys(_COUNTERS, 0)
    width_of = {}
    seen_widths = set()

    def flush(name):
        bucket = buckets.setdefault(name, dict.fromkeys(_COUNTERS, 0))
        for key in _COUNTERS:
            bucket[key] += pending[key]
            pending[key] = 0

    for line in lines:
        m = VKBE.search(line)
        if m:
            width = float(m.group(2))
            width_of[m.group(1)] = width
            if abs(width - TRACKED_WIDTH) < 1e-6:
                seen_widths.add(m.group(1))
            continue
        m = PUSH.search(line)
        if m:
            width = width_of.get(m.group(1))
            if width is not None and abs(width - TRACKED_WIDTH) < 1e-6:
                pending["recorded"] += 1
                if m.group(2) == "1":
                    pending["wide"] += 1
                else:
                    pending["thin"] += 1
            continue
        m = LOD.search(line)
        if m:
            if m.group(1) == "1":
                pending["lodOn"] += 1
            continue
        if POSE.search(line):
            pending["poses"] += 1
            continue
        m = PHASE.match(line)
        if m:
            flush(m.group(1))
    flush("tail")
    return buckets, seen_widths


def check(lines, report):
    buckets, seen_widths = _bucket(lines)

    if not seen_widths:
        report.add_error(
            "no line command was recorded at lineWidth %.2f: the Sketcher "
            "grid's division lines never reached the Vulkan backend (is "
            "COIN_VULKAN_BACKEND_DEBUG=1 set, and did the probe enter Sketcher "
            "edit mode with ShowGrid?)" % TRACKED_WIDTH)
        return

    total_recorded = sum(b["recorded"] for b in buckets.values())
    if total_recorded == 0:
        report.add_error("the tracked grid command was never drawn")
        return

    for phase in WIDE_PHASES:
        bucket = buckets.get(phase)
        if bucket is None:
            report.add_error("probe never reached phase %r" % phase)
            continue
        if bucket["thin"]:
            report.add_error(
                "phase %s rendered the grid's %.2fpx division lines %d time(s) "
                "through the plain 1px path (wide=%d): interaction LOD is "
                "downgrading a small wide line set"
                % (phase, TRACKED_WIDTH, bucket["thin"], bucket["wide"]))

    exercised = sum(buckets.get(p, {}).get("recorded", 0) for p in WIDE_PHASES)
    if exercised < MIN_HOVER_DRAWS:
        report.add_error(
            "only %d grid draws across the hover/camera phases (< %d): the "
            "probe did not exercise a moving pointer or camera"
            % (exercised, MIN_HOVER_DRAWS))

    # Interaction LOD must still engage on a real navigation, otherwise the
    # assertions above would pass trivially with the feature switched off.
    if any(POSE.search(line) for line in lines):
        lod_on = sum(b["lodOn"] for b in buckets.values())
        if lod_on == 0:
            report.add_error(
                "interaction LOD never engaged although the camera pose "
                "changed: the wide-line assertions above are vacuous")
    else:
        report.log_event("harness", "lod_trace_absent",
                         msg="FC_VULKAN_LOD_TRACE not set; LOD-state "
                             "assertions skipped")
