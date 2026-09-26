#!/usr/bin/env python3
"""Host-side assertions for vk_present_probe.py (Vulkan present-mode pref).

The probe sets ``VulkanPresentMode`` before the view is created, so
``QuarterVulkanWidget``'s ``applyPresentMode`` resolves it and emits

    [VK-PRESENT] requested=<N> using=<fifo|mailbox|immediate>

This check reads the requested mode back out of the run's env overrides
(``FC_TEST_PRESENT_MODE``) and asserts:

  - a breadcrumb for that request was emitted (the pref was read and applied),
  - the resolved mode is either the requested one or a FIFO fallback (the only
    guaranteed mode; the code logs a warning when it falls back).

Requires FC_VULKAN_BREADCRUMBS=1.
"""

import re

PRESENT = re.compile(r"\[VK-PRESENT\] requested=(\d+) using=(\S+)")
NAMES = {0: "fifo", 1: "mailbox", 2: "immediate"}


def check(lines, report):
    env = report.session.get("env_overrides") or {}
    requested = int(env.get("FC_TEST_PRESENT_MODE", "0"))
    want = NAMES.get(requested, "fifo")

    records = [
        (int(m.group(1)), m.group(2))
        for line in lines
        for m in [PRESENT.search(line)]
        if m
    ]
    if not records:
        report.add_error(
            "no [VK-PRESENT] breadcrumb (is FC_VULKAN_BREADCRUMBS=1 set?)")
        return

    # There may be earlier resolutions for other views; require at least one
    # record for our request, and validate only those.
    ours = [used for req, used in records if req == requested]
    if not ours:
        report.add_error(
            "no [VK-PRESENT] record for requested=%d (pref not read?)"
            % requested)
        return
    for used in ours:
        if used not in (want, "fifo"):
            report.add_error(
                "present mode requested %s resolved to unexpected %r "
                "(only %s or a fifo fallback is valid)" % (want, used, want))

    report.session["present_mode"] = want
    report.session["present_records"] = [list(r) for r in records]
