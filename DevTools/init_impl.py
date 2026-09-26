"""DevTools - workbench/command definitions (imported normally, not exec'd).

FreeCAD exec()s the addon's ``InitGui.py`` with quirky scope, so all real logic
lives here in a normally-imported module where ``__file__`` and module scope are
available.  ``InitGui.py`` simply imports this and registers.

The workbench exposes the two pieces of the DevTools repo that are useful from
*inside* a live FreeCAD session:

* the MCP server toggle -- start/stop the in-process socket listener from
  ``fcprobe/mcp/freecad_mcp_guest.py`` so an external MCP client can drive this
  session; and
* a runner for the host-side harness core self-test (``fcprobe/test_probe.py``).

The probe harness itself stays a host-side CLI
(``python3 fcprobe/freecad_probe.py run|suite|...``); probes are launched by it
in a fresh FreeCAD, not from this workbench.
"""

import os
import sys

import FreeCAD
import FreeCADGui
from PySide import QtCore

_WORKBENCH_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_WORKBENCH_DIR)
_FCPROBE_DIR = os.path.join(_REPO_ROOT, "fcprobe")
_MCP_DIR = os.path.join(_FCPROBE_DIR, "mcp")
_GUEST_PATH = os.path.join(_MCP_DIR, "freecad_mcp_guest.py")

_guest = None
_procs = []


def _icon():
    p = os.path.join(_WORKBENCH_DIR, "Resources", "devtools.svg")
    return p if os.path.exists(p) else None


def _load_guest():
    """Import the MCP guest in-process without auto-starting its listener."""
    global _guest
    if _guest is not None:
        return _guest
    if not os.path.isfile(_GUEST_PATH):
        raise RuntimeError("MCP guest not found at %s" % _GUEST_PATH)
    for p in (_FCPROBE_DIR, _MCP_DIR):
        if p not in sys.path:
            sys.path.insert(0, p)
    # Suppress the guest's script auto-start; the toggle owns its lifecycle.
    os.environ["FC_MCP_GUEST_NO_AUTOSTART"] = "1"
    import importlib.util
    spec = importlib.util.spec_from_file_location("freecad_mcp_guest", _GUEST_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["freecad_mcp_guest"] = mod
    spec.loader.exec_module(mod)
    _guest = mod
    return mod


def mcp_running():
    try:
        return bool(_load_guest().guest_running())
    except Exception:  # noqa: BLE001
        return False


def _set_mcp(run):
    g = _load_guest()
    if run and not g.guest_running():
        g.start_guest()
    elif not run and g.guest_running():
        g.stop_guest()
    return bool(g.guest_running())


class McpToggleCmd:
    """Start/stop the in-process MCP socket server."""
    def GetResources(self):
        running = mcp_running()
        return {"Pixmap": _icon(),
                "MenuText": "Stop MCP server" if running else "Start MCP server",
                "ToolTip": "Start or stop the in-process MCP socket server for "
                           "external clients (FC_MCP_SOCKET, default "
                           "/tmp/opencode/freecad_mcp.sock)"}

    def IsActive(self):
        return True

    def Activated(self):
        try:
            running = _set_mcp(not mcp_running())
        except Exception as exc:  # noqa: BLE001
            FreeCAD.Console.PrintError("DevTools: MCP toggle failed: %s\n" % exc)
            return
        FreeCAD.Console.PrintMessage(
            "DevTools: MCP server %s\n" % ("started" if running else "stopped"))


class RunSelfTestCmd:
    """Run fcprobe/test_probe.py (host-side core tests; no FreeCAD needed)."""
    def GetResources(self):
        return {"Pixmap": _icon(),
                "MenuText": "Run harness self-test",
                "ToolTip": "Run the fcprobe harness core self-test and print the "
                           "result in the report view"}

    def IsActive(self):
        return os.path.isfile(os.path.join(_FCPROBE_DIR, "test_probe.py"))

    def Activated(self):
        proc = QtCore.QProcess()
        proc.setProcessChannelMode(QtCore.QProcess.MergedChannels)
        proc.setProgram(sys.executable)
        proc.setArguments([os.path.join(_FCPROBE_DIR, "test_probe.py")])
        chunks = []

        def _on_read():
            chunks.append(bytes(proc.readAll()).decode("utf-8", "replace"))

        def _on_finished(code, _status):
            out = "".join(chunks)
            tail = "\n".join(out.strip().splitlines()[-10:])
            FreeCAD.Console.PrintMessage(
                "DevTools self-test: exit %d\n%s\n" % (code, tail))
            try:
                _procs.remove(proc)
            except ValueError:
                pass

        proc.readyRead.connect(_on_read)
        proc.finished.connect(_on_finished)
        _procs.append(proc)
        proc.start()
        if not proc.waitForStarted(5000):
            FreeCAD.Console.PrintError(
                "DevTools: could not start %s\n" % sys.executable)


class DevToolsWorkbench(FreeCADGui.Workbench):
    MenuText = "DevTools"
    ToolTip = ("FreeCAD dev/test tooling: the fcprobe harness and the live "
               "FreeCAD MCP server")
    Icon = ""

    def Initialize(self):
        icon = _icon()
        if icon:
            self.__class__.Icon = icon
        cmds = ["DevTools_McpToggle", "DevTools_RunSelfTest"]
        self.appendToolbar("DevTools", cmds)
        self.appendMenu("DevTools", cmds)

    def Activated(self):
        return None

    def Deactivated(self):
        return None

    def GetClassName(self):
        return "Gui::PythonWorkbench"
