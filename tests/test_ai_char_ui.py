"""AI character dialog — click-to-copy on the error status line."""

from PySide6 import QtCore, QtWidgets

from mycat.ai_char_ui import AICharDialog


def test_error_status_is_clickable_and_copies(qapp):
    dialog = AICharDialog()
    dialog.set_status("Stable Diffusion error (500): OutOfMemoryError.", error=True)
    assert dialog.status_label.cursor().shape() == QtCore.Qt.CursorShape.PointingHandCursor
    assert dialog.status_label.toolTip()

    dialog.status_label.clicked.emit()
    assert QtWidgets.QApplication.clipboard().text() == "Stable Diffusion error (500): OutOfMemoryError."
    assert dialog.status_label.text() == "Copied to clipboard."


def test_non_error_status_does_not_copy(qapp):
    dialog = AICharDialog()
    QtWidgets.QApplication.clipboard().setText("keep-me")
    dialog.set_status("Generating…", error=False)
    assert dialog.status_label.cursor().shape() == QtCore.Qt.CursorShape.ArrowCursor

    dialog.status_label.clicked.emit()
    assert QtWidgets.QApplication.clipboard().text() == "keep-me"


def test_restore_error_brings_the_message_back_after_the_flash(qapp):
    dialog = AICharDialog()
    message = "Stable Diffusion error (500): sampler not found."
    dialog.set_status(message, error=True)

    dialog.status_label.clicked.emit()
    assert dialog.status_label.text() == "Copied to clipboard."
    dialog.restore_error(message)
    assert dialog.status_label.text() == message
