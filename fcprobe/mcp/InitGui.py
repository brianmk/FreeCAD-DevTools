"""FreeCAD-MCP addon - GUI initializer (thin, exec-safe shim).

IMPORTANT: FreeCAD exec()s this file without defining ``__file__`` and with
quirky scope, so this file must not reference ``__file__`` and must not rely on
cross-references.  All real logic lives in ``mcp_addon.py`` (normally imported;
FreeCAD puts the addon dir on ``sys.path`` so ``import mcp_addon`` resolves).
"""

import FreeCADGui  # noqa: E402
import mcp_addon  # noqa: E402

FreeCADGui.addWorkbench(mcp_addon.FreeCADMcpWorkbench)
FreeCADGui.addCommand("FreeCADMCP_Toggle", mcp_addon.McpToggleCmd())
FreeCADGui.addCommand("FreeCADMCP_CopySocket", mcp_addon.McpCopySocketCmd())
FreeCADGui.addPreferencePage(mcp_addon.PreferencesPage, "MCP")

# Bring the socket server up/down to match the persisted preference.
mcp_addon.on_gui_start()
