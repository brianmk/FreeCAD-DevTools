#!/usr/bin/env python3
"""Host assertions for vk_physical_material_probe.py.

Parses the `[HARNESS] frame_phase phase=phys-m<metalness> frame=<n>` markers,
maps each step to the frame dumped just after its marker (FC_VULKAN_DUMP_FRAME,
provided by the suite entry) and counts highlight pixels above a fixed
threshold.  With roughness fixed, raising metalness raises the specular
reflectance, so the bright-highlight area must grow monotonically.  Asserts:

  - at least three metalness phases were dumped;
  - the highlight count is monotonically non-decreasing with metalness (small
    per-step tolerance for raster noise);
  - the count actually grows across the sweep.

Requires FC_VULKAN_DUMP_FRAME=1.
"""

import glob
import os
import re

from PIL import Image

PHASE = re.compile(r"\[HARNESS\] frame_phase phase=phys-m([0-9.]+) frame=(\d+)")
SATURATION = 120


def _frame_numbers(frames_dir):
    numbers = {}
    for path in glob.glob(os.path.join(frames_dir, "vk_frame_*.png")):
        try:
            n = int(os.path.basename(path)[len("vk_frame_"):-len(".png")])
        except ValueError:
            continue
        numbers[n] = path
    return numbers


def _highlight(path, threshold):
    image = Image.open(path).convert("RGB").resize((320, 200))
    count = 0
    for r, g, b in image.getdata():
        if (r + g + b) / 3.0 > threshold:
            count += 1
    return count


def check(lines, report):
    phases = []
    for line in lines:
        m = PHASE.search(line)
        if m:
            phases.append((float(m.group(1)), int(m.group(2))))
    if len(phases) < 3:
        report.add_error(
            f"only {len(phases)} physical-material phase(s) dumped; expected >= 3")
        return

    phases.sort(key=lambda p: p[0])
    if any(phases[i][0] >= phases[i + 1][0] for i in range(len(phases) - 1)):
        report.add_error("physical-material metalness phases were not ascending")

    frames_dir = os.path.join(report.artifact_dir, "frames")
    numbers = _frame_numbers(frames_dir)
    if not numbers:
        report.add_error("no frame dumps; render produced nothing")
        return

    ordered = sorted(numbers)
    counts = []
    for i, (_, ordinal) in enumerate(phases):
        limit = phases[i + 1][1] - 1 if i + 1 < len(phases) else ordered[-1]
        candidates = [n for n in ordered if ordinal <= n <= limit]
        if not candidates:
            candidates = [n for n in ordered if n <= ordinal]
        if not candidates:
            counts.append(None)
            continue
        counts.append(_highlight(numbers[max(candidates)], SATURATION))

    report.session["physical_material_highlight"] = [
        {"metalness": m, "count": c} for (m, _), c in zip(phases, counts)
    ]

    if any(c is None for c in counts):
        report.add_error("missing frame dump for a physical-material phase")
        return

    span = max(counts) - min(counts)
    if span < 20:
        report.add_error(
            f"highlight area barely changed across the metalness sweep "
            f"(counts={counts}); the material is not responding")

    tolerance = max(10, span // 20)
    for i in range(len(counts) - 1):
        if counts[i + 1] < counts[i] - tolerance:
            report.add_error(
                f"highlight did not grow monotonically with metalness: "
                f"{phases[i][0]} count={counts[i]} -> {phases[i + 1][0]} "
                f"count={counts[i + 1]} (tol={tolerance})")
