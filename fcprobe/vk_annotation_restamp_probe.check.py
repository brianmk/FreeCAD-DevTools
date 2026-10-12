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

The invariants enforced here, on a probe run that actually reached the Vulkan
path:

* the probe ran (PREVIEWRESTAMP phase markers) and the backend emitted the
  counters (``COIN_VULKAN_BACKEND_DEBUG=1``);
* annotations were present and drawn as annotations: ``overlayAnnotations > 0``
  and ``annotationDepthCleared >= 1`` (the group needs one depth clear in front
  of it, or a preview embedded in an opaque solid is depth-rejected);
* nothing was left stale: ``staleOverlayAfter == 0``;
* every retained command carried the current camera: ``restamped == retained``
  on each replayed frame.  This scene has no sub-camera commands, so the two
  counts must match; a retained command with the previous view would be the
  original bug;
* a retained region armed the replay restamp (``lastViewArmed ... armed=1``).

``retainedOverlay == 0`` is deliberately NOT a failure.  On this path the
preview is re-recorded every frame as a fresh OVERLAY command
(``overlayAnnotations > 0``) rather than staying in the retained main list, so
the restamp has nothing to repair; forcing the other shape would need a
different probe scene.  That property is recorded in the session data (and in
``report.json``) instead of asserted, so this check can neither go green nor red
on it.  Everything the probe *can* prove is still asserted above.
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

    if stale_after != 0:
        report.add_error(
            "a retained annotation command was replayed with a stale camera "
            "(staleOverlayAfter=%d): the preview is drawn where the previous camera "
            "put it instead of following the camera",
            stale_after,
        )

    # Frame-wise: every command in the retained region must have been restamped to
    # the current camera.  Aggregating maxima would compare counts from different
    # frames, so the check is done per counter line.
    unrestamped = [
        m.group(0)
        for m in counters
        if int(m.group(1)) > 0 and int(m.group(5)) != int(m.group(1))
    ]
    if unrestamped:
        report.add_error(
            "a replayed frame did not restamp every retained command (%s): a "
            "retained command kept the previous camera",
            unrestamped[0],
        )

    armed = [m for m in (ARMED.search(line) for line in lines) if m]
    if not armed:
        report.add_error(
            "no [RTDBG] lastViewArmed line: the replay bookkeeping never reported "
            "whether it armed the restamp"
        )
    else:
        unarmed = [
            m.group(0) for m in armed if int(m.group(1)) > 0 and int(m.group(2)) != 1
        ]
        if unarmed:
            report.add_error(
                "a retained region did not arm the replay restamp (%s): promoted "
                "annotation commands would then keep the previous camera",
                unarmed[0],
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
        if seen > 0 and cleared < 1:
            report.add_error(
                "annotation overlay commands were drawn without the group depth clear "
                "(overlayAnnotations=%d annotationDepthCleared=%d): a preview embedded "
                "in an opaque solid is depth-rejected",
                seen,
                cleared,
            )

    if retained_overlay == 0:
        # Documented property of this environment, not a failure: the preview is
        # re-recorded as a fresh overlay command each frame, so there is nothing in
        # the retained list for the restamp to repair.
        report.log_event(
            "CHECK",
            "annotation_restamp_note",
            retainedOverlay=0,
            reason="annotations re-recorded as fresh overlay commands",
            overlayAnnotations=seen if annotations else 0,
        )

    report.session["annotation_restamp"] = {
        "retained_overlay": retained_overlay,
        "stale_overlay_after": stale_after,
        "restamped_mismatches": len(unrestamped),
        "retained_overlay_zero_is_expected": retained_overlay == 0,
        "phases": [m.group(1) for m in phases],
    }
