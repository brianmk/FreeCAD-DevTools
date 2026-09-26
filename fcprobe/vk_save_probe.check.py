#!/usr/bin/env python3
"""Host-side assertions for vk_save_probe.py.

The probe calls ``view.saveImage()`` while the path tracer is active.  This
check asserts every save wrote a file and none raised (a regression in the
Vulkan saveImage path would surface as "saveImage failed").
"""

import re

WROTE = re.compile(r"SAVE .*saveImage wrote (\S+) \(phase k=(\d+)\)")
FAILED = re.compile(r"SAVE .*saveImage failed k=(\d+)")


def check(lines, report):
    wrote = [m.group(1) for line in lines for m in [WROTE.search(line)] if m]
    failed = [m.group(1) for line in lines for m in [FAILED.search(line)] if m]
    if failed:
        report.add_error("saveImage failed at phase(s): %s" % ", ".join(failed))
    if not wrote:
        report.add_error("saveImage never wrote a file (probe did not exercise it)")
    report.session["save_image_writes"] = len(wrote)
