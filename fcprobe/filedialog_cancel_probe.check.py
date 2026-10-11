#!/usr/bin/env python3
"""Host-side assertions for filedialog_cancel_probe.py (FileDialog cancel path).

The probe cancels a Qt-backed native file dialog for both single-file modes and
then accepts one Save-As dialog as a positive control.  This check asserts:

  * the FileDialog "selected filter that wasn't in the original list"
    developer error does NOT appear in the captured output at all -- the
    reported bug: cancelling returns an empty QString, which was appended to the
    result list, so the helper's cancel test (selected.isEmpty()) never saw the
    cancellation and the filter-mismatch failsafe fired;
  * the error text is absent from the whole captured output;
  * the positive control ran: a dialog was cancelled, a dialog was accepted and
    the document was actually written, so the fix did not break real saves.

The probe forces Qt's own file dialog (Qt::AA_DontUseNativeDialogs): Qt's KDE
platform dialog returns a valid filter even on cancel and would hide the defect.
"""

import re

MSG = "selected filter that wasn't in the original"
RESULT = re.compile(
    r"FD_RESULT cancel_msg=(-?\d+) open_cancel_msg=(-?\d+) saved_exists=(\d+) "
    r"cancelled=(\d+) accepted=(\d+)(?: open_cancelled=(\d+))?")


def check(lines, report):
    results = [RESULT.search(line) for line in lines]
    results = [m for m in results if m]
    if not results:
        report.add_error("no FD_RESULT marker: the probe did not drive the "
                         "file dialogs")
        return
    last = results[-1]
    cancel_msg = last.group(1)
    saved_exists = last.group(3)
    cancelled = last.group(4)
    accepted = last.group(5)

    if cancel_msg == "-1":
        report.add_error("the probe timed out before it finished the phases "
                         "(watchdog result)")
    elif cancel_msg != "0":
        report.add_error(
            "cancelling the Save-As dialog logged the FileDialog "
            "filter-mismatch developer error (the cancelled dialog's empty "
            "filter is treated as a real selection)")
    # The authoritative gate is the message text in the captured output: it is
    # what the user sees, and it also works when the probe could not read its
    # own redirected log (e.g. under the host runner).
    if saved_exists != "1":
        report.add_error("positive control failed: accepting the Save-As "
                         "dialog did not write the document")
    if cancelled != "1":
        report.add_error("no file dialog was cancelled: dialog automation did "
                         "not run")
    if accepted != "1":
        report.add_error("no file dialog was accepted: dialog automation did "
                         "not run")
    if any(MSG in line for line in lines):
        report.add_error("the FileDialog filter-mismatch error text appears in "
                         "the captured output")

    report.session["filedialog_cancel"] = {
        "cancel_msg": cancel_msg,
        "open_cancel_msg": last.group(2),
        "saved_exists": saved_exists,
        "cancelled": cancelled,
        "accepted": accepted,
    }
