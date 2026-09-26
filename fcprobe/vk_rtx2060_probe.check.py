#!/usr/bin/env python3
"""Host-side assertions for vk_rtx2060_probe.py (simulated RTX 2060).

The probe runs path tracing under the ``rtx-2060`` device profile.  Asserts:

  - the ``[RTDBG] caps`` self-probe ran and the four post-Turing optional
    extensions are reported ABSENT (opacityMicromap / nvCluster /
    nvPartitioned / nvLinearSweptSpheres == 0) -- so the profile really took
    effect;
  - ray tracing still initialized and path-traced anyway
    ("initialized (Vulkan ray tracing)" + accumulating ``[RTDBG] ptState``
    frames + a dumped frame), i.e. a 2060-class device degrades gracefully.

Requires FC_VULKAN_RT_DEBUG=1 and FC_VULKAN_DUMP_FRAME=1.
"""

import glob
import os
import re

CAPS = re.compile(
    r"\[RTDBG\] caps positionFetch=(\d+)\s+opacityMicromap=(\d+)\s+"
    r"nvCluster=(\d+)\s+nvPartitioned=(\d+)\s+nvLinearSweptSpheres=(\d+)")
PTSTATE = re.compile(r"\[RTDBG\] ptState frame=(\d+)")
DEVICE = re.compile(
    r"\[VK-DEVICE\] selected index=(\d+) name='([^']*)' type=(\d+) "
    r"maxMemAlloc=(\d+)")
RT_INIT = "initialized (Vulkan ray tracing)"

# Capabilities a strict Turing (2060) part must not report.
MUST_BE_ABSENT = ("positionFetch", "opacityMicromap", "nvCluster",
                  "nvPartitioned", "nvLinearSweptSpheres")
# The VP_NVIDIA_rtx_2060 profiles document forces this finite limit.
SIM_MAX_MEM_ALLOC = 65536


def check(lines, report):
    def err(msg):
        report.add_error(msg)

    caps = None
    pt_frames = []
    device = None
    for line in lines:
        m = CAPS.search(line)
        if m and caps is None:
            caps = {
                "positionFetch": int(m.group(1)),
                "opacityMicromap": int(m.group(2)),
                "nvCluster": int(m.group(3)),
                "nvPartitioned": int(m.group(4)),
                "nvLinearSweptSpheres": int(m.group(5)),
            }
        m2 = PTSTATE.search(line)
        if m2:
            pt_frames.append(int(m2.group(1)))
        m3 = DEVICE.search(line)
        if m3:
            device = {"name": m3.group(2), "type": int(m3.group(3)),
                      "maxMemAlloc": int(m3.group(4))}

    if caps is None:
        err("no [RTDBG] caps line: RTX caps self-probe never ran (did RT come "
            "up under the simulated device?)")
        return
    report.session["rtx2060_caps"] = caps

    # Control runs (no device profile) set FC_RTX2060_EXPECT=present: the full
    # GPU must report these caps, which proves the profile is what zeroes them.
    expect = (report.session.get("env_overrides") or {}).get(
        "FC_RTX2060_EXPECT", "absent")
    for name in MUST_BE_ABSENT:
        if expect == "present":
            if not caps[name]:
                err("control: full device reports %s=0 but should advertise it"
                    % name)
        elif caps[name]:
            err("simulated RTX 2060 still reports %s=1; the rtx-2060 device "
                "profile did not hide the extension" % name)

    # The strict profile also constrains a device limit via the Vulkan Profiles
    # document (SIMULATE_PROPERTIES_BIT); the [VK-DEVICE] breadcrumb carries it.
    if device is not None:
        report.session["rtx2060_device"] = device
    if expect == "absent":
        if device is None:
            err("no [VK-DEVICE] line; cannot verify the simulated device limits")
        elif device["maxMemAlloc"] != SIM_MAX_MEM_ALLOC:
            err("simulated maxMemoryAllocationCount=%d, expected %d "
                "(VP_NVIDIA_rtx_2060 properties were not applied)"
                % (device["maxMemAlloc"], SIM_MAX_MEM_ALLOC))

    if not any(RT_INIT in line for line in lines):
        err("ray tracing did not initialize on the simulated RTX 2060 "
            "(the fallback path is broken)")

    if not pt_frames:
        err("no [RTDBG] ptState lines: path tracing never accumulated on the "
            "simulated RTX 2060")
    elif len(pt_frames) < 3:
        err("path tracing only accumulated %d frames (< 3) on the simulated "
            "device" % len(pt_frames))

    frames = glob.glob(
        os.path.join(report.artifact_dir, "frames", "vk_frame_*.png"))
    if not frames:
        err("no frame dumps produced on the simulated RTX 2060")
