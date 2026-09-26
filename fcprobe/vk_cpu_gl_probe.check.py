#!/usr/bin/env python3
"""Host-side assertions for vk_cpu_gl_probe.py (CPU-only GL render on Wayland).

Asserts:
  - the run was configured for software OpenGL (``LIBGL_ALWAYS_SOFTWARE=1`` and
    ``MESA_LOADER_DRIVER_OVERRIDE=llvmpipe``);
  - ``view.saveImage()`` produced a real, non-uniform image -- something
    rendered on the CPU through llvmpipe.

The image path comes from the probe's ``FC_CPU_PNG`` env override.
"""

import os

from PIL import Image


def check(lines, report):
    def err(msg):
        report.add_error(msg)

    env = report.session.get("env_overrides") or {}
    if env.get("LIBGL_ALWAYS_SOFTWARE") != "1":
        err("LIBGL_ALWAYS_SOFTWARE=1 not set for the run (a GPU may have "
            "rendered)")
    if env.get("MESA_LOADER_DRIVER_OVERRIDE") != "llvmpipe":
        err("MESA_LOADER_DRIVER_OVERRIDE=llvmpipe not set for the run")

    path = env.get("FC_CPU_PNG", "/tmp/opencode/cpu_gl_probe.png")
    if not os.path.isfile(path):
        err("saveImage did not produce %s" % path)
        return
    import numpy as np
    a = np.asarray(Image.open(path).convert("RGB"), dtype=np.int32)
    report.session["cpu_gl_image"] = {
        "path": path, "w": int(a.shape[1]), "h": int(a.shape[0]),
    }
    std = float(a.reshape(-1, 3).std(0).max())
    report.session["cpu_gl_image_max_channel_std"] = round(std, 2)
    if a.shape[0] < 16 or a.shape[1] < 16:
        err("saved image is too small (%dx%d)" % (a.shape[1], a.shape[0]))
    if std < 2.0:
        err("saved image is (near) uniform (max channel std %.2f); nothing "
            "rendered" % std)
