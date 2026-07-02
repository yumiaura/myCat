"""Chat vendor settings dialog: pick a vendor (Ollama / OpenAI / Grok / … or a
custom one), fetch and choose a model, test the connection, save."""

from __future__ import annotations

import logging
import os
import time

from PySide6 import QtCore, QtWidgets

from . import llm_ollama, llm_openai_compat, llm_prompt, llm_vendors
from .ui_theme import LIGHT_QSS

logger = logging.getLogger(__name__)

STATUS_OK = "color: #1c7c2f;"
STATUS_ERR = "color: #c0392b;"
STATUS_INFO = "color: #555555;"

ADD_CUSTOM = "➕ Add custom…"
TEST_TIMEOUT = 30.0


class ProbeSignals(QtCore.QObject):
    models = QtCore.Signal(list)
    tested = QtCore.Signal(float, str)
    error = QtCore.Signal(str)


class ModelsWorker(QtCore.QRunnable):
    """Fetch the model list for a vendor kind, off the UI thread."""

    def __init__(self, kind: str, base_url: str, api_key: str, timeout: float) -> None:
        super().__init__()
        self.kind = kind
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout
        self.signals = ProbeSignals()

    def run(self) -> None:
        try:
            if self.kind == llm_vendors.KIND_OLLAMA:
                names = llm_ollama.fetch_models(self.base_url, self.timeout)
            else:
                names = llm_openai_compat.fetch_models(self.base_url, self.api_key, self.timeout)
        except Exception as exc:  # noqa: BLE001 - surfaced verbatim
            self.signals.error.emit(str(exc))
        else:
            self.signals.models.emit(names)


class TestWorker(QtCore.QRunnable):
    """Send one short chat request and time it, off the UI thread."""

    def __init__(self, kind: str, base_url: str, api_key: str, model: str, timeout: float) -> None:
        super().__init__()
        self.kind = kind
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.signals = ProbeSignals()

    def run(self) -> None:
        if self.kind == llm_vendors.KIND_OLLAMA:
            backend = llm_ollama.OllamaBackend(url=self.base_url, model=self.model, timeout=self.timeout)
        else:
            backend = llm_openai_compat.OpenAICompatBackend(
                base_url=self.base_url, api_key=self.api_key, model=self.model, timeout=self.timeout
            )
        start = time.monotonic()
        try:
            reply = backend.reply(
                "Reply with exactly: OK",
                "You are a connectivity test. Reply with exactly: OK and nothing else.",
            )
        except Exception as exc:  # noqa: BLE001 - surfaced verbatim
            self.signals.error.emit(str(exc))
        else:
            self.signals.tested.emit(time.monotonic() - start, reply)


