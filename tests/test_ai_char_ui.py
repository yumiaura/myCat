"""AI character dialog — click-to-copy, and the generate/preview/save flow."""

import io

from PIL import Image
from PySide6 import QtCore, QtWidgets

from mycat import char_catalog
from mycat.ai_char_ui import AICharDialog


def png_bytes(size=(400, 600), color=(150, 190, 230, 255)):
    output = io.BytesIO()
    Image.new("RGBA", size, color).save(output, "PNG")
    return output.getvalue()


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


def test_save_is_disabled_until_a_generation_lands(qapp):
    dialog = AICharDialog()
    assert dialog.save_btn.isEnabled() is False
    assert dialog.generated_image is None


def test_on_generated_stores_image_enables_save_and_previews(qapp):
    dialog = AICharDialog()
    dialog.show()
    qapp.processEvents()
    image = png_bytes()
    dialog.on_generated(image)
    assert dialog.generated_image == image
    assert dialog.save_btn.isEnabled() is True
    assert not dialog.preview_label.pixmap().isNull()


def test_save_installs_the_char_emits_and_closes(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(char_catalog, "user_chars_dir", lambda: tmp_path)
    dialog = AICharDialog()
    dialog.name_edit.setText("Preview Cat")
    dialog.on_generated(png_bytes())

    created = []
    dialog.character_created.connect(created.append)
    dialog.save_character()

    assert created == ["custom-preview-cat"]
    assert dialog.result() == QtWidgets.QDialog.DialogCode.Accepted
    assert list(tmp_path.glob("*.zip"))


def test_save_without_a_generation_does_nothing(qapp):
    dialog = AICharDialog()
    dialog.name_edit.setText("Nope")
    dialog.save_character()  # generated_image is None → no-op
    assert dialog.result() != QtWidgets.QDialog.DialogCode.Accepted
