#!/usr/bin/env python3
"""Reproduce the FileDialog 'Save As -> Cancel' spurious developer error.

Drives Std_SaveAs twice through the *native* QFileDialog helper path:

  cancel phase -- a polling timer rejects the modal file dialog.  FreeCAD's
    report view / log must NOT contain the FileDialog
    "selected filter that wasn't in the original list" developer error.
    Before the fix it does: cancelling returns an empty QString which was
    appended to the result list, so the helper's cancel test
    (selected.isEmpty()) never saw the cancellation.
  accept phase -- the same timer fills in a path and accepts the dialog; the
    document must be written (positive control: a real save must keep working).

Emitted markers (parsed by the host script):
  FD_RESULT cancel_msg=<0|1> open_cancel_msg=<0|1> saved_exists=<0|1>
              cancelled=<0|1> accepted=<0|1> open_cancelled=<0|1>

Run (GPU sandbox recommended: without a GL context FreeCAD raises its own
"No valid GL context found!" error dialogs, which disturb dialog automation):

  HOME=<writable dir> FD_OUT=<writable dir> QT_QPA_PLATFORM=xcb \
  QT_STYLE_OVERRIDE=fusion FC_SKIP_UNSAVED_PROMPT=1 \
  build-freecad/bin/FreeCAD filedialog_cancel_probe.py
"""

import os

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtGui, QtWidgets

# Qt's platform (KDE) file dialog returns a valid filter even on cancel, which
# hides the defect; the Qt dialog returns an empty filter.  Pin the Qt dialog so
# the test exercises the same path on every machine.
_DONT_USE_NATIVE = getattr(QtCore.Qt, "AA_DontUseNativeDialogs", None)
if _DONT_USE_NATIVE is not None:
    QtCore.QCoreApplication.setAttribute(_DONT_USE_NATIVE)

OUT = os.environ.get("FD_OUT", "/tmp/fd")
os.makedirs(OUT, exist_ok=True)
LOG = open(os.path.join(OUT, "probe.log"), "w")

MSG = "selected filter that wasn't in the original"


def log(*args):
    LOG.write(" ".join(str(a) for a in args) + "\n")
    LOG.flush()


def emit(line):
    """Marker the host-side .check.py parses, on the real process stdout."""
    log(line)
    try:
        os.write(1, (line + "\n").encode())
    except OSError:
        pass


_log_seen = {"len": 0}


def new_log_text():
    """Log output produced since this function was last called."""
    path = os.environ.get("FD_LOG", os.path.join(OUT, "freecad.log"))
    try:
        with open(path, errors="replace") as fh:
            data = fh.read()
    except OSError:
        data = ""
    new = data[_log_seen["len"]:]
    _log_seen["len"] = len(data)
    return new


def report_text():
    """Text currently shown in the Report view output pane."""
    win = FreeCADGui.getMainWindow()
    holder = win.findChild(QtWidgets.QWidget, "ReportOutput")
    if holder is None:
        return ""
    for cls in (QtWidgets.QPlainTextEdit, QtWidgets.QTextEdit):
        for widget in holder.findChildren(cls):
            return widget.toPlainText()
    return ""


def widgets():
    return QtWidgets.QApplication.topLevelWidgets()


def describe(widget):
    if widget is None:
        return "None"
    try:
        return "%s(%r)" % (widget.metaObject().className(),
                           widget.windowTitle())
    except Exception:  # noqa: BLE001
        return repr(widget)


def find_file_dialog():
    """The modal QFileDialog/QFileDialog-derived widget, if present."""
    for widget in widgets():
        if widget.isVisible() and "FileDialog" in widget.metaObject().className():
            return widget
    modal = QtWidgets.QApplication.activeModalWidget()
    if modal is not None and "FileDialog" in modal.metaObject().className():
        return modal
    return None


def dump_state(tag):
    log("%s: modal=%s" % (tag, describe(QtWidgets.QApplication.activeModalWidget())))
    log("%s: top-levels=%s" % (tag, [describe(w) for w in widgets()]))


def poll(callback, attempts=60, interval=100):
    """Call callback() every `interval` ms until it returns True."""
    state = {"n": 0}

    def tick():
        state["n"] += 1
        try:
            if callback() or state["n"] >= attempts:
                timer.stop()
        except Exception:  # noqa: BLE001
            log("poll callback error:\n%s" % __import__("traceback").format_exc())
            timer.stop()

    timer = QtCore.QTimer()
    timer.timeout.connect(tick)
    timer.start(interval)
    return timer


results = {}
steps = [0]


