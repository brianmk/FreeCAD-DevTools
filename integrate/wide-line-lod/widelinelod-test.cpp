// integrate/wide-line-lod/widelinelod-test.cpp
//
// CPU-only test for the wide-line predicate that the Vulkan raster draw path,
// the pipeline key, the batching pass and the CPU expansion pre-pass all share
// (CoinVulkanDetail::isWideLine / lineSegmentCount, in
// rendering/SoVulkanRenderBackend/SoVulkanRenderBackendP.h).
//
// What it guards: interaction LOD (reduced detail while the camera moves) used
// to drop *every* width>1 line to the plain 1px path.  A small wide line set --
// the Sketcher grid's every-nth division lines (2px by default), a NaviCube
// edge, a GUI tracker -- is cheap to expand either way, and downgrading it is a
// visible quality change for as long as frames keep coming.  Only line sets
// large enough that the CPU quad expansion is the dominant navigation cost may
// be downgraded.
//
// No GPU / backend instance is required: the predicate is pure command state.

#include <Inventor/SoDB.h>
#include <Inventor/rendering/SoRenderIR.h>
#include <rendering/SoVulkanRenderBackend.h>
#include <rendering/SoVulkanRenderBackend/SoVulkanRenderBackendP.h>

#include <iostream>

namespace {

using CoinVulkanDetail::isWideLine;
using CoinVulkanDetail::kLargeLineSetMinSegments;
using CoinVulkanDetail::lineSegmentCount;

int failures = 0;

void expect(bool ok, const char * what)
{
  if (!ok) {
    std::cerr << "FAIL: " << what << std::endl;
    ++failures;
  }
}

// A non-indexed LINE_LIST carrying `segments` two-vertex segments, as the
// Sketcher grid's SoLineSet emits.
SoRenderCommand lineList(uint32_t segments, float width,
                         uint16_t pattern = 0xFFFF)
{
  SoRenderCommand command;
  command.geometry.topology = SO_TOPOLOGY_LINES;
  command.geometry.vertexCount = segments * 2;
  command.state.raster.lineWidth = width;
  command.state.raster.linePattern = pattern;
  return command;
}

} // namespace

int
main()
{
  SoDB::init();

  // Plain 1px solid line: never the wide-line path.
  {
    const SoRenderCommand command = lineList(4, 1.0f);
    expect(!isWideLine(command, -1, false), "1px line is not a wide line");
    expect(!isWideLine(command, -1, true),
           "1px line is not a wide line under interaction LOD");
  }

  // Small 2px line set (the Sketcher grid's division lines are ~246 segments):
  // wide with and without interaction LOD.
  {
    const SoRenderCommand command = lineList(246, 2.0f);
    expect(isWideLine(command, -1, false),
           "small 2px line set is a wide line without interaction LOD");
    expect(isWideLine(command, -1, true),
           "small 2px line set keeps the wide path under interaction LOD");
  }

  // A stipple always needs the expanded path, LOD or not.
  {
    const SoRenderCommand command = lineList(4, 1.0f, 0x0F0F);
    expect(isWideLine(command, -1, false), "stippled line is a wide line");
    expect(isWideLine(command, -1, true),
           "stippled line survives interaction LOD");
  }

  // Large line set: expanded normally, downgraded while the camera moves (the
  // expansion is the dominant navigation cost at this size).
  {
    const SoRenderCommand command =
      lineList(kLargeLineSetMinSegments, 2.0f);
    expect(isWideLine(command, -1, false),
           "large 2px line set is a wide line without interaction LOD");
    expect(!isWideLine(command, -1, true),
           "large 2px line set is downgraded under interaction LOD");
  }

  // Threshold boundary: one segment below the cut keeps the wide path.
  {
    const SoRenderCommand below =
      lineList(kLargeLineSetMinSegments - 1, 2.0f);
    expect(isWideLine(below, -1, true),
           "line set one segment below the LOD cut keeps the wide path");
  }

  // Indexed LINE_LIST: the segment count comes from the index count.
  {
    SoRenderCommand command = lineList(1, 2.0f);
    static uint32_t indices[4] = {0, 1, 2, 3};
    command.geometry.vertexCount = 4096;
    command.geometry.indices = indices;
    command.geometry.indexCount = 4;
    expect(lineSegmentCount(command) == 2,
           "indexed line list segments = indexCount / 2");
    expect(isWideLine(command, -1, true),
           "indexed small 2px line set keeps the wide path under LOD");
  }

  // LINE_STRIP: n vertices are n-1 segments.
  {
    SoRenderCommand command;
    command.geometry.topology = SO_TOPOLOGY_LINE_STRIP;
    command.geometry.vertexCount = 5;
    command.state.raster.lineWidth = 2.0f;
    expect(lineSegmentCount(command) == 4, "line strip segments = count - 1");
    expect(isWideLine(command, -1, true),
           "small 2px line strip keeps the wide path under LOD");
  }

  // Overlay wireframe/point redraws (fillModeOverride >= 0) stay on the plain
  // line path regardless of width.
  {
    const SoRenderCommand command = lineList(246, 4.0f);
    expect(!isWideLine(command, 1, false),
           "overlay redraw is never a wide line");
    expect(!isWideLine(command, 1, true),
           "overlay redraw is never a wide line under interaction LOD");
  }

  // Non-line topologies never take the line path.
  {
    SoRenderCommand command;
    command.geometry.topology = SO_TOPOLOGY_TRIANGLES;
    command.geometry.vertexCount = 300;
    command.state.raster.lineWidth = 4.0f;
    expect(lineSegmentCount(command) == 0,
           "triangle topology has no line segments");
    expect(!isWideLine(command, -1, true),
           "triangle topology is not a wide line");
  }

  if (failures == 0) {
    std::cout << "WideLineLodTest: all checks passed" << std::endl;
  }
  return failures == 0 ? 0 : 1;
}
