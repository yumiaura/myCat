"""Qt dialog for creating a custom AI-generated desktop character."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from . import ai_char, char_catalog, secret_store
from .ui_theme import LIGHT_QSS


class GenerationSignals(QtCore.QObject):
    completed = QtCore.Signal(str, str)
    failed = QtCore.Signal(str)


class GenerationWorker(QtCore.QRunnable):
    def __init__(
        self,
        name: str,
        paths: list[Path],
        api_key: str,
        quality: str,
        additional_instructions: str = "",
    ) -> None:
        super().__init__()
        self.name = name
        self.paths = paths
        self.api_key = api_key
        self.quality = quality
        self.additional_instructions = additional_instructions
        self.signals = GenerationSignals()

    def run(self) -> None:
        try:
            char_id, path = ai_char.generate_character(
                self.name,
                self.paths,
                self.api_key,
                quality=self.quality,
                additional_instructions=self.additional_instructions,
            )
        except Exception as exc:  # noqa: BLE001 - error is shown in the dialog
            self.signals.failed.emit(str(exc))
        else:
            self.signals.completed.emit(char_id, str(path))


class AICharDialog(QtWidgets.QDialog):
    character_created = QtCore.Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create a custom cat with AI")
        self.setMinimumWidth(520)
        self.setStyleSheet(LIGHT_QSS)
        self.pool = QtCore.QThreadPool(self)
        self.reference_paths: list[Path] = []

        intro = QtWidgets.QLabel(
            "Choose 1–3 photos of the same person. OpenAI will turn their visual features "
            "into one chibi kitten desktop character. The reference photos are not stored by myCat."
        )
        intro.setWordWrap(True)

        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("Example: Mina chibi cat")
        self.key_edit = QtWidgets.QLineEdit()
        self.key_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        saved_key = secret_store.get_secret(ai_char.SECRET_NAME)
        self.key_edit.setText(saved_key or os.getenv("OPENAI_API_KEY", ""))
        self.key_edit.setPlaceholderText("sk-… (or OPENAI_API_KEY)")

        self.remember_box = QtWidgets.QCheckBox("Remember key in the operating system keyring")
        self.remember_box.setChecked(bool(saved_key))
        self.remember_box.setEnabled(secret_store.keyring_available())
        if not self.remember_box.isEnabled():
            self.remember_box.setToolTip("Install mycat[secure] and configure an OS keyring to enable this.")

        self.quality_combo = QtWidgets.QComboBox()
        self.quality_combo.addItem("Low — lower cost, recommended for a desktop mascot", "low")
        self.quality_combo.addItem("Medium — more detail, higher cost", "medium")

        self.details_edit = QtWidgets.QPlainTextEdit()
        self.details_edit.setPlaceholderText(
            'Optional. Example: "Add round glasses and make the blouse say LOVE in red letters."'
        )
        self.details_edit.setMaximumHeight(90)
        self.details_edit.setToolTip(
            f"Optional visual instructions, up to {ai_char.MAX_ADDITIONAL_INSTRUCTIONS} characters."
        )

        self.reference_list = QtWidgets.QListWidget()
        self.reference_list.setIconSize(QtCore.QSize(64, 64))
        self.reference_list.setMinimumHeight(110)
        add_btn = QtWidgets.QPushButton("Add photos…")
        remove_btn = QtWidgets.QPushButton("Remove selected")
        add_btn.clicked.connect(self.add_references)
        remove_btn.clicked.connect(self.remove_selected)
        photo_buttons = QtWidgets.QHBoxLayout()
        photo_buttons.addWidget(add_btn)
        photo_buttons.addWidget(remove_btn)
        photo_buttons.addStretch(1)

        form = QtWidgets.QFormLayout()
        form.addRow("Character name", self.name_edit)
        form.addRow("OpenAI API key", self.key_edit)
        form.addRow("", self.remember_box)
        form.addRow("Quality", self.quality_combo)
        form.addRow("Additional details", self.details_edit)

        self.status_label = QtWidgets.QLabel("")
        self.status_label.setWordWrap(True)
        self.generate_btn = QtWidgets.QPushButton("Generate and save")
        close_btn = QtWidgets.QPushButton("Close")
        self.generate_btn.clicked.connect(self.generate)
        close_btn.clicked.connect(self.reject)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.generate_btn)
        buttons.addWidget(close_btn)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(QtWidgets.QLabel("Reference photos (maximum 3)"))
        layout.addWidget(self.reference_list)
        layout.addLayout(photo_buttons)
        layout.addWidget(self.status_label)
        layout.addLayout(buttons)

    def set_status(self, text: str, *, error: bool = False) -> None:
        self.status_label.setStyleSheet("color: #c0392b;" if error else "color: #555555;")
        self.status_label.setText(text)

    def add_references(self) -> None:
        remaining = ai_char.MAX_REFERENCES - len(self.reference_paths)
        if remaining <= 0:
            self.set_status("You already selected the maximum of 3 photos.", error=True)
            return
        names, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "Choose reference photos",
            "",
            "Images (*.png *.jpg *.jpeg *.webp);;All files (*)",
        )
        for name in names[:remaining]:
            path = Path(name)
            if path in self.reference_paths:
                continue
            self.reference_paths.append(path)
            icon = QtGui.QIcon(str(path))
            item = QtWidgets.QListWidgetItem(icon, path.name)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(str(path))
            self.reference_list.addItem(item)
        if len(names) > remaining:
            self.set_status("Only the first 3 photos were added.")

    def remove_selected(self) -> None:
        for item in self.reference_list.selectedItems():
            path = Path(item.data(QtCore.Qt.ItemDataRole.UserRole))
            if path in self.reference_paths:
                self.reference_paths.remove(path)
            self.reference_list.takeItem(self.reference_list.row(item))

    def generate(self) -> None:
        name = self.name_edit.text().strip()
        key = self.key_edit.text().strip() or os.getenv("OPENAI_API_KEY", "")
        try:
            char_id = ai_char.slugify(name)
        except ai_char.AICharError as exc:
            self.set_status(str(exc), error=True)
            return
        if not self.reference_paths:
            self.set_status("Choose at least one reference photo.", error=True)
            return
        if not key:
            self.set_status("Enter an OpenAI API key.", error=True)
            return
        details = self.details_edit.toPlainText().strip()
        try:
            ai_char.build_prompt(details)
        except ai_char.AICharError as exc:
            self.set_status(str(exc), error=True)
            return
        if char_catalog.find_char(char_id) is not None:
            answer = QtWidgets.QMessageBox.question(
                self,
                "Replace character?",
                f'A character named "{char_id}" already exists. Replace it with a new generation?',
            )
            if answer != QtWidgets.QMessageBox.StandardButton.Yes:
                return
        if self.remember_box.isChecked():
            if not secret_store.set_secret(ai_char.SECRET_NAME, key):
                self.set_status("The keyring could not save the key. Generation will continue.", error=True)
        elif secret_store.get_secret(ai_char.SECRET_NAME):
            secret_store.delete_secret(ai_char.SECRET_NAME)

        self.generate_btn.setEnabled(False)
        self.set_status("Generating… this can take up to two minutes. One API request will be charged.")
        worker = GenerationWorker(
            name,
            list(self.reference_paths),
            key,
            self.quality_combo.currentData(),
            details,
        )
        worker.signals.completed.connect(self.on_completed)
        worker.signals.failed.connect(self.on_failed)
        self.pool.start(worker)

    def on_completed(self, char_id: str, _path: str) -> None:
        self.generate_btn.setEnabled(True)
        self.set_status("Saved. Reusing this character does not call the API again.")
        self.character_created.emit(char_id)
        self.accept()

    def on_failed(self, message: str) -> None:
        self.generate_btn.setEnabled(True)
        self.set_status(message, error=True)


__all__ = ["AICharDialog", "GenerationWorker"]
