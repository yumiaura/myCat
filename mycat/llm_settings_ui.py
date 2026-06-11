"""Ollama settings dialog: pick host/port, fetch and select a model, test, save."""

from __future__ import annotations

import logging
import time
from urllib.parse import urlsplit

from PySide6 import QtCore, QtWidgets

from . import llm_ollama, llm_prompt

logger = logging.getLogger(__name__)

# Same light theme as the reminder dialog so the window is readable under a dark
# desktop theme (otherwise dark text on a dark system background is invisible).
LIGHT_QSS = (
    "QDialog { background: #ffffff; color: #1c1c1c; }"
    "QLabel, QCheckBox { color: #1c1c1c; background: transparent; }"
    "QLineEdit, QSpinBox, QComboBox {"
    " color: #1c1c1c; background: #ffffff;"
    " border: 1px solid #c0c0c0; border-radius: 4px; padding: 3px 5px;"
    " selection-color: white; selection-background-color: #ff6f91; }"
    "QComboBox QAbstractItemView {"
    " color: #1c1c1c; background: #ffffff;"
    " selection-color: white; selection-background-color: #ff6f91; }"
    "QPushButton {"
    " color: #1c1c1c; background: #f0f0f0;"
    " border: 1px solid #c0c0c0; border-radius: 4px; padding: 5px 14px; }"
    "QPushButton:hover { background: #e7e7e7; }"
    "QPushButton:disabled { color: #9a9a9a; background: #f5f5f5; }"
)

STATUS_OK = "color: #1c7c2f;"
STATUS_ERR = "color: #c0392b;"
STATUS_INFO = "color: #555555;"

TEST_TIMEOUT = 30.0


class ProbeSignals(QtCore.QObject):
    """Signals emitted by the background network workers."""

    models = QtCore.Signal(list)
    tested = QtCore.Signal(float, str)  # elapsed seconds, reply text
    error = QtCore.Signal(str)


class ModelsWorker(QtCore.QRunnable):
    """GET /api/tags off the UI thread."""

    def __init__(self, base_url: str, timeout: float) -> None:
        super().__init__()
        self.base_url = base_url
        self.timeout = timeout
        self.signals = ProbeSignals()

    def run(self) -> None:
        try:
            names = llm_ollama.fetch_models(self.base_url, self.timeout)
        except Exception as exc:  # noqa: BLE001 - surfaced to the user verbatim
            self.signals.error.emit(str(exc))
        else:
            self.signals.models.emit(names)


class TestWorker(QtCore.QRunnable):
    """Send one short chat request and time it, off the UI thread."""

    def __init__(self, base_url: str, model: str, timeout: float) -> None:
        super().__init__()
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        self.signals = ProbeSignals()

    def run(self) -> None:
        backend = llm_ollama.OllamaBackend(url=self.base_url, model=self.model, timeout=self.timeout)
        start = time.monotonic()
        try:
            reply = backend.reply(
                "Reply with exactly: OK",
                "You are a connectivity test. Reply with exactly: OK and nothing else.",
            )
        except Exception as exc:  # noqa: BLE001 - surfaced to the user verbatim
            self.signals.error.emit(str(exc))
        else:
            self.signals.tested.emit(time.monotonic() - start, reply)


