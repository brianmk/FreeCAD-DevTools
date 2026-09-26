#!/usr/bin/env python3
"""Authoring test for the optional PBR roughness map.

Builds a Part::Box, assigns an App::Material that carries both a base-color
image (unit 0) and a roughness image (unit 1) plus a physical-material scalar
roughness, then asserts the appearance authoring wired the texture units and
the physical-material strengths into the Coin scene graph the Vulkan renderer
consumes.

Run:
  python3 tools/fcprobe/freecad_probe.py run \\
      tools/fcprobe/vk_pbrmap_probe.py --profile vulkan
"""

import os
import sys

import FreeCAD
import FreeCADGui
from PySide import QtCore

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from freecad_probe import Session  # noqa: E402

VIEW = "User parameter:BaseApp/Preferences/View"

# 2x2 PNGs (base red, roughness dark) -- BitmapFactory decodes PNG via QImage.
BASE_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEklEQVR4nGM4YWNzwsaGAUIBACU+"
    "BQE37XHpAAAAAElFTkSuQmCC"
)
ROUGH_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAADklEQVR4nGMQAQMGCAUABp4A8UKt"
    "Z7MAAAAASUVORK5CYII="
)


def log(msg):
    print("PBRMAP " + msg, file=sys.stderr)


s = Session(name="pbrmap")


def walk(node, out):
    out.append(node)
    n = -1
    try:
        n = node.getNumChildren()
    except Exception:
        n = -1
    if n and n > 0:
        for i in range(n):
            walk(node.getChild(i), out)


def image_is_set(texture2):
    # pivy materializes an explicitly-set SoSFImage pixel buffer as an
    # undecodable str, so getValue() raises for a set image and returns
    # (None, size) for the untouched default (Coin's checker).  isDefault()
    # cannot be used: SoTexture2's default IS a checker, so it is never
    # "default".
    try:
        value = texture2.image.getValue()
    except Exception:
        return True
    return value is not None and value[0] is not None


def build():
    for name in list(FreeCAD.listDocuments()):
        FreeCAD.closeDocument(name)
    doc = FreeCAD.newDocument("PbrMap")
    box = doc.addObject("Part::Box", "Box")
    box.Length = 20
    box.Width = 20
    box.Height = 20

    mat = FreeCAD.Material()
    mat.AmbientColor = (0.0, 0.0, 0.0)
    mat.DiffuseColor = (0.8, 0.2, 0.2)
    mat.SpecularColor = (0.5, 0.5, 0.5)
    mat.Shininess = 0.5
    mat.Image = BASE_PNG
    mat.RoughnessImage = ROUGH_PNG
    mat.NormalImage = BASE_PNG
    mat.EmissiveImage = BASE_PNG
    mat.UsePhysicalMaterial = True
    mat.Metallic = 1.0
    mat.Roughness = 0.9
    mat.RoughnessStrength = 0.7
    mat.NormalStrength = 0.5
    mat.EmissiveIntensity = 0.25
    box.ViewObject.ShapeAppearance = [mat]
    doc.recompute()
    return box


def inspect(box):
    from pivy import coin

    root = box.ViewObject.RootNode
    nodes = []
    walk(root, nodes)
    log("nodes=%d" % len(nodes))

    units = [x for x in nodes if x.isOfType(coin.SoTextureUnit.getClassTypeId())]
    unit_values = sorted(int(x.unit.getValue()) for x in units)
    log("texture_units=%s" % unit_values)
    s.expect("roughness texture unit present", 1 in unit_values,
             "units=%s" % unit_values)

    textures = [x for x in nodes if x.isOfType(coin.SoTexture2.getClassTypeId())]
    nonempty = sum(1 for x in textures if image_is_set(x))
    log("textures=%d nonempty=%d" % (len(textures), nonempty))
    # base + roughness + normal + emissive (each visited twice in the graph).
    s.expect("base and PBR map images authored", nonempty >= 6,
             "nonempty=%d" % nonempty)

    physicals = [
        x for x in nodes if x.isOfType(coin.SoPhysicalMaterial.getClassTypeId())
    ]
    log("physical_nodes=%d" % len(physicals))
    if physicals:
        node = physicals[0]
        strength = float(node.roughnessStrength.getValue())
        normal_strength = float(node.normalStrength.getValue())
        emissive = float(node.emissiveIntensity.getValue())
        enabled = bool(node.enabled.getValues()[0])
        metalness = float(node.metalness.getValues()[0])
        log("physical strength=%s normal=%s emissive=%s enabled=%s metalness=%s"
            % (strength, normal_strength, emissive, enabled, metalness))
        s.expect("roughness strength authored", abs(strength - 0.7) < 1e-4,
                 "strength=%s" % strength)
        s.expect("normal strength authored", abs(normal_strength - 0.5) < 1e-4,
                 "normal=%s" % normal_strength)
        s.expect("emissive intensity authored", abs(emissive - 0.25) < 1e-4,
                 "emissive=%s" % emissive)
        s.expect("physical material enabled", enabled, "enabled=%s" % enabled)
    else:
        s.expect("physical material node present", False, "none found")


def step():
    s.set_pref(VIEW, "UseVulkanRenderer", True)
    try:
        box = build()
    except Exception as exc:
        s.error("build failed: %s" % exc)
        return
    s.frame_phase("pbrmap-built")

    def check():
        try:
            inspect(box)
        except Exception as exc:
            s.error("inspect failed: %s" % exc)
            return
        s.snapshot()
        s.finish()
        FreeCADGui.getMainWindow().close()

    QtCore.QTimer.singleShot(800, check)


QtCore.QTimer.singleShot(500, step)
