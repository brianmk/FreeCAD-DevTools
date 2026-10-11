cmake_minimum_required(VERSION 3.16)
project(coin-vulkan-tests CXX)

# Out-of-tree build of the Coin raster (Vulkan + retained-IR) testsuite subset
# against an already-built bundled Coin.  See integrate/README.md for the
# rationale and the list of dropped tests.

enable_testing()

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# ---------------------------------------------------------------------------
# Coin locations.  Every one is a cache variable so a different FreeCAD/Coin
# build can be targeted with -D<VAR>=...
#   cmake -S integrate/coin-vulkan-tests -B build -G Ninja \
#         -DCOIN_ROOT=/path/to/coin \
#         -DCOIN_BUILD_ROOT=/path/to/build/coin \
#         -DCOIN_LIBRARY=/path/to/build/lib/libCoin.so
# ---------------------------------------------------------------------------
set(COIN_ROOT
    "/home/phantom/dev/FreeCAD-Integrate/FreeCAD-vulkan/src/3rdParty/coin"
    CACHE PATH "Coin source tree (for the internal rendering/*.h headers)")

set(COIN_BUILD_ROOT
    "/home/phantom/dev/FreeCAD-Integrate/build-freecad/src/3rdParty/coin"
    CACHE PATH "Coin build tree (generated config.h and generated headers)")

set(COIN_INCLUDE_DIR
    "${COIN_ROOT}/include"
    CACHE PATH "Coin public include directory")

set(COIN_LIBRARY
    "/home/phantom/dev/FreeCAD-Integrate/build-freecad/lib/libCoin.so"
    CACHE FILEPATH "libCoin shared library to link against")

# Derived include directories.
set(COIN_GENERATED_INCLUDE_DIR "${COIN_BUILD_ROOT}/include")
set(COIN_GENERATED_SRC_DIR "${COIN_BUILD_ROOT}/src")
set(COIN_SRC_DIR "${COIN_ROOT}/src")

foreach(_required
        "${COIN_INCLUDE_DIR}/Inventor/SoDB.h"
        "${COIN_GENERATED_SRC_DIR}/config.h"
        "${COIN_SRC_DIR}/rendering/SoVulkanRenderBackend.h"
        "${COIN_LIBRARY}")
  if(NOT EXISTS "${_required}")
    message(FATAL_ERROR
            "coin-vulkan-tests: required Coin file not found: ${_required}\n"
            "Set COIN_ROOT / COIN_BUILD_ROOT / COIN_INCLUDE_DIR / COIN_LIBRARY.")
  endif()
endforeach()

# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------
set(THREADS_PREFER_PTHREAD_FLAG ON)
find_package(Threads REQUIRED)

# The system has the Vulkan loader + headers but no CMake package config, so
# locate them directly (overridable).
if(NOT VULKAN_INCLUDE_DIR)
  find_path(VULKAN_INCLUDE_DIR NAMES vulkan/vulkan.h
            HINTS ENV VULKAN_SDK PATH_SUFFIXES include)
endif()
if(NOT VULKAN_LIBRARY)
  find_library(VULKAN_LIBRARY NAMES vulkan vulkan-1
               HINTS ENV VULKAN_SDK PATH_SUFFIXES lib lib64)
endif()
if(NOT VULKAN_LIBRARY)
  set(VULKAN_LIBRARY "vulkan")
endif()

# ---------------------------------------------------------------------------
# Test helper.  A test that returns 77 is reported as skipped (no Vulkan
# device / missing feature).
# ---------------------------------------------------------------------------
function(cvkt_add_test name)
  cmake_parse_arguments(PARSE_ARGV 1 arg "VULKAN;ALLOW_LEGACY_GL" "" "SOURCES")

  add_executable(${name} ${arg_SOURCES})
  target_compile_features(${name} PRIVATE cxx_std_20)
  target_compile_definitions(${name} PRIVATE COIN_BUILD_VULKAN_RENDERER=1)
  if(arg_ALLOW_LEGACY_GL)
    target_compile_definitions(${name} PRIVATE COIN_TESTSUITE_ALLOW_LEGACY_GL=1)
  endif()

  target_include_directories(${name} PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/testsuite"
    "${CMAKE_CURRENT_SOURCE_DIR}/testsuite/vulkan"
    "${COIN_INCLUDE_DIR}"
    "${COIN_GENERATED_INCLUDE_DIR}"
    "${COIN_SRC_DIR}"
    "${COIN_GENERATED_SRC_DIR}")

  target_link_libraries(${name} PRIVATE "${COIN_LIBRARY}" Threads::Threads)

  if(arg_VULKAN)
    if(VULKAN_INCLUDE_DIR)
      target_include_directories(${name} PRIVATE "${VULKAN_INCLUDE_DIR}")
    endif()
    target_link_libraries(${name} PRIVATE "${VULKAN_LIBRARY}")
  endif()

  # Make ctest able to find libCoin (and a non-system Vulkan loader) without a
  # hand-exported LD_LIBRARY_PATH.
  get_filename_component(_coin_lib_dir "${COIN_LIBRARY}" DIRECTORY)
  set(_rpaths "${_coin_lib_dir}")
  if(IS_ABSOLUTE "${VULKAN_LIBRARY}")
    get_filename_component(_vulkan_lib_dir "${VULKAN_LIBRARY}" DIRECTORY)
    list(APPEND _rpaths "${_vulkan_lib_dir}")
  endif()
  set_target_properties(${name} PROPERTIES BUILD_RPATH "${_rpaths}")

  add_test(NAME ${name} COMMAND ${name})
  set_tests_properties(${name} PROPERTIES SKIP_RETURN_CODE 77 LABELS raster)