class OllamaSettingsDialog(QtWidgets.QDialog):
    """Configure the Ollama backend: host/port, model, a connectivity test, save."""

    def __init__(self, window: QtWidgets.QWidget, parent=None) -> None:
        super().__init__(parent)
        self.host_window = window
        self.setWindowTitle("Ollama settings")
        self.setMinimumWidth(440)
        self.setStyleSheet(LIGHT_QSS)
        self.pool = QtCore.QThreadPool(self)
        self.models: list = []

        url, model = self.current_url_model()
        host, port = self.split_url(url)
        self.saved_model = model

        self.enabled_box = QtWidgets.QCheckBox("LLM enabled")
        self.enabled_box.setChecked(self.current_enabled())

        self.host_edit = QtWidgets.QLineEdit(host)
        self.port_spin = QtWidgets.QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(port)
        self.load_btn = QtWidgets.QPushButton("Load models")
        self.model_combo = QtWidgets.QComboBox()
        self.model_combo.setEnabled(False)
        self.status_label = QtWidgets.QLabel("")
        self.status_label.setWordWrap(True)
        self.test_btn = QtWidgets.QPushButton("Test")
        self.save_btn = QtWidgets.QPushButton("Save")
        self.test_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        cancel_btn = QtWidgets.QPushButton("Cancel")

        form = QtWidgets.QFormLayout()
        form.addRow(self.enabled_box)
        form.addRow("Host", self.host_edit)
        # Port and the load button share a row. The row is added as a bare layout
        # (not wrapped in a QWidget) so the button keeps the dialog's button style
        # instead of sitting on a stray system-coloured panel.
        port_row = QtWidgets.QHBoxLayout()
        port_row.addWidget(self.port_spin)
        port_row.addStretch(1)
        port_row.addWidget(self.load_btn)
        # Don't let the load button grab the dialog default (it would highlight).
        self.load_btn.setAutoDefault(False)
        self.load_btn.setDefault(False)
        form.addRow("Port", port_row)
        form.addRow("Model", self.model_combo)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addWidget(self.test_btn)
        buttons.addStretch(1)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(self.save_btn)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.status_label)
        layout.addLayout(buttons)

        self.load_btn.clicked.connect(self.on_load)
        self.model_combo.currentIndexChanged.connect(self.on_model_changed)
        self.test_btn.clicked.connect(self.on_test)
        self.save_btn.clicked.connect(self.on_save)
        cancel_btn.clicked.connect(self.reject)
        # Reset model list if the user edits the endpoint after a load.
        self.host_edit.textEdited.connect(self.invalidate_models)
        self.port_spin.valueChanged.connect(self.invalidate_models)

        # Fetch the model list immediately so the user lands on a ready selector.
        QtCore.QTimer.singleShot(0, self.on_load)

    # -- helpers ------------------------------------------------------------

    def controller(self):
        return getattr(self.host_window, "_llm_controller", None)

    def current_url_model(self):
        controller = self.controller()
        if controller is not None:
            settings = controller.context.settings
            return settings.ollama_url, settings.ollama_model
        llm_prompt.load_env_file()
        settings = llm_prompt.load_llm_settings()
        return settings.ollama_url, settings.ollama_model

    def current_enabled(self) -> bool:
        controller = self.controller()
        if controller is not None:
            return bool(controller.is_enabled())
        return True

    def current_timeout(self) -> float:
        controller = self.controller()
        if controller is not None:
            return float(controller.context.settings.ollama_timeout)
        return float(llm_prompt.load_llm_settings().ollama_timeout)

    def split_url(self, url: str):
        parts = urlsplit(url if "//" in url else f"http://{url}")
        return (parts.hostname or "localhost"), (parts.port or 11434)

    def base_url(self) -> str:
        return f"http://{self.host_edit.text().strip() or 'localhost'}:{self.port_spin.value()}"

    def set_status(self, text: str, style: str = STATUS_INFO) -> None:
        self.status_label.setStyleSheet(style)
        self.status_label.setText(text)

    def invalidate_models(self, *args) -> None:
        self.models = []
        self.model_combo.clear()
        self.model_combo.setEnabled(False)
        self.test_btn.setEnabled(False)
        self.save_btn.setEnabled(False)

    # -- load models --------------------------------------------------------

    def on_load(self) -> None:
        self.load_btn.setEnabled(False)
        self.set_status("Loading models…", STATUS_INFO)
        worker = ModelsWorker(self.base_url(), 10.0)
        worker.signals.models.connect(self.on_models)
        worker.signals.error.connect(self.on_load_error)
        self.pool.start(worker)

    def on_models(self, names: list) -> None:
        self.load_btn.setEnabled(True)
        self.models = names
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        self.model_combo.addItems(names)
        self.model_combo.setEnabled(True)
        if self.saved_model in names:
            self.model_combo.setCurrentText(self.saved_model)
        self.model_combo.blockSignals(False)
        self.set_status(f"Found {len(names)} model(s).", STATUS_OK)
        self.on_model_changed()

    def on_load_error(self, message: str) -> None:
        self.load_btn.setEnabled(True)
        self.invalidate_models()
        self.set_status(f"Could not load models: {message}", STATUS_ERR)

    # -- model selection ----------------------------------------------------

    def on_model_changed(self, *args) -> None:
        has_model = self.model_combo.isEnabled() and bool(self.model_combo.currentText())
        self.test_btn.setEnabled(has_model)
        self.save_btn.setEnabled(has_model)

    # -- test ---------------------------------------------------------------

    def on_test(self) -> None:
        model = self.model_combo.currentText()
        if not model:
            return
        self.test_btn.setEnabled(False)
        self.set_status(f"Testing {model}…", STATUS_INFO)
        worker = TestWorker(self.base_url(), model, self.current_timeout() or TEST_TIMEOUT)
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

    def on_save(self) -> None:
        model = self.model_combo.currentText()
        if not model:
            return
        endpoint = self.base_url()
        enabled = self.enabled_box.isChecked()
        try:
            llm_prompt.save_ollama_settings(endpoint, model)
            llm_prompt.save_llm_enabled(enabled)
        except OSError as exc:
            self.set_status(f"Could not save: {exc}", STATUS_ERR)
            return
        try:
            self.apply_live(endpoint, model, enabled)
        except Exception as exc:  # noqa: BLE001 - report but the config is saved
            logger.exception("Failed to apply Ollama settings live")
            self.set_status(f"Saved to config, but live apply failed: {exc}", STATUS_ERR)
            return
        self.set_status("Saved ✓", STATUS_OK)
        self.accept()

    def apply_live(self, endpoint: str, model: str, enabled: bool) -> None:
        controller = self.controller()
        if controller is not None and controller.context.backend_name == "ollama":
            backend = controller.context.backend
            if hasattr(backend, "chat_url"):
                backend.chat_url = f"{endpoint.rstrip('/')}/api/chat"
            if hasattr(backend, "model"):
                backend.model = model
            controller.context.settings.ollama_url = endpoint
            controller.context.settings.ollama_model = model
            controller.context.enabled = enabled
            controller.set_enabled(enabled)
            return

        # No Ollama controller yet (LLM was off, or a different backend) — build
        # one now so the Chat item appears without a restart.
        from . import llm, llm_ui

        settings = llm_prompt.load_llm_settings()
        settings.ollama_url = endpoint
        settings.ollama_model = model
        backend = llm.create_backend("ollama", settings)
        context = llm.LLMContext(
            backend_name="ollama", backend=backend, settings=settings, enabled=enabled
        )
        llm_ui.attach_chat(self.host_window, context, enabled=enabled)


__all__ = ["OllamaSettingsDialog"]
