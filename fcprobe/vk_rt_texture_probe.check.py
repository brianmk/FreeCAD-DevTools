#!/usr/bin/env python3
"""Host-side assertions for vk_rt_texture_probe.py.

Verifies that the ray-traced backend samples the material's base-colour
texture: the box is authored with a red diffuse and a solid-green image, so a
dumped frame that is dominated by green (and free of red) proves the texture
was uploaded to the RT sampler2DArray and sampled at the interpolated UV.

Requires FC_VULKAN_DUMP_FRAME=1 so the probe run leaves frames in
<artifact>/frames/.
"""

import glob
import os

from PIL import Image


def _count_colors(path):
    image = Image.open(path).convert("RGB")
    green = red = 0
    for r, g, b in image.getdata():
        if g > 150 and r < 120 and b < 120:
            green += 1
        elif r > 150 and g < 100 and b < 100:
            red += 1
    return green, red


def check(lines, report):
    if not any("initialized (Vulkan ray tracing)" in line for line in lines):
        report.add_error("ray-tracing backend never initialized")

    frames_dir = os.path.join(report.artifact_dir, "frames")
    frames = sorted(glob.glob(os.path.join(frames_dir, "*.png")))
    if not frames:
        report.add_error("no frame dumps; render produced nothing")
        return

    green, red = _count_colors(frames[-1])
    report.session["texture_green_pixels"] = green
    report.session["texture_red_pixels"] = red

    # The textured face fills a large part of the viewport; require a solid
    # green presence and no red-dominant frame.
    if green < 200:
        report.add_error(
            "RT frame has too few texture-green pixels (%d); the base-colour "
            "texture was not sampled" % green)
    if red > green:
        report.add_error(
            "RT frame is dominated by the red diffuse (%d) over the texture "
            "green (%d); texture sampling did not modulate the base colour"
            % (red, green))
