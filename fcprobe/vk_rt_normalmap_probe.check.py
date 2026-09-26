#!/usr/bin/env python3
"""Host-side assertions for vk_rt_normalmap_probe.py.

Two green boxes are lit by the headlight: the left carries a flat normal map,
the right a strongly tilted one.  If the ray-traced backend samples the normal
map the right box's top face darkens; if normal mapping is ignored both halves
read identically.

Requires FC_VULKAN_DUMP_FRAME=1.
"""

import glob
import os

from PIL import Image


def _green_split(path):
    image = Image.open(path).convert("RGB")
    width, height = image.size
    left = right = 0
    for y in range(height):
        for x in range(width):
            r, g, b = image.getpixel((x, y))
            if r < 120 and g > 150 and b < 120:
                if x < width // 2:
                    left += 1
                else:
                    right += 1
    return left, right


def check(lines, report):
    if not any("initialized (Vulkan ray tracing)" in line for line in lines):
        report.add_error("ray-tracing backend never initialized")

    frames_dir = os.path.join(report.artifact_dir, "frames")
    frames = sorted(glob.glob(os.path.join(frames_dir, "*.png")))
    if not frames:
        report.add_error("no frame dumps; render produced nothing")
        return

    left, right = _green_split(frames[-1])
    report.session["normalmap_left_green"] = left
    report.session["normalmap_right_green"] = right

    if left < 200:
        report.add_error(
            "flat-normal box is not brightly lit (left green=%d)" % left)
    # The tilted normal must darken the right box's top face well below the
    # flat-normal box; equality would mean the normal map was ignored.
    if right >= left:
        report.add_error(
            "tilted normal map did not darken the surface (left=%d right=%d); "
            "the normal map was not sampled" % (left, right))
    elif right > left * 0.5:
        report.add_error(
            "tilted normal map had too little effect (left=%d right=%d)"
            % (left, right))