endfunction()

# ---------------------------------------------------------------------------
# Shared test utilities.  The ported raster tests are standalone (each has its
# own main()), so none of them link this; it is vendored for parity with the
# Coin testsuite and for future extractor-based tests.  See README.
# ---------------------------------------------------------------------------
add_library(cointest_support STATIC
  testsuite/TestSuiteUtils.cpp
  testsuite/TestSuiteMisc.cpp)
target_compile_features(cointest_support PRIVATE cxx_std_20)
target_compile_definitions(cointest_support PRIVATE COIN_BUILD_VULKAN_RENDERER=1)
target_include_directories(cointest_support PRIVATE
  "${CMAKE_CURRENT_SOURCE_DIR}/testsuite"
  "${COIN_INCLUDE_DIR}"
  "${COIN_GENERATED_INCLUDE_DIR}"
  "${COIN_SRC_DIR}"
  "${COIN_GENERATED_SRC_DIR}")
target_link_libraries(cointest_support PUBLIC "${COIN_LIBRARY}" Threads::Threads)

# ---------------------------------------------------------------------------
# Headless Vulkan raster backend tests (each creates its own instance/device;
# they skip with 77 when no usable device is present).
# ---------------------------------------------------------------------------
set(CVKT_VULKAN_TESTS
  DrawListVulkanTest                 vulkan/drawlist-vulkan-test.cpp
  VulkanBackendLifecycleTest         vulkan/vulkan-backend-lifecycle-test.cpp
  VulkanBackendRenderExternalTest    vulkan/vulkan-backend-render-external-test.cpp
  VulkanBackendTextOverlayTest       vulkan/vulkan-backend-text-overlay-test.cpp
  VulkanBackendMixedTopologyTest     vulkan/vulkan-backend-mixed-topology-test.cpp
  VulkanBackendFragmentOutputTest    vulkan/vulkan-backend-fragment-output-test.cpp
  VulkanBackendDepthTest             vulkan/vulkan-backend-depth-test.cpp
  VulkanBackendCullingTest           vulkan/vulkan-backend-culling-test.cpp
  VulkanBackendLightingTest          vulkan/vulkan-backend-lighting-test.cpp
  VulkanBackendTextureModelsTest     vulkan/vulkan-backend-texture-models-test.cpp
  VulkanBackendMultitexStagingTest   vulkan/vulkan-backend-multitex-staging-test.cpp
  VulkanBackendScissorTest           vulkan/vulkan-backend-scissor-test.cpp
  VulkanBackendClearTest             vulkan/vulkan-backend-clear-test.cpp
  VulkanBackendYFlipTest             vulkan/vulkan-backend-yflip-test.cpp
  VulkanBackendStencilTest           vulkan/vulkan-backend-stencil-test.cpp
  VulkanBackendTessOverlayTest       vulkan/vulkan-backend-tess-overlay-test.cpp
  VulkanBackendRetainedChangeTest    vulkan/vulkan-backend-retained-change-test.cpp
  VulkanBackendParallelTest          vulkan/vulkan-backend-parallel-test.cpp
  VulkanRenderManagerTest            vulkan/vulkan-rendermanager-test.cpp
  VulkanRenderManagerVisibilityTest  vulkan/vulkan-rendermanager-visibility-test.cpp
  VulkanLightStabilityTest           vulkan/vulkan-light-stability-test.cpp)

list(LENGTH CVKT_VULKAN_TESTS _n)
math(EXPR _pairs "${_n} / 2")
set(_i 0)
while(_i LESS _pairs)
  math(EXPR _off "${_i} * 2")
  list(GET CVKT_VULKAN_TESTS ${_off} _name)
  math(EXPR _off2 "${_off} + 1")
  list(GET CVKT_VULKAN_TESTS ${_off2} _src)
  cvkt_add_test(${_name} VULKAN SOURCES "testsuite/${_src}")
  math(EXPR _i "${_i} + 1")
endwhile()

# ---------------------------------------------------------------------------
# Retained-IR / core traversal tests (no GPU required).
# ---------------------------------------------------------------------------
cvkt_add_test(CoreTraversalTest          SOURCES testsuite/core-traversal-test.cpp)
cvkt_add_test(DrawListSortStabilityTest  SOURCES testsuite/drawlist-sort-stability-test.cpp)
cvkt_add_test(RetainedIRTest             SOURCES testsuite/retained-ir-test.cpp)
cvkt_add_test(RetainedMixedTopologyTest  SOURCES testsuite/retained-mixed-topology-test.cpp)
cvkt_add_test(RetainedNodeTest           SOURCES testsuite/retained-node-test.cpp)
cvkt_add_test(RetainedRasterTextTest     SOURCES testsuite/retained-raster-text-test.cpp)

# This Coin build has COIN_BUILD_LEGACY_GL_RENDERER=ON; upstream only compiles
# this test when the legacy renderer is off, so opt in explicitly (the APIs it
# checks are renderer-agnostic and pass).  See README.
cvkt_add_test(SceneManagerCoreTest
  ALLOW_LEGACY_GL SOURCES testsuite/scene-manager-core-test.cpp)

message(STATUS "coin-vulkan-tests: Coin include  = ${COIN_INCLUDE_DIR}")
message(STATUS "coin-vulkan-tests: Coin build    = ${COIN_BUILD_ROOT}")
message(STATUS "coin-vulkan-tests: Coin library  = ${COIN_LIBRARY}")
message(STATUS "coin-vulkan-tests: Vulkan lib    = ${VULKAN_LIBRARY}")
