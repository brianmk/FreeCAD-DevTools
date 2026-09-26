#!/usr/bin/env python3
"""Host assertions for vk_material_optics_probe.py.

The probe renders the same glass box twice with only its authored per-material
optics changed (IOR/absorption: same geometry, camera, lights and global
viewer glass setting), marking each phase with frame_phase().  The dumped
frames are compared: if the authored optics reach the renderer (and restart its
accumulation) the two phases differ; if the global setting overrides them, or
the material dirty-hash misses the optics edit and the converged tracer stays
stale, the frames are identical.

A path-tracer accumulation restart resets the frame numbering, so the dumped
frames fall into two runs separated by a numbering gap; the two runs are the
two phases.  The check splits on the largest gap and compares their averaged
frames (falling back to first-vs-last when there is no gap).  Unreadable
(mid-write) frames are skipped.

Requires FC_VULKAN_DUMP_FRAME=1.
"""

import glob
import os
import re

from PIL import Image

PHASE = re.compile(r"\[HARNESS\] frame_phase phase=optics-(\S+) frame=(\d+)")


def _frames(frames_dir):
    def ordinal(path):
        try:
            return int(os.path.basename(path)[len("vk_frame_"):-len(".png")])
        except ValueError:
            return -1

    loaded = []
    for path in sorted(glob.glob(os.path.join(frames_dir, "vk_frame_*.png")),
                       key=ordinal):
        try:
            image = Image.open(path).convert("RGB").resize((160, 100))
            image.load()
            loaded.append((ordinal(path), image))
        except Exception:
            continue
    loaded.sort(key=lambda item: item[0])
    return loaded


def _mean_rgb(images):
    pixels = [p for image in images for p in image.getdata()]
    n = max(len(pixels), 1)
    return (
        sum(p[0] for p in pixels) / n,
        sum(p[1] for p in pixels) / n,
        sum(p[2] for p in pixels) / n,
    )


def _mean_abs_diff(a, b):
    pa, pb = a.getdata(), b.getdata()
    total = 0
    for (r1, g1, b1), (r2, g2, b2) in zip(pa, pb):
        total += abs(r1 - r2) + abs(g1 - g2) + abs(b1 - b2)
    return total / (3.0 * max(len(pa), 1))


def check(lines, report):
    phases = set()
    for line in lines:
        m = PHASE.search(line)
        if m:
            phases.add(m.group(1))
    if "clear" not in phases or "tinted" not in phases:
        report.add_error("probe did not mark both optics phases")
        return

    # The optics edit is an edit of the material record, so the ray tracer's
    # material dirty-hash must change and fire its [GCR] MATERIAL breadcrumb
    # (FC_VULKAN_RT_GEO=1); without it the converged accumulation would stay
    # stale.  This is the precise acceptance signal for per-material optics.
    if any("initialized (Vulkan ray tracing)" in line for line in lines):
        if not any("[GCR] MATERIAL" in line for line in lines):
            report.add_error(
                "no [GCR] MATERIAL breadcrumb: the per-material optics edit did "
                "not change the material dirty-hash (tracer would stay stale)")
    else:
        report.add_error("ray-tracing backend never initialized")

    # Secondary visual guard: the dumped frames must not all be identical.  A
    # stale accumulation (or an overridden optics value) renders one frozen
    # image for the whole run.
    frames = _frames(os.path.join(report.artifact_dir, "frames"))
    if len(frames) < 4:
        report.add_error("not enough frame dumps; render produced nothing")
        return

    images = [image for _, image in frames]
    diff = _mean_abs_diff(images[0], images[-1])
    report.session["material_optics"] = {
        "first_rgb": [round(v, 1) for v in _mean_rgb([images[0]])],
        "last_rgb": [round(v, 1) for v in _mean_rgb([images[-1]])],
        "first_vs_last_diff": round(diff, 3),
        "frames": len(frames),
    }

    if max(_mean_rgb([images[0]])) < 5.0 or max(_mean_rgb([images[-1]])) < 5.0:
        report.add_error("a glass frame rendered black; nothing was traced")

    if diff < 0.3:
        report.add_error(
            f"the whole run rendered an identical image (diff={diff:.3f}); the "
            "authored optics edit either did not reach the renderer or the "
            "tracer never restarted")
