#!/usr/bin/env python3
"""Host-side assertions for vk_gpupick_probe.py (GPU ray-query pick parity).

The probe emits ``[HARNESS] gpick mode=<raster|rt> point=.. hit=.. ob=.. comp=..
x=.. y=.. z=..``.  This check independently asserts:

  - the RTX backend initialized ("initialized (Vulkan ray tracing)"), so the
    RT-mode samples really went through the GPU picker;
  - each sampled point picked the same object/component in both modes, within
    POS_TOL mm.
"""

import re

RT_INIT = "initialized (Vulkan ray tracing)"
GP = re.compile(r"\[HARNESS\] gpick (.*)")
POS_TOL = 0.5


def _pairs(text):
    out = {}
    for tok in text.split():
        key, _, value = tok.partition("=")
        out[key] = value
    return out


def check(lines, report):
    def err(msg):
        report.add_error(msg)

    if not any(RT_INIT in line for line in lines):
        err("RTX backend never initialized (is FC_VULKAN_RT_DEBUG=1 set?); "
            "the GPU pick path was never active")

    rows = []
    for line in lines:
        m = GP.search(line)
        if m:
            rows.append(_pairs(m.group(1)))
    if not rows:
        err("no [HARNESS] gpick records (probe did not sample)")
        return

    def index(mode):
        return {r.get("point"): r for r in rows if r.get("mode") == mode}

    raster, rt = index("raster"), index("rt")
    if not raster:
        err("no raster-mode pick samples")
    if not rt:
        err("no RT-mode pick samples")
    if not raster or not rt:
        return

    common = sorted(set(raster) & set(rt))
    if not common:
        err("raster and RT sampled no common points")
        return

    hits = 0
    for point in common:
        r, t = raster[point], rt[point]
        if r.get("hit") != t.get("hit"):
            err("pick hit parity at %s: raster=%s rt=%s"
                % (point, r.get("hit"), t.get("hit")))
            continue
        if r.get("hit") != "1":
            continue
        hits += 1
        if r.get("ob") != t.get("ob"):
            err("picked object parity at %s: raster=%s rt=%s"
                % (point, r.get("ob"), t.get("ob")))
        if r.get("comp") != t.get("comp"):
            err("picked component parity at %s: raster=%s rt=%s"
                % (point, r.get("comp"), t.get("comp")))
        try:
            d = max(abs(float(r[k]) - float(t[k])) for k in ("x", "y", "z"))
        except (KeyError, ValueError):
            d = 0.0
        if d > POS_TOL:
            err("hit position parity at %s: max delta=%.4f" % (point, d))
    if hits == 0:
        err("no point was picked in both modes")

    report.session["gpupick_points"] = len(common)
    report.session["gpupick_hits"] = hits
