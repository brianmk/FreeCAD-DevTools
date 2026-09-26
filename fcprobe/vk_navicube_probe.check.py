#!/usr/bin/env python3
"""Host-side assertions for vk_navicube_probe.py (Vulkan nav cube).

The probe emits one ``[HARNESS] navicube phase=<control|cube> changed=<0|1>``
per corner click.  This check asserts the signal is real:

  - with the nav cube disabled every click left the camera unchanged;
  - with it enabled at least one click navigated the camera.
"""

import re

REC = re.compile(
    r"\[HARNESS\] navicube phase=(\S+) changed=(\d+) x=(\d+) y=(\d+)")


def check(lines, report):
    rows = [
        (m.group(1), int(m.group(2)))
        for line in lines
        for m in [REC.search(line)]
        if m
    ]
    if not rows:
        report.add_error("no [HARNESS] navicube records (probe did not sweep)")
        return

    control = [c for p, c in rows if p == "control"]
    cube = [c for p, c in rows if p == "cube"]
    if not control:
        report.add_error("no navicube 'control' phase records")
    if not cube:
        report.add_error("no navicube 'cube' phase records")
    if any(c for c in control):
        report.add_error("control sweep changed the camera with the nav cube off")
    if cube and not any(cube):
        report.add_error(
            "nav cube sweep never changed the camera (click did not navigate)")

    report.session["navicube"] = {
        "control_clicks": len(control),
        "control_hits": sum(control),
        "cube_clicks": len(cube),
        "cube_hits": sum(cube),
    }
