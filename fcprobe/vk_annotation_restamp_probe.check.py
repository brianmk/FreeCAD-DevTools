#!/usr/bin/env python3
"""Host-side assertions for vk_annotation_restamp_probe.py.

The renderer logs, on every replayed retained frame with the backend debug log
on:

  [RTDBG] retained=<n> retainedOverlay=<n> staleOverlayBefore=<n> \
          staleOverlayAfter=<n> restamped=<n>

`retainedOverlay` counts annotation commands (PartDesign previews and friends)
that live in the retained main list and had to be restamped to the current
camera; `staleOverlayAfter` counts the ones still carrying a previous camera
after the restamp, which is the bug: the preview is then drawn where the old
camera put it.

The check requires both that annotations were actually present (otherwise it
would pass vacuously) and that nothing was left stale.
"""

import re

COUNTERS = re.compile(
    r"\[RTDBG\] retained=(\d+) retainedOverlay=(\d+) staleOverlayBefore=(\d+) "
    r"staleOverlayAfter=(\d+) restamped=(\d+)"
)

PHASE = re.compile(r"PREVIEWRESTAMP phase=(\w+) preview=(\w+) camera=([\d,.\-]+)")

ARMED = re.compile(r"\[RTDBG\] lastViewArmed retained=(\d+) armed=(\d+)")

# Annotation commands must be drawn in the annotation sweep with the depth buffer
# cleared once for the group, or a preview embedded in an opaque solid is depth-rejected.
OVERLAY_ANNOTATIONS = re.compile(
    r"\[RTDBG\] overlayAnnotations=(\d+) annotationDepthCleared=(\d+)"
)


def check(lines, report):
    counters = [m for m in (COUNTERS.search(line) for line in lines) if m]
    phases = [m for m in (PHASE.search(line) for line in lines) if m]

    if not phases:
        report.add_error("no PREVIEWRESTAMP phase marker: the probe did not run")
        return
    if not counters:
        report.add_error(
            "no [RTDBG] restamp counters in the output: run the probe with "
            "COIN_VULKAN_BACKEND_DEBUG=1 (the counters are the whole point)"
        )
        return

    retained_overlay = max(int(m.group(2)) for m in counters)
    stale_after = max(int(m.group(4)) for m in counters)
    restamped = max(int(m.group(5)) for m in counters)

    if retained_overlay == 0:
        report.add_error(
            "no annotation commands were retained (retainedOverlay=0): the preview "
            "never reached the retained list, so this check proves nothing"
        )
    if stale_after != 0:
        report.add_error(
            "a retained annotation command was replayed with a stale camera "
            "(staleOverlayAfter=%d): the preview is drawn where the previous camera "
            "put it instead of following the camera" % stale_after
        )

    armed = [m for m in (ARMED.search(line) for line in lines) if m]
    if not armed:
        report.add_error(
            "no [RTDBG] lastViewArmed line: the replay bookkeeping never reported "
            "whether it armed the restamp"
        )
    else:
        unarmed = [m.group(0) for m in armed
                   if int(m.group(1)) > 0 and int(m.group(2)) != 1]
        if unarmed:
            report.add_error(
                "a retained region did not arm the replay restamp (%s): promoted "
                "annotation commands would then keep the previous camera"
                % unarmed[0]
            )

    annotations = [m for m in (OVERLAY_ANNOTATIONS.search(line) for line in lines) if m]
    if not annotations:
        report.add_error(
            "no [RTDBG] overlayAnnotations line: the backend never reported the "
            "annotation overlay sweep"
        )
    else:
        seen = max(int(m.group(1)) for m in annotations)
        cleared = max(int(m.group(2)) for m in annotations)
        if seen == 0:
            report.add_error(
                "no annotation commands reached the overlay sweep "
                "(overlayAnnotations=0): the preview/annotation is not being drawn as "
                "an annotation, so the check proves nothing"
            )
        if seen > 0 and cleared != 1:
            report.add_error(
                "annotation overlay commands were drawn without the group depth clear "
                "(overlayAnnotations=%d annotationDepthCleared=%d): a preview embedded "
                "in an opaque solid is depth-rejected" % (seen, cleared)
            )

    report.session["annotation_restamp"] = {
        "retained_overlay": retained_overlay,
        "stale_overlay_after": stale_after,
        "restamped": restamped,
        "phases": [m.group(1) for m in phases],
    }
