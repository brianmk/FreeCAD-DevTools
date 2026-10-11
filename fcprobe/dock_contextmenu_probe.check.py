#!/usr/bin/env python3
"""Host-side assertions for dock_contextmenu_probe.py.

The probe docks the Report view and the Python console, gives each dock a
native (non-top level) window -- the state in which Qt rejects the popup's
transient parent -- and opens the real context menu on both.  This check
asserts:

  * the menus actually opened (otherwise "no warning" would be vacuous);
  * Qt's "QWidgetWindow(...) must be a top level window." warning does not
    appear in the captured output for either view;
  * the probe reached both phases.

The message text check is authoritative: it is what the user sees, and it also
works when the harness captures the process output instead of the probe's log.
"""

import re

WARN = "must be a top level window"
RESULT = re.compile(
    r"DOCKMENU_RESULT reportview=(-?\d+) pythonconsole=(-?\d+) opened=(\d+) "
    r"found=(\d+)")


def check(lines, report):
    results = [RESULT.search(line) for line in lines]
    results = [m for m in results if m]
    if not results:
        report.add_error("no DOCKMENU_RESULT marker: the probe did not open "
                         "the dock context menus")
        return
    last = results[-1]
    reportview, pythonconsole, opened, found = last.groups()

    if found != "1":
        report.add_error("the Report view dock/text widget was not found")
    if opened != "1":
        report.add_error("no context menu opened: the warning assertions would "
                         "be vacuous")
    if reportview == "-1" or pythonconsole == "-1":
        report.add_error("the probe timed out before it finished the phases")
    if any(WARN in line for line in lines):
        report.add_error("Qt's 'must be a top level window.' warning appears in "
                         "the captured output (a dock context menu resolved its "
                         "transient parent to a native child window)")

    report.session["dock_contextmenu"] = {
        "reportview_warned": reportview,
        "pythonconsole_warned": pythonconsole,
        "menu_opened": opened,
        "docks_found": found,
    }
