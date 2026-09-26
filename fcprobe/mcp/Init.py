"""FreeCAD-MCP addon - App-side initializer.

FreeCAD exec()s this file in the App process *without* setting ``__file__``, so
it must not reference ``__file__``.  The guest socket is a GUI concern and is
started from ``InitGui.py``; a headless session (FreeCADCmd has no GUI addon
loader) still uses ``FreeCADCmd freecad_mcp_guest.py`` directly.
"""


def startup():
    """Hook FreeCAD calls at App startup.  Nothing to do - socket is GUI-side."""
    return None
