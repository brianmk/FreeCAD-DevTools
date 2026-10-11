cmake_minimum_required(VERSION 3.16)
project(wide-line-lod-test CXX)

# Standalone, GPU-free test for the Vulkan raster wide-line predicate
# (CoinVulkanDetail::isWideLine / lineSegmentCount / kLargeLineSetMinSegments).
# It builds against an *already built* FreeCAD/Coin, links libCoin for the
# internal headers' out-of-line pieces and never creates a Vulkan device.
#
#   cmake -S integrate/wide-line-lod -B /tmp/wide-line-lod -G Ninja
#   cmake --build /tmp/wide-line-lod
#   ctest --test-dir /tmp/wide-line-lod --output-on-failure
#
# All Coin locations are cache variables so another build can be targeted:
#   -DCOIN_ROOT=... -DCOIN_BUILD_ROOT=... -DCOIN_INCLUDE_DIR=... -DCOIN_LIBRARY=...

enable_testing()

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

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

set(COIN_GENERATED_INCLUDE_DIR "${COIN_BUILD_ROOT}/include")
set(COIN_GENERATED_SRC_DIR "${COIN_BUILD_ROOT}/src")
set(COIN_SRC_DIR "${COIN_ROOT}/src")

foreach(_required
        "${COIN_INCLUDE_DIR}/Inventor/SoDB.h"
        "${COIN_GENERATED_SRC_DIR}/config.h"
        "${COIN_SRC_DIR}/rendering/SoVulkanRenderBackend.h"
        "${COIN_SRC_DIR}/rendering/SoVulkanRenderBackend/SoVulkanRenderBackendP.h"
        "${COIN_LIBRARY}")
  if(NOT EXISTS "${_required}")
    message(FATAL_ERROR
            "wide-line-lod: required Coin file not found: ${_required}\n"
            "Set COIN_ROOT / COIN_BUILD_ROOT / COIN_INCLUDE_DIR / COIN_LIBRARY.")
  endif()
endforeach()

set(THREADS_PREFER_PTHREAD_FLAG ON)
find_package(Threads REQUIRED)

# The private backend header includes <vulkan/vulkan.h>; the headers are enough
# (no Vulkan symbols are referenced, so nothing is linked).
find_path(VULKAN_INCLUDE_DIR NAMES vulkan/vulkan.h HINTS ENV VULKAN_SDK PATH_SUFFIXES include)

add_executable(WideLineLodTest widelinelod-test.cpp)
target_compile_features(WideLineLodTest PRIVATE cxx_std_20)
target_compile_definitions(WideLineLodTest PRIVATE COIN_BUILD_VULKAN_RENDERER=1)
target_include_directories(WideLineLodTest PRIVATE
  "${CMAKE_CURRENT_SOURCE_DIR}"
  "${COIN_INCLUDE_DIR}"
  "${COIN_GENERATED_INCLUDE_DIR}"
  "${COIN_SRC_DIR}"
  "${COIN_GENERATED_SRC_DIR}")
if(VULKAN_INCLUDE_DIR)
  target_include_directories(WideLineLodTest PRIVATE "${VULKAN_INCLUDE_DIR}")
endif()
target_link_libraries(WideLineLodTest PRIVATE "${COIN_LIBRARY}" Threads::Threads)

get_filename_component(_coin_lib_dir "${COIN_LIBRARY}" DIRECTORY)
set_target_properties(WideLineLodTest PROPERTIES BUILD_RPATH "${_coin_lib_dir}")

add_test(NAME WideLineLodTest COMMAND WideLineLodTest)
set_tests_properties(WideLineLodTest PROPERTIES LABELS raster)

message(STATUS "wide-line-lod: Coin include = ${COIN_INCLUDE_DIR}")
message(STATUS "wide-line-lod: Coin library = ${COIN_LIBRARY}")
