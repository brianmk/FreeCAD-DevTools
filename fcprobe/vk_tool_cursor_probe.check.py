#!/usr/bin/env python3
"""Host-side assertions for vk_tool_cursor_probe.py.

The probe starts a sketch geometry tool and reports which widget carries the
tool's bitmap cursor:

  TOOLCURSOR_MODE mode=<vulkan|gl> container=<0|1>
  TOOLCURSOR_RESULT visible_bitmap=<0|1> container_bitmap=<0|1> viewer_bitmap=<0|1>

This check asserts the cursor reaches the widget the user actually sees, i.e.
the Vulkan container under Vulkan (the regression: the cursor went to the
hidden GL widget), or the GL viewer widget otherwise.  It also fails when no
tool cursor was produced at all, so "the hidden widget has no cursor" can never
pass vacuously.
"""

import re

MODE = re.compile(r"TOOLCURSOR_MODE mode=(\w+) container=(\d)")
RESULT = re.compile(
    r"TOOLCURSOR_RESULT visible_bitmap=(\d) container_bitmap=(\d) viewer_bitmap=(\d)"
)


def check(lines, report):
    modes = [m for m in (MODE.search(line) for line in lines) if m]
    results = [m for m in (RESULT.search(line) for line in lines) if m]
    if not modes or not results:
        report.add_error(
            "no TOOLCURSOR_RESULT marker: the probe did not reach the tool-cursor phase"
        )
        return

    mode, has_container = modes[-1].groups()
    visible, container, viewer = results[-1].groups()

    if mode == "vulkan" and has_container != "1":
        report.add_error("Vulkan mode was reported but no native surface container was found")
    if visible != "1":
        report.add_error(
            "the sketch tool's bitmap cursor did not reach the visible surface "
            "(visible=%s container=%s viewer=%s); it is being set on a widget the "
            "user cannot see" % (visible, container, viewer)
        )
    if mode == "vulkan" and container != "1":
        report.add_error(
            "under Vulkan the tool cursor was not applied to the native container "
            "(container=%s viewer=%s)" % (container, viewer)
        )

    report.session["tool_cursor"] = {
        "mode": mode,
        "visible_bitmap": visible,
        "container_bitmap": container,
        "viewer_bitmap": viewer,
    }
