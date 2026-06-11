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

        url, model = self._current_url_model()
        host, port = self._split_url(url)
        self._saved_model = model

        self._enabled = QtWidgets.QCheckBox("LLM enabled")
        self._enabled.setChecked(self._current_enabled())

        self._host = QtWidgets.QLineEdit(host)
        self._port = QtWidgets.QSpinBox()
        self._port.setRange(1, 65535)
        self._port.setValue(port)
        self._load_btn = QtWidgets.QPushButton("Load models")
        self._model = QtWidgets.QComboBox()
        self._model.setEnabled(False)
        self._status = QtWidgets.QLabel("")
        self._status.setWordWrap(True)
        self._test_btn = QtWidgets.QPushButton("Test")
        self._save_btn = QtWidgets.QPushButton("Save")
        self._test_btn.setEnabled(False)
        self._save_btn.setEnabled(False)
        cancel_btn = QtWidgets.QPushButton("Cancel")

        form = QtWidgets.QFormLayout()
        form.addRow(self._enabled)
        form.addRow("Host", self._host)
        # Port and the load button share a row. The row is added as a bare layout
        # (not wrapped in a QWidget) so the button keeps the dialog's button style
        # instead of sitting on a stray system-coloured panel.
        port_row = QtWidgets.QHBoxLayout()
        port_row.addWidget(self._port)
        port_row.addStretch(1)
        port_row.addWidget(self._load_btn)
        # Don't let the load button grab the dialog default (it would highlight).
        self._load_btn.setAutoDefault(False)
        self._load_btn.setDefault(False)
        form.addRow("Port", port_row)
        form.addRow("Model", self._model)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addWidget(self._test_btn)
        buttons.addStretch(1)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(self._save_btn)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._status)
        layout.addLayout(buttons)

        self._load_btn.clicked.connect(self._on_load)
        self._model.currentIndexChanged.connect(self._on_model_changed)
        self._test_btn.clicked.connect(self._on_test)
        self._save_btn.clicked.connect(self._on_save)
        cancel_btn.clicked.connect(self.reject)
        # Reset model list if the user edits the endpoint after a load.
        self._host.textEdited.connect(self._invalidate_models)
        self._port.valueChanged.connect(self._invalidate_models)

        # Fetch the model list immediately so the user lands on a ready selector.
        QtCore.QTimer.singleShot(0, self._on_load)

    # -- helpers ------------------------------------------------------------

    def _controller(self):
        return getattr(self.host_window, "_llm_controller", None)

    def _current_url_model(self):
        controller = self._controller()
        if controller is not None:
            settings = controller.context.settings
            return settings.ollama_url, settings.ollama_model
        llm_prompt.load_env_file()
        settings = llm_prompt.load_llm_settings()
        return settings.ollama_url, settings.ollama_model

    def _current_enabled(self) -> bool:
        controller = self._controller()
        if controller is not None:
            return bool(controller.is_enabled())
        return True

    def _current_timeout(self) -> float:
        controller = self._controller()
        if controller is not None:
            return float(controller.context.settings.ollama_timeout)
        return float(llm_prompt.load_llm_settings().ollama_timeout)

    def _split_url(self, url: str):
        parts = urlsplit(url if "//" in url else f"http://{url}")
        return (parts.hostname or "localhost"), (parts.port or 11434)

    def _base_url(self) -> str:
        return f"http://{self._host.text().strip() or 'localhost'}:{self._port.value()}"

    def _set_status(self, text: str, style: str = STATUS_INFO) -> None:
        self._status.setStyleSheet(style)
        self._status.setText(text)

    def _invalidate_models(self, *_args) -> None:
        self.models = []
        self._model.clear()
        self._model.setEnabled(False)
        self._test_btn.setEnabled(False)
        self._save_btn.setEnabled(False)

    # -- load models --------------------------------------------------------

    def _on_load(self) -> None:
        self._load_btn.setEnabled(False)
        self._set_status("Loading models…", STATUS_INFO)
        worker = ModelsWorker(self._base_url(), 10.0)
        worker.signals.models.connect(self._on_models)
        worker.signals.error.connect(self._on_load_error)
        self.pool.start(worker)

    def _on_models(self, names: list) -> None:
        self._load_btn.setEnabled(True)
        self.models = names
        self._model.blockSignals(True)
        self._model.clear()
        self._model.addItems(names)
        self._model.setEnabled(True)
        if self._saved_model in names:
            self._model.setCurrentText(self._saved_model)
        self._model.blockSignals(False)
        self._set_status(f"Found {len(names)} model(s).", STATUS_OK)
        self._on_model_changed()

    def _on_load_error(self, message: str) -> None:
        self._load_btn.setEnabled(True)
        self._invalidate_models()
        self._set_status(f"Could not load models: {message}", STATUS_ERR)

    # -- model selection ----------------------------------------------------

    def _on_model_changed(self, *_args) -> None:
        has_model = self._model.isEnabled() and bool(self._model.currentText())
        self._test_btn.setEnabled(has_model)
        self._save_btn.setEnabled(has_model)

    # -- test ---------------------------------------------------------------

    def _on_test(self) -> None:
        model = self._model.currentText()
        if not model:
            return
        self._test_btn.setEnabled(False)
        self._set_status(f"Testing {model}…", STATUS_INFO)
        worker = TestWorker(self._base_url(), model, self._current_timeout() or TEST_TIMEOUT)
        worker.signals.tested.connect(self._on_tested)
        worker.signals.error.connect(self._on_test_error)
        self.pool.start(worker)

    def _on_tested(self, elapsed: float, reply: str) -> None:
        self._test_btn.setEnabled(True)
        short = reply.strip().replace("\n", " ")
        if len(short) > 40:
            short = short[:40] + "…"
        self._set_status(f"OK — {elapsed:.2f} s (reply: {short})", STATUS_OK)

    def _on_test_error(self, message: str) -> None:
        self._test_btn.setEnabled(True)
        self._set_status(f"Test failed: {message}", STATUS_ERR)

    # -- save ---------------------------------------------------------------

    def _on_save(self) -> None:
        model = self._model.currentText()
        if not model:
            return
        base_url = self._base_url()
        enabled = self._enabled.isChecked()
        try:
            llm_prompt.save_ollama_settings(base_url, model)
            llm_prompt.save_llm_enabled(enabled)
        except OSError as exc:
            self._set_status(f"Could not save: {exc}", STATUS_ERR)
            return
        try:
            self._apply_live(base_url, model, enabled)
        except Exception as exc:  # noqa: BLE001 - report but the config is saved
            logger.exception("Failed to apply Ollama settings live")
            self._set_status(f"Saved to config, but live apply failed: {exc}", STATUS_ERR)
            return
        self._set_status("Saved ✓", STATUS_OK)
        self.accept()

    def _apply_live(self, base_url: str, model: str, enabled: bool) -> None:
        controller = self._controller()
        if controller is not None and controller.context.backend_name == "ollama":
            backend = controller.context.backend
            if hasattr(backend, "chat_url"):
                backend.chat_url = f"{base_url.rstrip('/')}/api/chat"
            if hasattr(backend, "model"):
                backend.model = model
            controller.context.settings.ollama_url = base_url
            controller.context.settings.ollama_model = model
            controller.context.enabled = enabled
            controller.set_enabled(enabled)
            return

        # No Ollama controller yet (LLM was off, or a different backend) — build
        # one now so the Chat item appears without a restart.
        from . import llm, llm_ui

        settings = llm_prompt.load_llm_settings()
        settings.ollama_url = base_url
        settings.ollama_model = model
        backend = llm.create_backend("ollama", settings)
        context = llm.LLMContext(
            backend_name="ollama", backend=backend, settings=settings, enabled=enabled
        )
        llm_ui.attach_chat(self.host_window, context, enabled=enabled)


__all__ = ["OllamaSettingsDialog"]
