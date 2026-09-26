#!/usr/bin/env python3
"""Host-side assertions for vk_glass_probe.py (opaque vs translucent glass).

The scene has a red backdrop behind a cyan cube.  When the cube is OPAQUE its
screen area is solid cyan; at Transparency 50 the red backdrop shows through and
the cyan area shrinks (the transmitted image is no longer the cube's own
diffuse).  This check compares the count of clearly-cyan pixels (green above
red, blue at/above green -- which the blue-ish background gradient does not
satisfy) in the last frame of each phase:

  - the opaque frame must have a real cyan area (the glass rendered);
  - the translucent frame must have noticeably fewer cyan pixels (transmission
    applied).  A broken path leaves the cube opaque and the counts equal.

Requires FC_VULKAN_DUMP_FRAME=1 and FC_VULKAN_RT_DEBUG=1.
"""

import glob
import os
import re

from PIL import Image

RT_INIT = "initialized (Vulkan ray tracing)"
PHASE = re.compile(r"\[HARNESS\] frame_phase phase=(\S+) frame=(\d+)")
FRAME_ORD = re.compile(r"vk_frame_(\d+)\.png$")
MIN_OPAQUE_CYAN = 3000


def _frames(frames_dir):
    out = []
    for p in glob.glob(os.path.join(frames_dir, "vk_frame_*.png")):
        m = FRAME_ORD.search(p)
        if m:
            out.append((int(m.group(1)), p))
    return sorted(out)


def _tight_cyan(path):
    import numpy as np
    a = np.asarray(Image.open(path).convert("RGB"), dtype=np.int32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return int(((g > r + 25) & (b > g) & (g > 80)).sum())


def check(lines, report):
    def err(msg):
        report.add_error(msg)

    if not any(RT_INIT in line for line in lines):
        err("RTX backend never initialized (is FC_VULKAN_RT_DEBUG=1 set?)")

    phases = {}
    for line in lines:
        m = PHASE.search(line)
        if m:
            phases[m.group(1)] = int(m.group(2))
    if "glass-opaque" not in phases or "glass-trans50" not in phases:
        err("probe did not mark both glass phases")
        return

    frames = _frames(os.path.join(report.artifact_dir, "frames"))
    if not frames:
        err("no frame dumps (is FC_VULKAN_DUMP_FRAME=1 set?)")
        return
    trans_ord = phases["glass-trans50"]
    opaque = [p for n, p in frames if n < trans_ord]
    trans = [p for n, p in frames if n >= trans_ord]
    if not opaque or not trans:
        err("no frame dumps on both sides of the transparency toggle")
        return

    oc = _tight_cyan(opaque[-1])
    tc = _tight_cyan(trans[-1])
    report.session["glass_opaque_cyan_px"] = oc
    report.session["glass_trans_cyan_px"] = tc

    if oc < MIN_OPAQUE_CYAN:
        err("opaque cube has too few cyan pixels (%d < %d); the glass did not "
            "render" % (oc, MIN_OPAQUE_CYAN))
    drop = oc - tc
    need = max(1000, int(0.10 * oc))
    if drop < need:
        err("cyan area did not shrink when Transparency went 0 -> 50 "
            "(opaque %d -> trans %d, drop %d < %d); thin-glass transmission "
            "is not applied" % (oc, tc, drop, need))
