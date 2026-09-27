"""FreeCAD-MCP addon - workbench, commands and guest-socket lifecycle.

Imported by ``InitGui.py`` (the addon dir is on ``sys.path``).  The actual
socket server is ``freecad_mcp_guest.py`` shipped beside this file; we import it
with its import-time auto-start suppressed and open/close the listener from the
persisted preference (default ON) so a normally-launched FreeCAD is immediately
drivable by ``freecad_mcp_server.py``.
"""

import os
import sys

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtWidgets

ADDON_DIR = os.path.dirname(os.path.abspath(__file__))

# Resolve symlinks: a dev checkout is often symlinked into FreeCAD's Mod dir, and
# the cursor/click/screenshot tools import ``freecad_probe.Session`` from the
# fcprobe harness one level up.  ``abspath`` alone would leave that at Mod/.
_REAL_DIR = os.path.dirname(os.path.realpath(__file__))
_HARNESS_DIR = os.path.dirname(_REAL_DIR)
if (os.path.exists(os.path.join(_HARNESS_DIR, "freecad_probe.py"))
        and _HARNESS_DIR not in sys.path):
    sys.path.insert(0, _HARNESS_DIR)

# The addon drives start/stop itself, so suppress the guest's import-time
# auto-run (it would otherwise open the socket as a side effect of import).
os.environ["FC_MCP_GUEST_NO_AUTOSTART"] = "1"
import freecad_mcp_guest as guest  # noqa: E402

_PREF = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/FreeCAD-MCP")
_ICON = os.path.join(ADDON_DIR, "Resources", "freecad_mcp.svg")


def _icon():
    return _ICON if os.path.exists(_ICON) else None


# ---------------------------------------------------------------------------
# socket server control
# ---------------------------------------------------------------------------

def is_running():
    try:
        return bool(guest.guest_running())
    except Exception:  # noqa: BLE001
        return False


def start():
    return guest.start_guest()


def stop():
    return guest.stop_guest()


def socket_path():
    return guest.SOCKET_PATH


def enabled():
    """The persisted setting (independent of the live state)."""
    return _PREF.GetBool("McpEnabled", True)


def set_enabled(value):
    """Persist the setting and bring the socket server up/down to match."""
    value = bool(value)
    _PREF.SetBool("McpEnabled", value)
    try:
        return start() if value else stop()
    except Exception:  # noqa: BLE001
        return is_running()


def toggle():
    return set_enabled(not is_running())


def on_gui_start():
    """Start the server (if enabled) once the GUI event loop is running."""
    def _start():
        if enabled():
            try:
                start()
            except Exception:  # noqa: BLE001
                pass

    QtCore.QTimer.singleShot(0, _start)


# ---------------------------------------------------------------------------
# workbench + commands
# ---------------------------------------------------------------------------

class FreeCADMcpWorkbench(FreeCADGui.Workbench):
    MenuText = "MCP"
    ToolTip = "FreeCAD MCP server - drive this session from an MCP client"
    Icon = _icon()

    def Initialize(self):
        self.appendToolbar("MCP", ["FreeCADMCP_Toggle", "FreeCADMCP_CopySocket"])
        self.appendMenu("MCP", ["FreeCADMCP_Toggle", "FreeCADMCP_CopySocket"])

    def GetClassName(self):
        # Must be the Python workbench type, otherwise appendToolbar/appendMenu
        # fail with "'FreeCADMcpWorkbench' object has no attribute '__Workbench__'".
        return "Gui::PythonWorkbench"


class McpToggleCmd:
    """Start/stop the MCP socket server."""

    def GetResources(self):
        return {"Pixmap": _icon(), "MenuText": "Toggle MCP Server",
                "ToolTip": "Start or stop the MCP socket server"}

    def IsActive(self):
        return True

    def Activated(self):
        toggle()


class McpCopySocketCmd:
    """Copy the Unix socket path an MCP server connects to."""

    def GetResources(self):
        return {"Pixmap": _icon(), "MenuText": "Copy MCP Socket Path",
                "ToolTip": "Copy the Unix socket path an MCP server connects to"}

    def IsActive(self):
        return True

    def Activated(self):
        cb = QtWidgets.QApplication.clipboard()
        if cb is not None:
            cb.setText(socket_path())


class PreferencesPage:
    """Editor for BaseApp/Preferences/Mod/FreeCAD-MCP -> McpEnabled."""

    def __init__(self):
        self.form = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.form)
        self._cb = QtWidgets.QCheckBox(
            "Start the MCP socket server when FreeCAD starts")
        self._cb.setChecked(enabled())
        layout.addWidget(self._cb)
        self._path = QtWidgets.QLabel("Socket: " + socket_path())
        self._path.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        layout.addWidget(self._path)
        layout.addStretch(1)

    def saveSettings(self):
        set_enabled(self._cb.isChecked())
