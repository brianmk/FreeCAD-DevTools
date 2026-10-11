#!/usr/bin/env python3
"""Host-side assertions for vk_navicube_hover_probe.py (Vulkan nav cube hover).

The probe hovers the nav cube with no button pressed and emits one

    [HARNESS] navicube_hover phase=<off|entry|sweep|repeat> x=.. y=.. frames=<n>

per move, where ``frames`` is how many *presented* Vulkan frames the move
caused.  This check asserts:

  * the run really was on the Vulkan viewport (a non-zero presented-frame
    ordinal at the phase stamps) -- otherwise ``frames=0`` everywhere would
    pass for the wrong reason;
  * nothing was pickable under any hover point (a preselection highlight would
    produce frames of its own and invalidate the measurement);
  * hovering the background presents no frame (the viewport is idle);
  * hovering onto the nav cube, and then across its faces, presents at least
    one frame each -- the regression.  Pre-fix the hover state changed but the
    only wake-up was the hidden GL render manager's ``scheduleRedraw()``, so
    every one of these deltas was 0;
  * re-hovering the exact point of the last sweep move presents 0 frames: the
    highlight does not change, so a delta there would mean the counts above
    are unrelated to the hover (flaky/refining frames) and the run is void.

The best-effort state witness (``[HARNESS] navicube_hover_state``) is folded
into the session dict as ``navicube_hover_state_changed`` /
``navicube_hover_state_diff_px``.  It is read from an offscreen ``saveImage()``
render (the same Coin nav cube node, not the swapchain), so it witnesses the
hover *state*: with the regression, ``changed=1`` alongside ``frames=0``
pinpoints "state updated, nothing presented" rather than "the hover never
reached the nav cube".  When the witness is available but reports no change,
that is a hard error -- the frame assertions would otherwise not prove the
hover was presented.
"""

import re

REC = re.compile(
    r"\[HARNESS\] navicube_hover phase=(\S+) x=(\d+) y=(\d+) frames=(\d+)")
GUARD = re.compile(r"\[HARNESS\] navicube_hover_guard .*pick=(\d)")
STATE = re.compile(
    r"\[HARNESS\] navicube_hover_state state_before=(\S+) state_after=(\S+) "
    r"changed=(\d) diff_px=(-?\d+)")
FRAME_PHASE = re.compile(r"\[HARNESS\] frame_phase phase=(\S+) frame=(\d+)")


def check(lines, report):
    rows = [
        (m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4)))
        for line in lines
        for m in [REC.search(line)]
        if m
    ]
    if not rows:
        report.add_error("no [HARNESS] navicube_hover records (probe did not "
                         "hover the nav cube)")
        return

    def total(phase):
        return sum(f for p, _, _, f in rows if p == phase)

    phases = {p for p, _, _, _ in rows}
    for phase in ("off", "entry", "sweep", "repeat"):
        if phase not in phases:
            report.add_error("navicube hover phase %r missing from the log",
                             phase)
    if report.errors:
        return

    # A real Vulkan run presents frames; without this, "0 hover frames" would
    # be indistinguishable from "never rendered under Vulkan at all".
    stamp_frames = [int(m.group(2)) for line in lines
                    for m in [FRAME_PHASE.search(line)] if m]
    if not stamp_frames or max(stamp_frames) <= 0:
        report.add_error("no presented Vulkan frames recorded "
                         "(frame_phase max=%s): not a Vulkan run",
                         max(stamp_frames) if stamp_frames else "none")

    picked = [int(m.group(1)) for line in lines
              for m in [GUARD.search(line)] if m]
    if not picked:
        report.add_error("no navicube_hover_guard records (no pickability "
                         "control)")
    elif any(picked):
        report.add_error("an object is pickable under %d nav cube hover "
                         "point(s): a preselection highlight could account for "
                         "the frames", sum(picked))

    off, entry, sweep, repeat = (total("off"), total("entry"),
                                 total("sweep"), total("repeat"))
    if off:
        report.add_error("hovering the background presented %d Vulkan frame(s): "
                         "the viewport was not idle", off)
    if entry < 1:
        report.add_error("hovering onto the nav cube presented no Vulkan frame "
                         "(nav cube hover highlight is not drawn)")
    if sweep < 1:
        report.add_error("hovering across the nav cube faces presented no "
                         "Vulkan frame (nav cube hover highlight is not drawn)")
    if repeat:
        report.add_error("re-hovering the same face presented %d Vulkan "
                         "frame(s): the frame counts are not caused by the "
                         "hover state change", repeat)

    state = None
    for line in lines:
        m = STATE.search(line)
        if m:
            state = m
    session = {
        "navicube_hover_off_frames": off,
        "navicube_hover_entry_frames": entry,
        "navicube_hover_sweep_frames": sweep,
        "navicube_hover_repeat_frames": repeat,
        "navicube_hover_moves": len(rows),
    }
    if state:
        session["navicube_hover_state_changed"] = int(state.group(3))
        session["navicube_hover_state_diff_px"] = int(state.group(4))
        session["navicube_hover_state_before"] = state.group(1)
        session["navicube_hover_state_after"] = state.group(2)
        # The witness is the offscreen GL render of the shared nav cube node
        # (never the swapchain).  When it is available it must differ: the
        # hover has to reach the nav cube and change its highlight, otherwise
        # the frame assertions above would not prove the hover was presented.
        if state.group(1) != "none" and int(state.group(3)) != 1:
            report.add_error("the nav cube highlight state did not change on "
                             "hover (state %s -> %s): the hover never reached "
                             "the nav cube", state.group(1), state.group(2))
    else:
        session["navicube_hover_state_changed"] = None
    report.session.update(session)
