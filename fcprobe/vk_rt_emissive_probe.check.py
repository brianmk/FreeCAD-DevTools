#!/usr/bin/env python3
"""Host-side assertions for vk_rt_emissive_probe.py.

The scene's only light source is a red emissive map on a black-diffuse box, so
a dumped frame dominated by red proves the ray-traced backend sampled the
emissive map (via the shared sampler2DArray layer).

Requires FC_VULKAN_DUMP_FRAME=1.
"""

import glob
import os

from PIL import Image


def _count_colors(path):
    image = Image.open(path).convert("RGB")
    red = green = 0
    for r, g, b in image.getdata():
        if r > 150 and g < 100 and b < 100:
            red += 1
        elif g > 150 and r < 120 and b < 120:
            green += 1
    return red, green


def check(lines, report):
    if not any("initialized (Vulkan ray tracing)" in line for line in lines):
        report.add_error("ray-tracing backend never initialized")

    frames_dir = os.path.join(report.artifact_dir, "frames")
    frames = sorted(glob.glob(os.path.join(frames_dir, "*.png")))
    if not frames:
        report.add_error("no frame dumps; render produced nothing")
        return

    red, green = _count_colors(frames[-1])
    report.session["emissive_red_pixels"] = red
    report.session["emissive_green_pixels"] = green

    if red < 200:
        report.add_error(
            "RT frame has too few emissive-red pixels (%d); the emissive map "
            "was not sampled" % red)
    if green >= red:
        report.add_error(
            "RT frame is not dominated by the red emissive map (red=%d "
            "green=%d)" % (red, green))
