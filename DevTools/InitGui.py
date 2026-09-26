"""DevTools addon - GUI initializer (thin, exec-safe shim).

IMPORTANT: FreeCAD exec()s this file without defining ``__file__``, so it must
not reference ``__file__`` and must not rely on module-scope cross-references.
All real logic lives in ``init_impl.py`` (normally imported); this file only
registers the workbench and its commands.  FreeCAD puts the addon dir on
``sys.path`` so ``import init_impl`` resolves.
"""

import FreeCADGui  # noqa: E402
import init_impl  # noqa: E402

FreeCADGui.addWorkbench(init_impl.DevToolsWorkbench)
FreeCADGui.addCommand("DevTools_McpToggle", init_impl.McpToggleCmd())
FreeCADGui.addCommand("DevTools_RunSelfTest", init_impl.RunSelfTestCmd())
