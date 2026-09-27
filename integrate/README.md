# FreeCAD Vulkan raster integration — dev/test tooling

Out-of-tree integration test suites for the FreeCAD **Vulkan raster** viewport
and the bundled Coin renderer.  Nothing here modifies the FreeCAD/Coin source
trees: both suites build and run **against an already-built** FreeCAD/Coin.

```
integrate/
├── README.md                     <- this file
├── coin-vulkan-tests/            A) C++ Coin raster tests (+ ctest)
│   ├── CMakeLists.txt
│   └── testsuite/                ported from coin testsuite @ origin/freecad-master
│       ├── CoinTest.h            ┐
│       ├── TestSuiteUtils.{h,cpp}│ shared test utilities (vendored; see note)
│       ├── TestSuiteMisc.{h,cpp} ┘
│       ├── core-traversal-test.cpp
│       ├── drawlist-sort-stability-test.cpp
│       ├── scene-manager-core-test.cpp        [adapted]
│       ├── retained-ir-test.cpp
│       ├── retained-mixed-topology-test.cpp
│       ├── retained-node-test.cpp
│       ├── retained-raster-text-test.cpp
│       └── vulkan/
│           ├── VulkanTestHarness.h
│           ├── drawlist-vulkan-test.cpp       [adapted]
│           ├── vulkan-backend-*.cpp           (19 raster backend tests)
│           ├── vulkan-light-stability-test.cpp
│           └── vulkan-rendermanager-*.cpp
└── gui-probes/                   B) Python in-GUI probes
    ├── run.sh
    └── probes/
        ├── geom.py               box / cylinder / sphere
        ├── camera.py             isometric / top / front / fitAll
        ├── edges.py              wireframe / points overlay toggles
        ├── mouse.py              hover + click-select (real pick)
        └── gl.py                 GL fallback (VulkanRenderMode=0)
```

Both suites are specific to the integration branch and are independent of
`fcprobe/` (the general FreeCAD probe harness) and `DevTools/`.

---

## Prerequisites

An existing FreeCAD build with the bundled Coin Vulkan renderer.  The default
paths (all overridable) are:

| What | Default |
| --- | --- |
| Coin source root | `/home/phantom/dev/FreeCAD-Integrate/FreeCAD-vulkan/src/3rdParty/coin` |
| Coin build root (generated headers) | `/home/phantom/dev/FreeCAD-Integrate/build-freecad/src/3rdParty/coin` |
| Coin public includes | `<COIN_ROOT>/include` |
| `libCoin.so` | `/home/phantom/dev/FreeCAD-Integrate/build-freecad/lib/libCoin.so` |
| Vulkan loader / headers | system (`/usr/lib/libvulkan.so`, `/usr/include/vulkan/vulkan.h`) |
| FreeCAD binary (probes) | `/home/phantom/dev/FreeCAD-Integrate/build-freecad/bin/FreeCAD` |
| ImageMagick (`magick`) | used by `gui-probes/run.sh` for the image check |

The C++ tests need the Coin **internal** headers (`src/rendering/…`): the
Vulkan backend contract used by the tests (`SoVulkanRenderBackend`,
`SoVulkanDeviceContext`, `SoRenderBackendInitParams`, `SoRenderParams`) is
internal-only, not installed public API.  The build therefore adds
`<COIN_ROOT>/include`, `<COIN_ROOT>/src`, the generated
`<COIN_BUILD_ROOT>/include`, and the generated `<COIN_BUILD_ROOT>/src`
(which holds the generated `config.h`), plus `-DCOIN_BUILD_VULKAN_RENDERER=1`
(these Coin headers expand to nothing without it).

---

## A) C++ Coin raster tests

Build and run (this is the verified invocation):

```bash
cmake -S integrate/coin-vulkan-tests -B /tmp/opencode/cvkt-build -G Ninja
cmake --build /tmp/opencode/cvkt-build -j"$(nproc)"
ctest --test-dir /tmp/opencode/cvkt-build --output-on-failure
```

Point it at another build with:

```bash
cmake -S integrate/coin-vulkan-tests -B build -G Ninja \
  -DCOIN_ROOT=/path/to/coin \
  -DCOIN_BUILD_ROOT=/path/to/build/coin \
  -DCOIN_INCLUDE_DIR=/path/to/coin/include \
  -DCOIN_LIBRARY=/path/to/build/coin/lib/libCoin.so \
  -DVULKAN_LIBRARY=/path/to/libvulkan.so
```

Each test is its own executable (as in the Coin testsuite).  A test that finds
no usable Vulkan device exits `77`, which ctest reports as a skip.

### Verified result (this machine, `build-freecad`)

```
96% tests passed, 1 tests failed out of 28
  Failed: VulkanBackendTessOverlayTest
```

All 27 other tests pass, including the 21 headless Vulkan tests and the pure
retained-IR / core / scene-manager tests.

### Ported

**Vulkan raster backend (21)** — one executable each, all standalone with their
own `main()`:

`DrawListVulkanTest`, `VulkanBackendLifecycleTest`,
`VulkanBackendRenderExternalTest`, `VulkanBackendTextOverlayTest`,
`VulkanBackendMixedTopologyTest`, `VulkanBackendFragmentOutputTest`,
`VulkanBackendDepthTest`, `VulkanBackendCullingTest`,
`VulkanBackendLightingTest`, `VulkanBackendTextureModelsTest`,
`VulkanBackendMultitexStagingTest`, `VulkanBackendScissorTest`,
`VulkanBackendClearTest`, `VulkanBackendYFlipTest`,
`VulkanBackendStencilTest`, `VulkanBackendTessOverlayTest`,
`VulkanBackendRetainedChangeTest`, `VulkanBackendParallelTest`,
`VulkanRenderManagerTest`, `VulkanRenderManagerVisibilityTest`,
`VulkanLightStabilityTest` — plus `vulkan/VulkanTestHarness.h`.

**Retained-IR / core (7)**: `CoreTraversalTest`,
`DrawListSortStabilityTest`, `SceneManagerCoreTest`, `RetainedIRTest`,
`RetainedMixedTopologyTest`, `RetainedNodeTest`, `RetainedRasterTextTest`.

### Dropped, and why

* **GL/EGL backend tests** — `drawlist-gl-test.cpp`,
  `retained-raster-gl-test.cpp`, `retained-material-lighting-gl-test.cpp`.
  They need `SoGLRenderBackend` / `CoinOffscreenGLCanvas` (the legacy GL
  retained backend) and compile the backend `.cpp` in-tree; this `libCoin.so`
  does not export `SoGLRenderBackend` (the integration build is the raster-only
  Vulkan branch), so they cannot link out of tree.
* **Material cases** (out of scope for the raster subset):
  `vulkan-backend-material-test.cpp`, `retained-material-lighting-test.cpp`,
  `retained-material-coalesce-test.cpp` (and the `-gl` one above).
* **GL shader / misc GL** — `glsl-runtime-test.cpp`, `glsl-diagnostics-test.cpp`,
  `egl-binding-test.cpp`, `offscreen-readback-test.cpp`, `GLUWrapperTest.cpp`,
  `legacy-blending-test.cpp`: GL-context dependent or outside the raster subset.
* **Extractor / scene-file tests** — `StandardTests.cpp`, the
  `#ifdef COIN_TEST_SUITE` extractor blocks, `TestSuiteMain.cpp`, and the
  `models/` scene file tests.  The ported raster tests are standalone (each
  has its own `main()`), so the CoinTest/Boost runner is unnecessary.
  `CoinTest.h`, `TestSuiteUtils.*` and `TestSuiteMisc.*` are nevertheless
  vendored (built as the unused `cointest_support` static library) for parity
  with the upstream testsuite and for future extractor-based tests.

### Port adaptations (documented deviations)

