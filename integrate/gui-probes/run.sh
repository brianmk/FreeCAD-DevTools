#!/usr/bin/env bash
#
# Run the FreeCAD Vulkan GUI probes against a built FreeCAD and report
# pass/fail.
#
#   integrate/gui-probes/run.sh
#   FREECAD_BUILD=/path/to/build-freecad integrate/gui-probes/run.sh
#
# Viewport images are written with view.saveImage(): screen capture is
# unusable on this box (a fullscreen video owns the display).  Every probe
# exits with os._exit(0), because close()/quit() block while a 3D view is
# open.
#
# A private FREECAD_USER_HOME is used: with the normal home, launching a
# second FreeCAD while another instance is running fails with "Application
# unexpectedly terminated" (the single-instance path).  The isolated home also
# keeps the probe independent of whatever the developer last configured.
#
# Checks per probe: the probe reached "done", no Python error, and every
# expected image is non-trivial (more than one colour).  The mouse probe must
# additionally report a Box pick; the validation probe must report zero VUIDs.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROBES="$HERE/probes"

BUILD="${FREECAD_BUILD:-/home/phantom/dev/FreeCAD-Integrate/build-freecad}"
BIN="${FREECAD_BIN:-$BUILD/bin/FreeCAD}"
OUT="${PROBE_OUT:-/tmp/opencode/gui-probes-out}"
USER_HOME="${PROBE_USER_HOME:-/tmp/opencode/gui-probes-home}"
TIMEOUT="${PROBE_TIMEOUT:-180}"

export FREECAD_USER_HOME="$USER_HOME"
export QT_STYLE_OVERRIDE="${QT_STYLE_OVERRIDE:-fusion}"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-wayland}"
export FC_SKIP_UNSAVED_PROMPT=1
# The fork's library path.  The 3rdParty/coin/lib and 3rdParty/pivy
# directories do not exist in every build; a missing dir in LD_LIBRARY_PATH is
# harmless.
export LD_LIBRARY_PATH="$BUILD/lib:$BUILD/src/3rdParty/coin/lib:$BUILD/src/3rdParty/pivy${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

for f in "$BIN" "$PROBES/geom.py" "$PROBES/camera.py" "$PROBES/edges.py" \
         "$PROBES/mouse.py" "$PROBES/gl.py"; do
  if [[ ! -e "$f" ]]; then
    echo "gui-probes: missing $f" >&2
    exit 2
  fi
done

rm -rf "$OUT"
mkdir -p "$OUT" "$USER_HOME"

PASS=0
FAIL=0
pass() { printf 'PASS  %-10s %s\n' "$1" "$2"; PASS=$((PASS + 1)); }
fail() { printf 'FAIL  %-10s %s\n' "$1" "$2"; FAIL=$((FAIL + 1)); }

LAST_RC=0
LAST_LOG=""

# run_probe <label> <script> [VAR=value ...]
run_probe() {
  local label="$1" script="$2"
  shift 2
  LAST_LOG="$OUT/$label.log"
  env PROBE_OUT="$OUT" "$@" timeout "$TIMEOUT" "$BIN" "$PROBES/$script" \
    >"$LAST_LOG" 2>&1
  LAST_RC=$?
}

# image_ok <path>: non-empty, bigger than a solid-colour PNG, >1 colour.
image_ok() {
  local f="$1"
  [[ -s "$f" ]] || return 1
  [[ "$(stat -c %s "$f" 2>/dev/null || echo 0)" -gt 2000 ]] || return 1
  local colors
  colors="$(magick identify -format '%k' "$f" 2>/dev/null)" || return 1
  [[ -n "$colors" && "$colors" -gt 1 ]]
}

# check_probe <label> <images...>: validates LAST_RC/LAST_LOG + images.
check_probe() {
  local label="$1"
  shift
  local detail=""
  [[ "$LAST_RC" -eq 0 ]] || detail+="exit=$LAST_RC "
  grep -q '^PROBE done' "$LAST_LOG" || detail+="no-done "
  if grep -qE '^PROBE ERROR|Traceback' "$LAST_LOG"; then
    detail+="probe-error "
  fi
  local img
  for img in "$@"; do
    image_ok "$img" || detail+="bad-image(${img##*/}) "
  done
  if [[ -z "$detail" ]]; then
    pass "$label" "rc=0, $# image(s) ok"
  else
    fail "$label" "$detail"
  fi
}

echo "FreeCAD: $BIN"
echo "Output:  $OUT"
echo

# 1. Geometry: box / cylinder / sphere.
run_probe geom geom.py
check_probe geom \
  "$OUT/geom_all.png" "$OUT/geom_box.png" \
  "$OUT/geom_cylinder.png" "$OUT/geom_sphere.png"

# 2. Camera: isometric / top / front / fitAll.
run_probe camera camera.py
check_probe camera \
  "$OUT/cam_isometric.png" "$OUT/cam_top.png" \
  "$OUT/cam_front.png" "$OUT/cam_fitall.png"

# 3. Edges: normal / wireframe / points / restored.
run_probe edges edges.py
check_probe edges \
  "$OUT/edges_normal.png" "$OUT/edges_wireframe.png" \
  "$OUT/edges_points.png" "$OUT/edges_restored.png"

# 4. Hover / click-select: the pick must return the Box object.
run_probe mouse mouse.py
if [[ "$LAST_RC" -eq 0 ]] \
   && grep -q '^PROBE done' "$LAST_LOG" \
   && ! grep -qE '^PROBE ERROR|Traceback' "$LAST_LOG" \
   && grep -qE "pick .*'Object': 'Box'|selection=\['Box'\]" "$LAST_LOG" \
   && image_ok "$OUT/mouse_after_click.png"; then
  pass mouse "pick returned Box"
else
  fail mouse "no Box pick / bad image (see $LAST_LOG)"
fi

# 5. Validation: run the geometry probe with the validation layer enabled;
#    zero VUIDs expected.
run_probe validation geom.py FC_VULKAN_VALIDATION=1
vuid="$(grep -c 'VUID' "$LAST_LOG" 2>/dev/null || true)"
vuid="${vuid:-0}"
if [[ "$LAST_RC" -eq 0 ]] \
   && grep -q '^PROBE done' "$LAST_LOG" \
   && ! grep -qE '^PROBE ERROR|Traceback' "$LAST_LOG" \
   && [[ "$vuid" -eq 0 ]] \
   && image_ok "$OUT/geom_all.png"; then
  pass validation "0 VUID"
else
  fail validation "VUID=$vuid (see $LAST_LOG)"
fi

# 6. GL fallback: VulkanRenderMode=0 (classic Coin/GL raster).
run_probe gl gl.py
check_probe gl "$OUT/gl_mode0_usevk1.png"

echo
echo "gui-probes: $PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]]