class LLMSettingsDialog(QtWidgets.QDialog):
    """Choose and configure the chat vendor."""

    def __init__(self, window: QtWidgets.QWidget, parent=None) -> None:
        super().__init__(parent)
        self.host_window = window
        self.setWindowTitle("Chat / LLM settings")
        self.setMinimumWidth(460)
        self.setStyleSheet(LIGHT_QSS)
        self.pool = QtCore.QThreadPool(self)
        llm_prompt.load_env_file()
        self.vendors = llm_vendors.load_vendors()
        self.current_api_key_env = ""

        self.enabled_box = QtWidgets.QCheckBox("LLM enabled")
        self.enabled_box.setChecked(self.current_enabled())

        self.vendor_combo = QtWidgets.QComboBox()
        self.name_edit = QtWidgets.QLineEdit()
        self.kind_combo = QtWidgets.QComboBox()
        self.kind_combo.addItem("Ollama (local)", llm_vendors.KIND_OLLAMA)
        self.kind_combo.addItem("OpenAI-compatible", llm_vendors.KIND_OPENAI)
        self.base_url_edit = QtWidgets.QLineEdit()
        self.key_edit = QtWidgets.QLineEdit()
        self.key_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.key_label = QtWidgets.QLabel("API key")
        self.model_combo = QtWidgets.QComboBox()
        self.model_combo.setEditable(True)
        self.load_btn = QtWidgets.QPushButton("Load models")
        self.load_btn.setAutoDefault(False)
        self.status_label = QtWidgets.QLabel("")
        self.status_label.setWordWrap(True)
        self.test_btn = QtWidgets.QPushButton("Test")
        self.save_btn = QtWidgets.QPushButton("Save")
        close_btn = QtWidgets.QPushButton("Close")

        form = QtWidgets.QFormLayout()
        form.addRow(self.enabled_box)
        form.addRow("Vendor", self.vendor_combo)
        form.addRow("Name", self.name_edit)
        form.addRow("Type", self.kind_combo)
        form.addRow("Base URL", self.base_url_edit)
        form.addRow(self.key_label, self.key_edit)
        model_row = QtWidgets.QHBoxLayout()
        model_row.addWidget(self.model_combo, 1)
        model_row.addWidget(self.load_btn)
        form.addRow("Model", model_row)

        # Test (left) · Save, Close (right) — same order in every dialog.
        buttons = QtWidgets.QHBoxLayout()
        buttons.addWidget(self.test_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.save_btn)
        buttons.addWidget(close_btn)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.status_label)
        layout.addLayout(buttons)

        # Populate the vendor dropdown: presets/custom first, then "Add custom…".
        for name, vendor in self.vendors.items():
            self.vendor_combo.addItem(vendor.label or name, name)
        self.vendor_combo.addItem(ADD_CUSTOM, None)

        self.vendor_combo.currentIndexChanged.connect(self.on_vendor_changed)
        self.kind_combo.currentIndexChanged.connect(self.refresh_key_visibility)
        self.load_btn.clicked.connect(self.on_load)
        self.model_combo.currentTextChanged.connect(self.on_model_changed)
        self.test_btn.clicked.connect(self.on_test)
        self.save_btn.clicked.connect(self.on_save)
        close_btn.clicked.connect(self.reject)

        # Select the active vendor and prime its fields.
        active = llm_vendors.active_vendor_name()
        idx = self.vendor_combo.findData(active)
        self.vendor_combo.setCurrentIndex(max(0, idx))
        self.on_vendor_changed()

    # -- state --------------------------------------------------------------

    def controller(self):
        return getattr(self.host_window, "_llm_controller", None)

    def current_enabled(self) -> bool:
        controller = self.controller()
        if controller is not None:
            return bool(controller.is_enabled())
        return llm_prompt.load_llm_enabled()

    def request_timeout(self) -> float:
        return float(llm_prompt.load_llm_settings().ollama_timeout) or TEST_TIMEOUT

    def is_custom_mode(self) -> bool:
        return self.vendor_combo.currentData() is None

    def kind_value(self) -> str:
        return self.kind_combo.currentData()

    def effective_key(self) -> str:
        typed = self.key_edit.text().strip()
        if typed:
            return typed
        return os.getenv(self.current_api_key_env, "") if self.current_api_key_env else ""

    def set_status(self, text: str, style: str = STATUS_INFO) -> None:
        self.status_label.setStyleSheet(style)
        self.status_label.setText(text)

    # -- vendor selection ---------------------------------------------------

    def on_vendor_changed(self, *args) -> None:
        custom = self.is_custom_mode()
        if custom:
            self.name_edit.setReadOnly(False)
            self.name_edit.setText("")
            self.name_edit.setPlaceholderText("my-vendor")
            self.kind_combo.setEnabled(True)
            self.kind_combo.setCurrentIndex(self.kind_combo.findData(llm_vendors.KIND_OPENAI))
            self.base_url_edit.setText("")
            self.base_url_edit.setPlaceholderText("https://api.example.com/v1")
            self.key_edit.setText("")
            self.key_edit.setPlaceholderText("API key")
            self.current_api_key_env = ""
        else:
            vendor = self.vendors[self.vendor_combo.currentData()]
            self.name_edit.setReadOnly(True)
            self.name_edit.setText(vendor.name)
            self.kind_combo.setEnabled(False)
            self.kind_combo.setCurrentIndex(max(0, self.kind_combo.findData(vendor.kind)))
            self.base_url_edit.setText(vendor.base_url)
            self.current_api_key_env = vendor.api_key_env
            self.key_edit.setText(vendor.api_key)
            self.key_edit.setPlaceholderText(
                f"leave empty to use ${vendor.api_key_env}" if vendor.api_key_env else "API key"
            )
        # Drop the previous vendor's model list so stale entries (e.g. Ollama
        # models) don't linger if the new vendor's load fails or hasn't run yet.
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        if not custom and vendor.model:
            self.model_combo.setCurrentText(vendor.model)
        self.model_combo.blockSignals(False)
        self.refresh_key_visibility()
        self.on_model_changed()
        # Auto-load models when the endpoint is reachable without typing a key.
        if not custom:
            QtCore.QTimer.singleShot(0, self.on_load)

    def refresh_key_visibility(self, *args) -> None:
        show_key = self.kind_value() == llm_vendors.KIND_OPENAI
        self.key_label.setVisible(show_key)
        self.key_edit.setVisible(show_key)

    # -- load models --------------------------------------------------------

    def on_load(self) -> None:
        base_url = self.base_url_edit.text().strip()
        if not base_url:
            self.set_status("Enter a base URL first.", STATUS_ERR)
            return
        self.load_btn.setEnabled(False)
        self.set_status("Loading models…", STATUS_INFO)
        worker = ModelsWorker(self.kind_value(), base_url, self.effective_key(), 10.0)
        worker.signals.models.connect(self.on_models)
        worker.signals.error.connect(self.on_load_error)
        self.pool.start(worker)

    def on_models(self, names: list) -> None:
        self.load_btn.setEnabled(True)
        keep = self.model_combo.currentText()
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        self.model_combo.addItems(names)
        # Long model ids get truncated in the narrow combo — show the full name
        # as a tooltip on each dropdown entry.
        for i in range(self.model_combo.count()):
            self.model_combo.setItemData(i, names[i], QtCore.Qt.ItemDataRole.ToolTipRole)
        if keep:
            self.model_combo.setCurrentText(keep)
        self.model_combo.blockSignals(False)
        self.set_status(f"Found {len(names)} model(s).", STATUS_OK)
        self.on_model_changed()

    def on_load_error(self, message: str) -> None:
        self.load_btn.setEnabled(True)
        self.set_status(f"Could not load models: {message}", STATUS_ERR)

    # -- model / actions ----------------------------------------------------

    def on_model_changed(self, *args) -> None:
        text = self.model_combo.currentText().strip()
        # Tooltip on the collapsed combo too, so the full selected name shows.
        self.model_combo.setToolTip(text)
        has_model = bool(text)
        self.test_btn.setEnabled(has_model)
        self.save_btn.setEnabled(has_model)

    def on_test(self) -> None:
        model = self.model_combo.currentText().strip()
        if not model:
            return
        self.test_btn.setEnabled(False)
        self.set_status(f"Testing {model}…", STATUS_INFO)
        worker = TestWorker(
            self.kind_value(),
            self.base_url_edit.text().strip(),
            self.effective_key(),
            model,
            self.request_timeout(),
        )
        worker.signals.tested.connect(self.on_tested)
        worker.signals.error.connect(self.on_test_error)
        self.pool.start(worker)

    def on_tested(self, elapsed: float, reply: str) -> None:
        self.test_btn.setEnabled(True)
        short = reply.strip().replace("\n", " ")
        if len(short) > 40:
            short = short[:40] + "…"
        self.set_status(f"OK — {elapsed:.2f} s (reply: {short})", STATUS_OK)

    def on_test_error(self, message: str) -> None:
        self.test_btn.setEnabled(True)
        self.set_status(f"Test failed: {message}", STATUS_ERR)

    # -- save ---------------------------------------------------------------

    def build_vendor(self) -> llm_vendors.Vendor | None:
        name = self.name_edit.text().strip()
        if not name:
            self.set_status("Enter a vendor name.", STATUS_ERR)
            return None
        base = self.vendors.get(name)
        return llm_vendors.Vendor(
            name=name,
            kind=self.kind_value(),
            base_url=self.base_url_edit.text().strip(),
            label=base.label if base else name,
            api_key=self.key_edit.text().strip(),
            api_key_env=self.current_api_key_env,
            model=self.model_combo.currentText().strip(),
        )

    def on_save(self) -> None:
        vendor = self.build_vendor()
        if vendor is None:
            return
        if not vendor.model:
            self.set_status("Pick a model first.", STATUS_ERR)
            return
        enabled = self.enabled_box.isChecked()
        try:
            llm_vendors.save_vendor(vendor, make_active=True)
            llm_prompt.save_llm_enabled(enabled)
        except OSError as exc:
            self.set_status(f"Could not save: {exc}", STATUS_ERR)
            return
        try:
            self.apply_live(vendor, enabled)
        except Exception as exc:  # noqa: BLE001 - config is saved regardless
            logger.exception("Failed to apply LLM settings live")
            self.set_status(f"Saved, but live apply failed: {exc}", STATUS_ERR)
            return
        state = "on" if enabled else "off"
        self.set_status(f"Saved ✓ ({state}): {vendor.name} · {vendor.model}", STATUS_OK)

    def apply_live(self, vendor: llm_vendors.Vendor, enabled: bool) -> None:
        from . import llm, llm_ui

        timeout = self.request_timeout()
        backend = llm.create_backend_for_vendor(vendor, timeout)
        controller = self.controller()
        if controller is not None:
            controller.context.backend = backend
            controller.context.backend_name = vendor.name
            controller.context.vendor = vendor
            controller.context.enabled = enabled
            controller.set_enabled(enabled)
            # Update an already-open chat window so it uses the new backend.
            chat = getattr(controller, "chat_dialog", None)
            if chat is not None and hasattr(chat, "backend"):
                chat.backend = backend
            return

        context = llm.LLMContext(
            backend_name=vendor.name,
            backend=backend,
            settings=llm_prompt.load_llm_settings(),
            enabled=enabled,
            vendor=vendor,
        )
        llm_ui.attach_chat(self.host_window, context, enabled=enabled)


# Backwards-compatible alias (the old dialog name).
OllamaSettingsDialog = LLMSettingsDialog

__all__ = ["LLMSettingsDialog", "OllamaSettingsDialog"]
