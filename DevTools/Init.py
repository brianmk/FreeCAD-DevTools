"""DevTools addon - App-side initializer.

IMPORTANT: FreeCAD exec()s this file in the App process *without* setting
``__file__``, so this module must never reference ``__file__`` at import time.
All wiring is GUI-side.
"""


def startup():
    """Hook FreeCAD calls at App startup.  Nothing to do here."""
    return None
