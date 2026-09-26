#!/usr/bin/env python3
"""Host-side assertions for vk_rt_hdr_probe.py.

The probe runs the path tracer with ``FC_RT_HDR=0`` (SDR) or ``1`` (scRGB HDR).
This check verifies the HDR request actually reached the swapchain setup: with
FC_RT_HDR=1 the "setHdrOutputEnabled: requested scRGB FP16 ..." breadcrumb must
appear; with FC_RT_HDR=0 it must not.  Requires FC_VULKAN_BREADCRUMBS=1.
"""

HDR_BREADCRUMB = "[VK-HDR] setHdrOutputEnabled: requested scRGB FP16"


def check(lines, report):
    env = report.session.get("env_overrides") or {}
    want_hdr = env.get("FC_RT_HDR", "0") == "1"
    seen = any(HDR_BREADCRUMB in line for line in lines)
    if want_hdr and not seen:
        report.add_error(
            "FC_RT_HDR=1 but no scRGB HDR setup breadcrumb "
            "(is FC_VULKAN_BREADCRUMBS=1 set? did the HDR pref apply?)")
    if not want_hdr and seen:
        report.add_error(
            "FC_RT_HDR=0 but the scRGB HDR path was still requested")
    report.session["rt_hdr_requested"] = want_hdr
    report.session["rt_hdr_breadcrumb"] = seen
