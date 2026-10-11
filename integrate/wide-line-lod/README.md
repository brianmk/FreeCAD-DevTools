# Wide-line / interaction-LOD predicate test

GPU-free C++ test for the wide-line predicate the Vulkan raster backend shares
across its draw path, pipeline key, batching pass and CPU expansion pre-pass:

- `CoinVulkanDetail::isWideLine()` — is this command drawn through the wide-line
  path (CPU quad expansion or the GPU-instanced vertex shader)?
- `CoinVulkanDetail::lineSegmentCount()` — the line-set size the rule uses.
- `CoinVulkanDetail::kLargeLineSetMinSegments` — the "large line set" scale
  shared with the expansion pre-pass split threshold.

What it guards: **interaction LOD must not downgrade small wide line sets.**
Reduced detail while the camera moves used to drop *every* `SoDrawStyle`
lineWidth > 1 line to the plain 1px path, which visibly removed the configured
width of small sets — most noticeably the Sketcher grid's every-nth division
lines (`GridDivLineWidth`, default 2, ~246 segments) — for as long as frames kept
coming. Only sets at or above `kLargeLineSetMinSegments` (where the CPU
quad expansion is the dominant navigation cost) may be downgraded; stippled
lines and overlay redraws are never downgraded.

It lives here, in the tooling repo, rather than in the Coin or FreeCAD trees:
the product trees carry the fixes, the tests live with the suites. It builds
against an already-built Coin and needs no Vulkan device (it constructs
`SoRenderCommand` state and calls the predicate), so it also runs on machines
without a GPU.

## Build and run

```bash
cmake -S integrate/wide-line-lod -B /tmp/wide-line-lod -G Ninja
cmake --build /tmp/wide-line-lod
ctest --test-dir /tmp/wide-line-lod --output-on-failure
```

Point it at another build with:

```bash
cmake -S integrate/wide-line-lod -B build -G Ninja \
  -DCOIN_ROOT=/path/to/coin \
  -DCOIN_BUILD_ROOT=/path/to/build/coin \
  -DCOIN_INCLUDE_DIR=/path/to/coin/include \
  -DCOIN_LIBRARY=/path/to/build/lib/libCoin.so
```

The test prints `WideLineLodTest: all checks passed` and exits 0 on success; any
failed expectation is printed and the process exits 1.