def step():
    steps[0] += 1
    k = steps[0]
    try:
        if k == 1:
            doc = FreeCAD.newDocument("FDCancel")
            doc.addObject("Part::Box", "Box")
            doc.recompute()
            FreeCADGui.activateWorkbench("PartWorkbench")
            FreeCADGui.updateGui()
            log("doc created; report len=%d" % len(report_text()))
        elif k == 2:
            def reject():
                dlg = find_file_dialog()
                if dlg is None:
                    return False
                log("cancel: dialog=%s" % describe(dlg))
                log("cancel: reject returned %s" % dlg.reject())
                results["cancelled"] = True
                return True
            timer = poll(reject)
            log("runCommand Std_SaveAs (cancel) ...")
            FreeCADGui.runCommand("Std_SaveAs")
            timer.stop()
            QtCore.QCoreApplication.processEvents()
            text = report_text()
            results["cancel_msg"] = MSG in text or MSG in new_log_text()
            log("cancel: report len=%d HAS_MSG=%s"
                % (len(text), results["cancel_msg"]))
            log("cancel: report tail=%r" % text[-300:])
            dump_state("after-cancel")
        elif k == 3:
            def reject_open():
                dlg = find_file_dialog()
                if dlg is None:
                    return False
                log("open-cancel: dialog=%s" % describe(dlg))
                dlg.reject()
                results["open_cancelled"] = True
                return True
            timer = poll(reject_open)
            log("runCommand Std_Open (cancel) ...")
            FreeCADGui.runCommand("Std_Open")
            timer.stop()
            QtCore.QCoreApplication.processEvents()
            results["open_cancel_msg"] = MSG in new_log_text()
            log("open-cancel: HAS_MSG=%s" % results["open_cancel_msg"])
        elif k == 4:
            target = os.path.join(OUT, "saved.FCStd")

            def accept():
                dlg = find_file_dialog()
                if dlg is None:
                    return False
                log("accept: dialog=%s" % describe(dlg))
                try:
                    dlg.selectFile(target)
                except Exception as exc:  # noqa: BLE001
                    log("accept: selectFile failed: %s" % exc)
                log("accept: selectedFiles=%s" % (dlg.selectedFiles(),))
                dlg.accept()
                results["accepted"] = True
                # If accept() did not take (a dialog that validates instead of
                # closing), fall back to done(Accepted) shortly after.
                def ensure_closed():
                    # The dialog is normally destroyed by accept(); touching a
                    # deleted C++ object raises, which is a success signal here.
                    try:
                        if dlg.isVisible():
                            log("accept: dialog still visible, calling "
                                "done(Accepted)")
                            dlg.done(QtWidgets.QDialog.Accepted)
                    except RuntimeError:
                        pass
                QtCore.QTimer.singleShot(1200, ensure_closed)
                return True
            timer = poll(accept)
            log("runCommand Std_SaveAs (accept) ...")
            FreeCADGui.runCommand("Std_SaveAs")
            timer.stop()
            QtCore.QCoreApplication.processEvents()
            doc = FreeCAD.ActiveDocument
            saved = doc.FileName if doc is not None else ""
            results["saved_exists"] = bool(saved) and os.path.exists(saved)
            results["saved_path"] = saved
            log("accept: document FileName=%r exists=%s (target was %s)"
                % (saved, results["saved_exists"], target))
        elif k >= 6:
            line = ("FD_RESULT cancel_msg=%d open_cancel_msg=%d "
                    "saved_exists=%d cancelled=%d accepted=%d "
                    "open_cancelled=%d"
                    % (results.get("cancel_msg", 0),
                       results.get("open_cancel_msg", 0),
                       results.get("saved_exists", 0),
                       results.get("cancelled", 0),
                       results.get("accepted", 0),
                       results.get("open_cancelled", 0)))
            emit(line)
            # The harness needs a verdict line; the host .check.py adds the
            # authoritative assertion on the error text in the captured output.
            ok = (not results.get("cancel_msg")
                  and results.get("saved_exists")
                  and results.get("cancelled")
                  and results.get("accepted"))
            emit("[VERDICT] filedialog_cancel %s" % ("PASS" if ok else "FAIL"))
            log("DONE")
            LOG.close()
            os._exit(0)
    except Exception:  # noqa: BLE001
        import traceback

        log("EXCEPTION:\n%s" % traceback.format_exc())
        LOG.close()
        os._exit(1)
    QtCore.QTimer.singleShot(900, step)


def watchdog():
    log("WATCHDOG: run did not finish; writing partial result")
    line = ("FD_RESULT cancel_msg=%d open_cancel_msg=%d saved_exists=%d "
            "cancelled=%d accepted=%d"
            % (results.get("cancel_msg", -1),
               results.get("open_cancel_msg", -1),
               results.get("saved_exists", 0),
               results.get("cancelled", 0),
               results.get("accepted", 0)))
    emit(line)
    LOG.close()
    os._exit(4)


# Hard watchdog: never leave a modal dialog blocking the run.
QtCore.QTimer.singleShot(120000, watchdog)
QtCore.QTimer.singleShot(2500, step)
