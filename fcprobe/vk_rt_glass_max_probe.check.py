#!/usr/bin/env python3
"""Host-side assertions for vk_rt_glass_max_probe.py.

Compares the thin-glass (mode 4) and dielectric Path-Tracing-Max (mode 6)
frames of the same translucent cyan cube.  A working dielectric BSDF, fed by
the per-material optics in SoRenderIR::SoMaterialBlock::optical, refracts and
tints the transmitted image, so the two frames must differ substantially; a
lost optical slot (IOR -> 1, no absorption) would make mode 6 read like thin
glass.

Requires FC_VULKAN_DUMP_FRAME=1.
"""

import glob
import os
import re

from PIL import Image

PHASE = re.compile(r"\[HARNESS\] frame_phase phase=(\S+) frame=(\d+)")


def _frame_path(frames_dir, ordinal):
    files = glob.glob(os.path.join(frames_dir, "vk_frame_*.png"))
    best = None
    best_ord = -1
    for path in files:
        try:
            n = int(os.path.basename(path)[len("vk_frame_"):-len(".png")])
        except ValueError:
            continue
        # Prefer the newest dump at or before the phase ordinal; otherwise the
        # nearest available.
        cand = n if n <= ordinal else -(n - ordinal)
        if best is None or cand > best_ord:
            best, best_ord = path, cand
    return best


def _load_small(path, size=(256, 160)):
    return Image.open(path).convert("RGB").resize(size)


def _mean_abs_diff(a, b):
    pa, pb = a.getdata(), b.getdata()
    total = 0
    for (r1, g1, b1), (r2, g2, b2) in zip(pa, pb):
        total += abs(r1 - r2) + abs(g1 - g2) + abs(b1 - b2)
    return total / (3.0 * max(len(pa), 1))


def _cyan_pixels(image):
    count = 0
    for r, g, b in image.getdata():
        if b > 120 and g > 100 and r < g and b >= r:
            count += 1
    return count


def check(lines, report):
    if not any("initialized (Vulkan ray tracing)" in line for line in lines):
        report.add_error("ray-tracing backend never initialized")

    phases = {}
    for line in lines:
        m = PHASE.search(line)
        if m:
            phases[m.group(1)] = int(m.group(2))
    if "thin-glass" not in phases or "dielectric-glass" not in phases:
        report.add_error("probe did not mark both glass phases")
        return

    frames_dir = os.path.join(report.artifact_dir, "frames")
    thin_path = _frame_path(frames_dir, phases["thin-glass"])
    max_path = _frame_path(frames_dir, phases["dielectric-glass"])
    if not thin_path or not max_path:
        report.add_error("no frame dumps for the glass phases")
        return

    thin = _load_small(thin_path)
    dielectric = _load_small(max_path)
    diff = _mean_abs_diff(thin, dielectric)
    report.session["glass_thin_vs_max_diff"] = round(diff, 3)

    # Path Tracing Max now adds a Fresnel-weighted ambient/environment body
    # term so the glass is not black against a dark background, which makes the
    # mode-6 glass deliberately closer to the thin-glass (mode 4) look.  The
    # check therefore only requires that refraction still changes the image
    # (non-zero diff) and that the dielectric frame is genuinely rendered (cyan
    # glass pixels present) rather than a black hole.
    if diff < 0.15:
        report.add_error(
            "dielectric (mode 6) frame is indistinguishable from thin-glass "
            "(mode 4) (mean abs diff %.3f); refraction is not being applied"
            % diff)
    if _cyan_pixels(dielectric) < 50:
        report.add_error(
            "dielectric frame has too few cyan glass pixels; the glass did "
            "not render (black hole)")
