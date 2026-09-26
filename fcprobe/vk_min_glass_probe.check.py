#!/usr/bin/env python3
"""Host-side assertions for vk_min_glass_probe.py.

The only geometry is the translucent cyan cube, so the frame centre must read
cyan (green clearly above red, blue at/above green) while the corners stay the
neutral background.  This distinguishes the glass from the (blue-ish) default
background gradient, which a loose "bluish pixel" count would not.

Requires FC_VULKAN_RT_DEBUG=1 and FC_VULKAN_DUMP_FRAME=1.
"""

import glob
import os

from PIL import Image

RT_INIT = "initialized (Vulkan ray tracing)"


def _region_mean(a, y0, y1, x0, x1):
    h, w, _ = a.shape
    return a[int(h * y0):int(h * y1), int(w * x0):int(w * x1)].reshape(-1, 3).mean(0)


def check(lines, report):
    if not any(RT_INIT in line for line in lines):
        report.add_error("RTX backend never initialized "
                         "(is FC_VULKAN_RT_DEBUG=1 set?)")
    frames = sorted(glob.glob(
        os.path.join(report.artifact_dir, "frames", "vk_frame_*.png")))
    if not frames:
        report.add_error("no frame dumps (is FC_VULKAN_DUMP_FRAME=1 set?)")
        return
    import numpy as np
    a = np.asarray(Image.open(frames[-1]).convert("RGB"), dtype=np.int32)
    center = _region_mean(a, 0.4, 0.6, 0.4, 0.6)
    corner = _region_mean(a, 0.0, 0.1, 0.0, 0.1)
    report.session["min_glass_center"] = [round(float(x), 1) for x in center]
    report.session["min_glass_corner"] = [round(float(x), 1) for x in corner]
    if not (center[1] > center[0] + 15):  # cyan: green above red
        report.add_error(
            "frame centre is not cyan (r=%.0f g=%.0f b=%.0f); the glass did "
            "not render" % tuple(center))
    if corner[1] > corner[0] + 15:
        report.add_error(
            "background corner also reads cyan (r=%.0f g=%.0f b=%.0f); the "
            "centre test is not discriminating" % tuple(corner))
