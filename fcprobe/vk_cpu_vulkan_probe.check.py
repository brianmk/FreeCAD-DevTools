#!/usr/bin/env python3
"""Host-side assertions for vk_cpu_vulkan_probe.py (CPU-only Vulkan render).

Asserts:
  - the Vulkan viewport selected a CPU software device
    (``[VK-DEVICE] ... type=4`` = VK_PHYSICAL_DEVICE_TYPE_CPU), so no GPU was
    used -- a run that fell back to the NVIDIA/RADV device fails here;
  - at least one frame was dumped and it is not a uniform image (something
    actually rendered on the CPU).

Requires FC_VULKAN_BREADCRUMBS=1 and FC_VULKAN_DUMP_FRAME=1.
"""

import glob
import os
import re

from PIL import Image

DEVICE = re.compile(
    r"\[VK-DEVICE\] selected index=(\d+) name='([^']*)' type=(\d+)")
VK_PHYSICAL_DEVICE_TYPE_CPU = 4


def check(lines, report):
    def err(msg):
        report.add_error(msg)

    devices = [
        (int(m.group(1)), m.group(2), int(m.group(3)))
        for line in lines
        for m in [DEVICE.search(line)]
        if m
    ]
    if not devices:
        err("no [VK-DEVICE] selection breadcrumb "
            "(is FC_VULKAN_BREADCRUMBS=1 set? did Vulkan come up?)")
        return
    index, name, dtype = devices[-1]
    report.session["cpu_vulkan_device"] = {"name": name, "type": dtype}
    if dtype != VK_PHYSICAL_DEVICE_TYPE_CPU:
        err("selected Vulkan device '%s' has type=%d, not CPU(4); a GPU was "
            "used (is the lavapipe ICD actually loaded?)" % (name, dtype))

    frames = sorted(glob.glob(
        os.path.join(report.artifact_dir, "frames", "vk_frame_*.png")))
    if not frames:
        err("no frame dumps (is FC_VULKAN_DUMP_FRAME=1 set?)")
        return
    import numpy as np
    best_std = 0.0
    for p in frames:
        a = np.asarray(Image.open(p).convert("RGB"), dtype=np.int32)
        best_std = max(best_std, float(a.reshape(-1, 3).std(0).max()))
    report.session["cpu_vulkan_frame_max_channel_std"] = round(best_std, 2)
    if best_std < 2.0:
        err("all dumped frames are (near) uniform (max channel std %.2f); "
            "nothing rendered" % best_std)