1. `testsuite/vulkan/drawlist-vulkan-test.cpp` — the instance is created as
   **Vulkan 1.2** instead of 1.0.  Coin configures VMA with
   `vulkanApiVersion = VK_API_VERSION_1_2`; handing the backend a 1.0 instance
   makes the validation layer reject VMA's `vkGetBufferMemoryRequirements2` /
   `vkGetPhysicalDeviceProperties2` calls and the test segfaults at backend
   `initialize()`.  The shipping app always gives Coin a 1.2+ instance.  The
   test now passes; it still logs nested-command-buffer VUIDs because the
   standalone harness does not enable `VK_EXT_nested_command_buffer` (the app
   does), so those validation messages are expected in this harness.
2. `testsuite/scene-manager-core-test.cpp` — upstream refuses to compile when
   `COIN_HAVE_LEGACY_GL_RENDERER` is set, and this Coin is built with
   `COIN_BUILD_LEGACY_GL_RENDERER=ON`.  The APIs it checks are
   renderer-agnostic, so the port allows an opt-in define
   (`COIN_TESTSUITE_ALLOW_LEGACY_GL`, set by the CMake target) instead of
   dropping the test.  It passes.

### Known failure

* `VulkanBackendTessOverlayTest`: 3 of 4 sub-cases pass; the combined
  tessellation-edges + wireframe-overlay case fails —
  `triangle edge should be re-drawn by the tess overlay` (the pixel stays the
  green fill).  This is a genuine result against the built `coin-Integrate`
  `libCoin`; it is reported by ctest as a failure and is **not** worked around.
  Note the tests are authored from `origin/freecad-master`, while the built
  library comes from the diverged `coin-Integrate` branch, so some expectation
  drift is expected (see "Branch divergence" below).

---

## B) Python GUI probes

```bash
integrate/gui-probes/run.sh
# or: FREECAD_BUILD=/path/to/build-freecad integrate/gui-probes/run.sh
```

`run.sh` launches `build-freecad/bin/FreeCAD <probe>` with:

```
QT_STYLE_OVERRIDE=fusion
QT_QPA_PLATFORM=wayland
LD_LIBRARY_PATH=<build>/lib:<build>/src/3rdParty/coin/lib:<build>/src/3rdParty/pivy
FREECAD_USER_HOME=<private temp dir>   # see note
FC_SKIP_UNSAVED_PROMPT=1
```

Each probe writes viewport images with `view.saveImage(...)` (screen capture is
unusable — a fullscreen video owns the display) and terminates with
`os._exit(0)`; `close()`/`quit()` block while a 3D view is open.

`FREECAD_USER_HOME` is pointed at a private directory because launching a
second FreeCAD while another instance is running hits the single-instance path
and dies with `Application unexpectedly terminated: Invalid argument`.  The
isolated home also keeps the run independent of the developer's settings.

### Verification

`run.sh` reports PASS/FAIL per probe and exits non-zero if anything failed:

| Probe | What it proves |
| --- | --- |
| `geom` | box/cylinder/sphere render; 4 non-trivial images |
| `camera` | isometric/top/front/fitAll render; 4 non-trivial images |
| `edges` | wireframe + points overlays toggle; 4 non-trivial images |
| `mouse` | hover/click **real pick returns `Box`** + selection + image |
| `validation` | `FC_VULKAN_VALIDATION=1` run of `geom`: **0 VUID** |
| `gl` | GL fallback (`VulkanRenderMode=0`) renders; 1 non-trivial image |

"Non-trivial image" = exists, > 2000 bytes, and more than one colour (a blank
`saveImage` background is a single colour).  Verified result: **6 passed, 0
failed**.

To keep the validation layer quiet but present for a debug run, export
`FC_VULKAN_VALIDATION=1`; the runner already does this for the `validation`
probe only.

---

## Branch divergence (context for failures)

The C++ test sources come from the fork Coin's `origin/freecad-master`
testsuite.  The `libCoin.so` this suite runs against was built from the
integration branch (HEAD `196c75194`, branch `coin-Integrate`), which is **not**
an ancestor of `origin/freecad-master`.  Where a test fails, both facts are
possible causes; the tess-overlay failure above is the only observed one.
