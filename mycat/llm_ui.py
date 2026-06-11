"""Chat UI layer for PixelCat."""

from __future__ import annotations

import base64
import logging
import os
import re
import threading
import time
from datetime import datetime
from typing import List, Optional, TYPE_CHECKING

from PySide6 import QtCore, QtGui, QtWidgets

from . import llm_prompt, personas, voice

if TYPE_CHECKING:
    from .llm import LLMContext

logger = logging.getLogger(__name__)

# --- styling -----------------------------------------------------------------
ICON_BTN_STYLE = """
    QPushButton {
        background-color: #f0f0f3;
        border: none;
        border-radius: 10px;
        font-size: 15px;
    }
    QPushButton:hover { background-color: #e2e2e8; }
    QPushButton:pressed { background-color: #d4d4dc; }
    QPushButton:disabled { color: #b8b8b8; background-color: #f4f4f6; }
"""
SEND_BTN_STYLE = """
    QPushButton {
        background-color: #4a90d9;
        color: white;
        border: none;
        border-radius: 10px;
        font-size: 13px;
        font-weight: bold;
        padding: 0 12px;
    }
    QPushButton:hover { background-color: #3f7fc2; }
    QPushButton:pressed { background-color: #356da8; }
"""
STOP_BTN_STYLE = """
    QPushButton {
        background-color: #e05c5c;
        color: white;
        border: none;
        border-radius: 10px;
        font-size: 15px;
        font-weight: bold;
        padding: 0 12px;
    }
    QPushButton:hover { background-color: #cf4d4d; }
"""
INPUT_STYLE = """
    QLineEdit {
        background-color: white;
        border: 1px solid #d4d4da;
        border-radius: 10px;
        padding-left: 12px;
        padding-right: 12px;
        font-size: 13px;
    }
    QLineEdit:focus { border-color: #4a90d9; }
    QLineEdit:disabled { background-color: #f4f4f6; color: #888; }
"""
PANEL_STYLE = """
    QFrame#settingsPanel {
        background-color: #f7f7fa;
        border: 1px solid #e4e4ea;
        border-radius: 10px;
    }
    QLabel { color: #555; font-size: 12px; }
    QPushButton.flat {
        background-color: #ffffff;
        border: 1px solid #d4d4da;
        border-radius: 8px;
        padding: 4px 8px;
        font-size: 12px;
        color: #333;
    }
    QPushButton.flat:hover { background-color: #eef0f5; }
"""

_ASTERISK_RE = re.compile(r"\*+")
_MULTISPACE_RE = re.compile(r"[ \t]{2,}")


def _strip_markup(text: str) -> str:
    """Remove asterisks (markdown emphasis and *action* descriptions)."""
    text = _ASTERISK_RE.sub("", text)
    return _MULTISPACE_RE.sub(" ", text)


def _pretty_voice_name(name: str) -> str:
    """'en_US-amy-medium' -> 'Amy (US, medium)'."""
    try:
        locale, voice_name, quality = name.split("-", 2)
        region = locale.split("_")[-1]
        label = voice_name.replace("_", " ").title()
        return f"{label} ({region}, {quality})"
    except ValueError:
        return name


def attach_chat(window: QtWidgets.QWidget, context: "LLMContext", enabled: bool = True) -> None:
    controller = _LLMController(window, context, enabled=enabled)
    setattr(window, "_llm_controller", controller)
    setattr(window, "_toggle_llm_chat", controller.toggle_chat)
    setattr(window, "_toggle_llm_enabled", controller.toggle_enabled)
    setattr(window, "_is_llm_enabled", controller.is_enabled)
    logger.debug("Chat controller attached to window %s", window)


class _LLMController(QtCore.QObject):
    """Owns the chat dialog lifecycle and keeps it anchored to the cat window."""

    def __init__(self, window: QtWidgets.QWidget, context: "LLMContext", enabled: bool = True) -> None:
        super().__init__(window)
        self.window = window
        self.context = context
        self.enabled = enabled
        self.chat_dialog: Optional[ChatDialog] = None
        self.history_file = llm_prompt.ensure_history_file()

        window.installEventFilter(self)
        window.destroyed.connect(self._on_window_destroyed)
        logger.debug("LLM controller initialised with history file %s", self.history_file)

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if watched is self.window and event.type() in (
            QtCore.QEvent.Type.Move,
            QtCore.QEvent.Type.Resize,
        ):
            self._position_dialog()
        return super().eventFilter(watched, event)

    def _toggle_chat(self) -> None:
        if not self.enabled:
            logger.debug("LLM chat is disabled, ignoring toggle")
            return
        if self.chat_dialog:
            if self.chat_dialog.isVisible():
                self.chat_dialog.hide()
                return
            self.chat_dialog.show()
            self._position_dialog()
            self.chat_dialog.raise_()
            self.chat_dialog.activateWindow()
            return

        dialog = ChatDialog(self)
        dialog.show()
        dialog.destroyed.connect(self._on_chat_destroyed)
        self.chat_dialog = dialog
        self._position_dialog()

    def toggle_chat(self) -> None:
        """Public hook for opening chat from host UI."""
        self._toggle_chat()

    def refresh_persona(self) -> None:
        """Update the open chat dialog after the personality changed."""
        if self.chat_dialog:
            self.chat_dialog.refresh_persona()

    def is_enabled(self) -> bool:
        return self.enabled

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if not enabled and self.chat_dialog and self.chat_dialog.isVisible():
            self.chat_dialog.hide()

    def toggle_enabled(self) -> bool:
        self.set_enabled(not self.enabled)
        logger.info("LLM chat %s", "enabled" if self.enabled else "disabled")
        return self.enabled

    def _position_dialog(self) -> None:
        if not self.chat_dialog:
            return
        screen_rect = QtGui.QGuiApplication.primaryScreen().availableGeometry()
        cat_rect = self.window.geometry()
        dialog = self.chat_dialog

        dialog_width = dialog.width()
        dialog_height = dialog.height()

        x = cat_rect.right() - dialog_width
        y = cat_rect.top() - dialog_height - 10

        if y < 0:
            y = cat_rect.bottom() + 10
        if x < 10:
            x = 10
        if x + dialog_width > screen_rect.width():
            x = screen_rect.width() - dialog_width - 10

        dialog._suspend_anchor = True  # type: ignore[attr-defined]
        dialog.move(x, y)
        dialog._suspend_anchor = False  # type: ignore[attr-defined]

    def _on_chat_destroyed(self, *_args) -> None:
        self.chat_dialog = None

    def _on_window_destroyed(self, *_args) -> None:
        self.chat_dialog = None


class ChatDialog(QtWidgets.QDialog):
    """Frameless chat dialog with streaming replies, voice, and image input."""

    def __init__(self, controller: _LLMController):
        super().__init__(controller.window)
        self.controller = controller
        self.backend = controller.context.backend
        self.settings = controller.context.settings
        self.history_file = controller.history_file
        self.message_count = 0
        self._thread_pool = QtCore.QThreadPool.globalInstance()
        self._suspend_anchor = False
        self._messages: List[tuple[str, str, str]] = []

        # Streaming / generation state.
        self._streaming = False
        self._stop_event: Optional[threading.Event] = None
        self._stream_raw = ""
        self._live_bubble: Optional[MessageBubble] = None
        self._req_started: Optional[float] = None
        self._req_text: Optional[str] = None

        # Image attachment for the next message.
        self._pending_image: Optional[str] = None

        # Voice chat (speech in / speech out), all local. Disabled if deps missing.
        self._recorder = voice.Recorder()
        self._voice_ok = voice.available()
        self._tts_enabled = self._voice_ok
        self._tts_volume = 0.8
        self._interim_running = False
        self._record_timer = QtCore.QTimer(self)
        self._record_timer.setInterval(1500)
        self._record_timer.timeout.connect(self._tick_interim)

        self.setWindowFlags(
            QtCore.Qt.WindowType.Window | QtCore.Qt.WindowType.WindowStaysOnTopHint
        )
        self.setWindowTitle(f"Chat with your {personas.label().lower()}")
        self.resize(380, 460)
        self.setMinimumSize(240, 200)
        self.setSizeGripEnabled(True)
        self.setModal(False)

        self._build_ui()
        self._load_history()
        if self._voice_ok:
            voice.prewarm()

    # --- UI construction -----------------------------------------------------
    def _build_ui(self) -> None:
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # Messages.
        self.scroll_area = QtWidgets.QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignBottom
        )
        main_layout.addWidget(self.scroll_area, 1)

        self.messages_widget = QtWidgets.QWidget()
        self.messages_layout = QtWidgets.QVBoxLayout(self.messages_widget)
        self.messages_layout.setContentsMargins(2, 2, 2, 2)
        self.messages_layout.setSpacing(6)
        self.messages_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignBottom)
        self.scroll_area.setWidget(self.messages_widget)
        self.scroll_area.verticalScrollBar().rangeChanged.connect(
            lambda *_: QtCore.QTimer.singleShot(0, self._scroll_to_bottom)
        )

        # Settings panel (hidden by default; toggled by the gear button).
        self.settings_panel = self._build_settings_panel()
        self.settings_panel.setVisible(False)
        main_layout.addWidget(self.settings_panel)

        # Attachment chip (hidden unless an image is attached).
        self.attach_row = QtWidgets.QWidget()
        attach_layout = QtWidgets.QHBoxLayout(self.attach_row)
        attach_layout.setContentsMargins(2, 0, 2, 0)
        attach_layout.setSpacing(4)
        self.attach_label = QtWidgets.QLabel()
        self.attach_label.setStyleSheet("color: #4a90d9; font-size: 12px;")
        attach_layout.addWidget(self.attach_label, 1)
        self.attach_remove = QtWidgets.QPushButton("✕")
        self.attach_remove.setFixedSize(20, 20)
        self.attach_remove.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.attach_remove.setStyleSheet(ICON_BTN_STYLE)
        self.attach_remove.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.attach_remove.clicked.connect(self._clear_attachment)
        attach_layout.addWidget(self.attach_remove)
        self.attach_row.setVisible(False)
        main_layout.addWidget(self.attach_row)

        # Input bar.
        input_layout = QtWidgets.QHBoxLayout()
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(4)

        self.gear_button = self._icon_button("⚙", "Settings (voice, volume, history)")
        self.gear_button.clicked.connect(self._toggle_settings)
        input_layout.addWidget(self.gear_button)

        self.attach_button = self._icon_button("📎", "Attach an image to send to the cat")
        self.attach_button.clicked.connect(self._attach_image)
        input_layout.addWidget(self.attach_button)

        self.mic_button = self._icon_button("🎤", "Talk to the cat: click to record, click again to send")
        self.mic_button.clicked.connect(self._toggle_record)
        self.mic_button.setEnabled(self._voice_ok)
        input_layout.addWidget(self.mic_button)

        self.input_field = QtWidgets.QLineEdit()
        self.input_field.setPlaceholderText("Write a message…")
        self.input_field.setMinimumHeight(36)
        self.input_field.setStyleSheet(INPUT_STYLE)
        self.input_field.returnPressed.connect(self._on_send_clicked)
        input_layout.addWidget(self.input_field, 1)

        self.send_button = QtWidgets.QPushButton("Send")
        self.send_button.setFixedHeight(36)
        self.send_button.setMinimumWidth(58)
        self.send_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.send_button.setStyleSheet(SEND_BTN_STYLE)
        # Not the dialog default button: otherwise Enter triggers BOTH returnPressed
        # and the default-button click, sending then immediately stopping.
        self.send_button.setDefault(False)
        self.send_button.setAutoDefault(False)
        self.send_button.clicked.connect(self._on_send_clicked)
        input_layout.addWidget(self.send_button)

        main_layout.addLayout(input_layout)

        # No button should auto-activate on Enter — Enter must only send via the
        # input field's returnPressed (otherwise Enter could fire Stop/Export/etc.).
        for button in self.findChildren(QtWidgets.QPushButton):
            button.setAutoDefault(False)
            button.setDefault(False)

        self._typing_indicator: Optional[TypingIndicator] = None

    def _icon_button(self, text: str, tooltip: str) -> QtWidgets.QPushButton:
        button = QtWidgets.QPushButton(text)
        button.setFixedSize(36, 36)
        button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(ICON_BTN_STYLE)
        button.setDefault(False)
        button.setAutoDefault(False)
        button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        button.setToolTip(tooltip)
        return button

    def _build_settings_panel(self) -> QtWidgets.QFrame:
        panel = QtWidgets.QFrame()
        panel.setObjectName("settingsPanel")
        panel.setStyleSheet(PANEL_STYLE)
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # Voice picker.
        voice_row = QtWidgets.QHBoxLayout()
        voice_row.setSpacing(6)
        voice_row.addWidget(QtWidgets.QLabel("Voice"))
        self.voice_combo = QtWidgets.QComboBox()
        self.voice_combo.setFixedHeight(24)
        self.voice_combo.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.voice_combo.setEnabled(self._voice_ok)
        if self._voice_ok:
            current_voice = voice.get_voice()
            for name, path in voice.list_voices():
                self.voice_combo.addItem(_pretty_voice_name(name), path)
                if path == current_voice:
                    self.voice_combo.setCurrentIndex(self.voice_combo.count() - 1)
        else:
            self.voice_combo.addItem("(voice unavailable)")
        self.voice_combo.currentIndexChanged.connect(self._on_voice_changed)
        voice_row.addWidget(self.voice_combo, 1)
        layout.addLayout(voice_row)

        # Volume.
        vol_row = QtWidgets.QHBoxLayout()
        vol_row.setSpacing(6)
        self.tts_toggle = QtWidgets.QPushButton("🔊" if self._tts_enabled else "🔇")
        self.tts_toggle.setFixedSize(28, 24)
        self.tts_toggle.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.tts_toggle.setStyleSheet(ICON_BTN_STYLE)
        self.tts_toggle.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.tts_toggle.setToolTip("Mute / unmute the cat's voice")
        self.tts_toggle.clicked.connect(self._toggle_tts)
        self.tts_toggle.setEnabled(self._voice_ok)
        vol_row.addWidget(self.tts_toggle)
        self.volume_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(int(self._tts_volume * 100))
        self.volume_slider.setFixedHeight(24)
        self.volume_slider.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.volume_slider.setToolTip("Cat voice volume")
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        self.volume_slider.setEnabled(self._voice_ok)
        vol_row.addWidget(self.volume_slider, 1)
        layout.addLayout(vol_row)

        # History export / import.
        hist_row = QtWidgets.QHBoxLayout()
        hist_row.setSpacing(6)
        self.export_button = QtWidgets.QPushButton("Export chat")
        self.export_button.setProperty("class", "flat")
        self.export_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.export_button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.export_button.clicked.connect(self._export_history)
        hist_row.addWidget(self.export_button)
        self.import_button = QtWidgets.QPushButton("Import chat")
        self.import_button.setProperty("class", "flat")
        self.import_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.import_button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.import_button.clicked.connect(self._import_history)
        hist_row.addWidget(self.import_button)
        layout.addLayout(hist_row)

        return panel

    def _toggle_settings(self) -> None:
        self.settings_panel.setVisible(not self.settings_panel.isVisible())

    def refresh_persona(self) -> None:
        """Reflect a personality change live: title, name labels, and voice."""
        self.setWindowTitle(f"Chat with your {personas.label().lower()}")
        # Sync the settings voice picker to the persona's preferred voice.
        if self._voice_ok:
            current = voice.get_voice()
            for i in range(self.voice_combo.count()):
                if self.voice_combo.itemData(i) == current:
                    self.voice_combo.blockSignals(True)
                    self.voice_combo.setCurrentIndex(i)
                    self.voice_combo.blockSignals(False)
                    break
        self._render_messages()

    # --- history -------------------------------------------------------------
    def _load_history(self) -> None:
        entries = llm_prompt.parse_history_file(self.history_file)
        self._messages = entries
        self.message_count = len(entries)
        self._render_messages()

    def _show_welcome_message(self) -> None:
        self._messages = []
        self._clear_message_widgets()
        label = QtWidgets.QLabel("Say something to your cat…")
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: #999; font-style: italic; margin-top: 40px;")
        self.messages_layout.addWidget(label)
        self.message_count = 0

    def _export_history(self) -> None:
        default_path = str(llm_prompt.CFG_DIR / "history-export.txt")
        target_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export History", default_path, "Text files (*.txt);;All files (*)"
        )
        if not target_path:
            return
        try:
            content = self.history_file.read_text(encoding="utf-8")
            with open(target_path, "w", encoding="utf-8") as handle:
                handle.write(content)
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, "Export failed", f"Could not export history:\n{exc}")
            return
        QtWidgets.QMessageBox.information(self, "Export complete", f"History saved to:\n{target_path}")

    def _import_history(self) -> None:
        source_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Import History", str(llm_prompt.CFG_DIR), "Text files (*.txt);;All files (*)"
        )
        if not source_path:
            return
        try:
            with open(source_path, "r", encoding="utf-8") as handle:
                content = handle.read()
            self.history_file.write_text(content, encoding="utf-8")
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, "Import failed", f"Could not import history:\n{exc}")
            return
        self._load_history()
        QtWidgets.QMessageBox.information(self, "Import complete", f"History loaded from:\n{source_path}")

    # --- window events -------------------------------------------------------
    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self.controller.window.isVisible():
            event.ignore()
            self.hide()
        else:
            super().closeEvent(event)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_bubble_widths()

    def moveEvent(self, event: QtGui.QMoveEvent) -> None:
        super().moveEvent(event)
        # The dialog is anchored to the cat once when it opens, then stays where
        # the user drags it (re-anchoring here would snap it back on every move).

    # --- sending / streaming -------------------------------------------------
    def _on_send_clicked(self) -> None:
        if self._streaming:
            self._stop_generation()
        else:
            self._send_message()

    def _send_message(self) -> None:
        text = self.input_field.text().strip()
        image_path = self._pending_image
        if not text and not image_path:
            return
        if self._streaming:
            return

        # Build the text shown in the chat vs. the text sent to the model.
        if image_path:
            name = os.path.basename(image_path)
            model_text = text or "What's in this image?"
            display_text = f"🖼 {name}" + (f"\n{text}" if text else "")
            images = [self._encode_image(image_path)]
        else:
            model_text = text
            display_text = text
            images = None

        self._append_message("user", display_text)
        self.input_field.clear()
        self._clear_attachment()
        self._start_stream(model_text, images)

    def _encode_image(self, path: str) -> str:
        with open(path, "rb") as handle:
            return base64.b64encode(handle.read()).decode("ascii")

    def _start_stream(self, model_text: str, images: Optional[List[str]]) -> None:
        history_lines = llm_prompt.get_history_tail(self.history_file, self.settings.history_messages)
        system_prompt = llm_prompt.render_prompt(history_lines, self.settings.history_messages)
        system_prompt += (
            "\n\nFormatting: reply in plain conversational text only. Do not use "
            "asterisks, markdown, or *action* descriptions (e.g. *purrs*)."
        )
        self._req_started = time.monotonic()
        self._req_text = model_text
        self._stream_raw = ""
        self._stop_event = threading.Event()
        self._streaming = True
        self._set_busy(True)
        self._show_typing_indicator()
        self._schedule_scroll()

        worker = _StreamWorker(self.backend, model_text, system_prompt, images, self._stop_event)
        worker.signals.chunk.connect(self._on_stream_chunk)
        worker.signals.error.connect(self._on_stream_error)
        worker.signals.finished.connect(self._on_stream_finished)
        self._thread_pool.start(worker)

    def _stop_generation(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        voice.stop_speaking()
        logger.info("Generation stopped by user")

    def _ensure_live_bubble(self) -> None:
        if self._live_bubble is not None:
            return
        self._hide_typing_indicator()
        bubble = MessageBubble("cat", "")
        self.messages_layout.addWidget(bubble, alignment=bubble.alignment_flag)
        self._live_bubble = bubble
        self._update_bubble_widths()

    def _on_stream_chunk(self, chunk: str) -> None:
        self._stream_raw += chunk
        self._ensure_live_bubble()
        if self._live_bubble is not None:
            self._live_bubble.set_text(_strip_markup(self._stream_raw))
        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_stream_error(self, message: str) -> None:
        logger.error("LLM backend error: %s", message)
        self._stream_raw = f"Error: {message}"

    def _on_stream_finished(self) -> None:
        # Remove the live bubble; commit the final text as a normal message.
        if self._live_bubble is not None:
            self._live_bubble.deleteLater()
            self.messages_layout.removeWidget(self._live_bubble)
            self._live_bubble = None
        self._hide_typing_indicator()

        final_text = _strip_markup(self._stream_raw).strip()
        if final_text:
            self._append_message("cat", final_text)
            self._speak(final_text)
        self._log_request_summary(final_text, success=not final_text.startswith("Error:"))

        self._streaming = False
        self._stop_event = None
        self._stream_raw = ""
        self._req_started = None
        self._req_text = None
        self._set_busy(False)
        self.input_field.setFocus()

    def _set_busy(self, busy: bool) -> None:
        self.input_field.setEnabled(not busy)
        self.attach_button.setEnabled(not busy)
        self.gear_button.setEnabled(not busy)
        self.mic_button.setEnabled(self._voice_ok and not busy)
        if busy:
            self.send_button.setText("■")
            self.send_button.setStyleSheet(STOP_BTN_STYLE)
            self.send_button.setToolTip("Stop the cat's response")
        else:
            self.send_button.setText("Send")
            self.send_button.setStyleSheet(SEND_BTN_STYLE)
            self.send_button.setToolTip("")

    # --- image attachment ----------------------------------------------------
    def _attach_image(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Attach image", str(llm_prompt.CFG_DIR.home()),
            "Images (*.png *.jpg *.jpeg *.webp *.gif *.bmp);;All files (*)",
        )
        if not path:
            return
        self._pending_image = path
        self.attach_label.setText(f"🖼 {os.path.basename(path)}")
        self.attach_row.setVisible(True)

    def _clear_attachment(self) -> None:
        self._pending_image = None
        self.attach_row.setVisible(False)

    # --- voice input (with live transcription) -------------------------------
    def _toggle_record(self) -> None:
        if not self._voice_ok or self._streaming:
            return
        if self._recorder.active:
            self._record_timer.stop()
            wav_path = self._recorder.stop()
            self.mic_button.setText("🎤")
            if not wav_path:
                self.input_field.setPlaceholderText("Write a message…")
                return
            self.mic_button.setEnabled(False)
            self.input_field.setPlaceholderText("Transcribing…")
            worker = _TranscribeWorker(wav_path)
            worker.signals.result.connect(self._on_transcribed)
            worker.signals.finished.connect(self._on_transcribe_finished)
            self._thread_pool.start(worker)
        else:
            self._recorder.start()
            self.mic_button.setText("🔴")
            self.input_field.clear()
            self.input_field.setPlaceholderText("Listening…")
            self._record_timer.start()

    def _tick_interim(self) -> None:
        if not self._recorder.active or self._interim_running:
            return
        path = self._recorder.path
        if not path:
            return
        self._interim_running = True
        worker = _InterimWorker(path)
        worker.signals.result.connect(self._on_interim_result)
        worker.signals.done.connect(self._on_interim_done)
        self._thread_pool.start(worker)

    def _on_interim_result(self, text: str) -> None:
        if self._recorder.active and text:
            self.input_field.setText(text)

    def _on_interim_done(self) -> None:
        self._interim_running = False

    def _on_transcribed(self, text: str) -> None:
        text = text.strip()
        if text:
            self.input_field.setText(text)
            self._send_message()

    def _on_transcribe_finished(self) -> None:
        self.mic_button.setEnabled(self._voice_ok)
        self.input_field.setPlaceholderText("Write a message…")

    # --- voice output --------------------------------------------------------
    def _toggle_tts(self) -> None:
        self._tts_enabled = not self._tts_enabled
        self.tts_toggle.setText("🔊" if self._tts_enabled else "🔇")
        if not self._tts_enabled:
            voice.stop_speaking()

    def _on_volume_changed(self, value: int) -> None:
        self._tts_volume = value / 100.0
        if value == 0 and self._tts_enabled:
            self._tts_enabled = False
            self.tts_toggle.setText("🔇")
        elif value > 0 and not self._tts_enabled:
            self._tts_enabled = True
            self.tts_toggle.setText("🔊")

    def _on_voice_changed(self, index: int) -> None:
        if not self._voice_ok:
            return
        path = self.voice_combo.itemData(index)
        if not path:
            return
        voice.set_voice(path)
        if self._tts_enabled and self._tts_volume > 0:
            self._start_speech("Mrow! This is my new voice.")

    def _speak(self, text: str) -> None:
        if not self._voice_ok or not self._tts_enabled or self._tts_volume <= 0:
            return
        self._start_speech(text)

    def _start_speech(self, text: str) -> None:
        # Animate the pet's mouth/face while it speaks, then return to idle.
        self._set_pet_talking(True)
        worker = _SpeakWorker(text, self._tts_volume)
        worker.signals.finished.connect(self._on_speech_done)  # primary stop
        self._thread_pool.start(worker)
        # Backstop: poll playback so we always return to idle even if the
        # worker's finished signal is missed.
        self._speech_seen = False
        self._speech_ticks = 0
        if not hasattr(self, "_speech_timer"):
            self._speech_timer = QtCore.QTimer(self)
            self._speech_timer.setInterval(200)
            self._speech_timer.timeout.connect(self._speech_tick)
        self._speech_timer.start()

    def _speech_tick(self) -> None:
        self._speech_ticks += 1
        speaking = False
        try:
            speaking = voice.is_speaking()
        except Exception:
            pass
        if speaking:
            self._speech_seen = True
        if (self._speech_seen and not speaking) or self._speech_ticks > 300:
            self._on_speech_done()

    def _on_speech_done(self) -> None:
        if hasattr(self, "_speech_timer"):
            self._speech_timer.stop()
        self._set_pet_talking(False)

    def _set_pet_talking(self, on: bool) -> None:
        self._talk_count = max(0, getattr(self, "_talk_count", 0) + (1 if on else -1))
        win = getattr(self.controller, "window", None)
        fn = getattr(win, "set_talking", None)
        if callable(fn):
            fn(self._talk_count > 0)

    # --- message rendering ---------------------------------------------------
    def _append_message(
        self, role: str, text: str, timestamp: Optional[str] = None, persist: bool = True
    ) -> None:
        timestamp = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if self.message_count == 0:
            self._messages = []
        self._messages.append((role, text, timestamp))
        self.message_count = len(self._messages)
        self._render_messages()
        if persist:
            llm_prompt.append_history_entry(self.history_file, role, text, timestamp)

    def _render_messages(self) -> None:
        if not self._messages:
            self._show_welcome_message()
            return
        self._clear_message_widgets()
        for role, text, _timestamp in self._messages:
            bubble = MessageBubble(role, text)
            self.messages_layout.addWidget(bubble, alignment=bubble.alignment_flag)
        self._schedule_scroll()
        self._update_bubble_widths()

    def _clear_message_widgets(self) -> None:
        while self.messages_layout.count():
            item = self.messages_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._typing_indicator = None
        self._live_bubble = None

    def _show_typing_indicator(self) -> None:
        if getattr(self, "_typing_indicator", None):
            return
        indicator = TypingIndicator()
        self.messages_layout.addWidget(indicator, alignment=QtCore.Qt.AlignmentFlag.AlignRight)
        self._typing_indicator = indicator
        self._schedule_scroll()

    def _hide_typing_indicator(self) -> None:
        indicator = getattr(self, "_typing_indicator", None)
        if not indicator:
            return
        indicator.deleteLater()
        self._typing_indicator = None
        self._schedule_scroll()

    def _scroll_to_bottom(self) -> None:
        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        self._update_bubble_widths()

    def _schedule_scroll(self) -> None:
        QtCore.QTimer.singleShot(0, self._scroll_to_bottom)
        QtCore.QTimer.singleShot(60, self._scroll_to_bottom)

    def _update_bubble_widths(self) -> None:
        viewport = self.scroll_area.viewport()
        max_width = max(100, int(viewport.width() * 0.85))
        for index in range(self.messages_layout.count()):
            item = self.messages_layout.itemAt(index)
            widget = item.widget()
            if isinstance(widget, MessageBubble):
                widget.set_max_width(max_width)
        self.messages_widget.setMinimumHeight(viewport.height())

    def _log_request_summary(self, response: str, success: bool) -> None:
        if self._req_started is None or self._req_text is None:
            return
        duration = time.monotonic() - self._req_started
        status = "success" if success else "error"
        logger.info("LLM request %s in %.2fs", status, duration)


# --- background workers ------------------------------------------------------
class _StreamSignals(QtCore.QObject):
    chunk = QtCore.Signal(str)
    error = QtCore.Signal(str)
    finished = QtCore.Signal()


class _StreamWorker(QtCore.QRunnable):
    """Streams the reply off the UI thread, chunk by chunk."""

    def __init__(self, backend, user_text, system_prompt, images, stop_event) -> None:
        super().__init__()
        self.backend = backend
        self.user_text = user_text
        self.system_prompt = system_prompt
        self.images = images
        self.stop_event = stop_event
        self.signals = _StreamSignals()

    def run(self) -> None:
        try:
            if hasattr(self.backend, "stream_reply"):
                for chunk in self.backend.stream_reply(
                    self.user_text, self.system_prompt, self.images, self.stop_event
                ):
                    self.signals.chunk.emit(chunk)
            else:
                self.signals.chunk.emit(self.backend.reply(self.user_text, self.system_prompt))
        except Exception as exc:  # pragma: no cover
            self.signals.error.emit(str(exc))
        finally:
            self.signals.finished.emit()


class _TranscribeSignals(QtCore.QObject):
    result = QtCore.Signal(str)
    finished = QtCore.Signal()


class _TranscribeWorker(QtCore.QRunnable):
    """Runs final speech-to-text off the UI thread."""

    def __init__(self, wav_path: str) -> None:
        super().__init__()
        self.wav_path = wav_path
        self.signals = _TranscribeSignals()

    def run(self) -> None:
        try:
            text = voice.transcribe(self.wav_path)
        except Exception as exc:  # pragma: no cover
            logger.error("Transcription failed: %s", exc)
            text = ""
        self.signals.result.emit(text)
        self.signals.finished.emit()


class _InterimSignals(QtCore.QObject):
    result = QtCore.Signal(str)
    done = QtCore.Signal()


class _InterimWorker(QtCore.QRunnable):
    """Transcribes the partial recording for live display."""

    def __init__(self, wav_path: str) -> None:
        super().__init__()
        self.wav_path = wav_path
        self.signals = _InterimSignals()

    def run(self) -> None:
        try:
            text = voice.transcribe_partial(self.wav_path)
        except Exception as exc:  # pragma: no cover
            logger.debug("Interim transcription failed: %s", exc)
            text = ""
        self.signals.result.emit(text)
        self.signals.done.emit()


class _SpeakSignals(QtCore.QObject):
    finished = QtCore.Signal()


class _SpeakWorker(QtCore.QRunnable):
    """Synthesizes and plays the cat's reply off the UI thread."""

    def __init__(self, text: str, volume: float) -> None:
        super().__init__()
        self.text = text
        self.volume = volume
        self.signals = _SpeakSignals()

    def run(self) -> None:
        try:
            voice.speak(self.text, self.volume)
        except Exception as exc:  # pragma: no cover
            logger.error("TTS playback failed: %s", exc)
        finally:
            self.signals.finished.emit()


class MessageBubble(QtWidgets.QWidget):
    """A single chat bubble that copies its text on click and flashes opacity."""

    def __init__(self, role: str, text: str) -> None:
        super().__init__()
        self.role = role
        self.raw_text = text

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        alignment = QtCore.Qt.AlignmentFlag.AlignLeft if role == "user" else QtCore.Qt.AlignmentFlag.AlignRight
        layout.setAlignment(alignment)
        self.alignment_flag = alignment
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Minimum)

        self.frame = QtWidgets.QFrame()
        self.frame.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        color = "#dff3df" if role == "user" else "#e4ecff"
        self.frame.setStyleSheet(
            f"QFrame {{ background-color: {color}; border: none; border-radius: 12px; }}"
        )
        self.frame.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Minimum)
        inner = QtWidgets.QVBoxLayout(self.frame)
        inner.setContentsMargins(10, 6, 10, 6)
        inner.setSpacing(2)

        header = QtWidgets.QLabel("You" if role == "user" else personas.label())
        header.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        header.setStyleSheet("font-size: 11px; font-weight: bold; color: #6a6a6a;")

        body = QtWidgets.QLabel(text.replace("\r\n", "\n"))
        body.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        body.setWordWrap(True)
        body.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        body.setStyleSheet("font-size: 13px; color: #1c1c1c; background: transparent;")
        body.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Minimum)

        inner.addWidget(header)
        inner.addWidget(body)
        layout.addWidget(self.frame)

        self._body_label = body
        self._opacity_timer = QtCore.QTimer(self)
        self._opacity_timer.setSingleShot(True)
        self._opacity_timer.timeout.connect(self._restore_opacity)

    def set_text(self, text: str) -> None:
        """Update the bubble text in place (used for streaming replies)."""
        self.raw_text = text
        self._body_label.setText(text.replace("\r\n", "\n"))

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            QtWidgets.QApplication.clipboard().setText(self.raw_text)
            self._body_label.setStyleSheet("font-size: 13px; color: rgba(28,28,28,0.4);")
            self._opacity_timer.start(200)
        super().mousePressEvent(event)

    def _restore_opacity(self) -> None:
        self._body_label.setStyleSheet("font-size: 13px; color: #1c1c1c; background: transparent;")

    def set_max_width(self, width: int) -> None:
        self.frame.setMaximumWidth(width)
        max_body = max(50, width - 12)
        self.frame.setMinimumWidth(max_body)
        self._body_label.setMaximumWidth(max_body - 12)
        self._body_label.setMinimumWidth(max(60, max_body - 12))


class TypingIndicator(QtWidgets.QWidget):
    """Animated indicator shown while waiting for assistant reply."""

    def __init__(self) -> None:
        super().__init__()
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)

        frame = QtWidgets.QFrame()
        frame.setStyleSheet("QFrame { background-color: #e4ecff; border: none; border-radius: 12px; }")
        inner = QtWidgets.QHBoxLayout(frame)
        inner.setContentsMargins(14, 8, 14, 8)
        self.label = QtWidgets.QLabel("⋯")
        self.label.setStyleSheet("font-size: 14px; color: #1c1c1c;")
        inner.addWidget(self.label)
        layout.addWidget(frame)

        self._phase = 0
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._timer.start(400)

    def _advance(self) -> None:
        self.label.setText("●" * self._phase + "○" * (3 - self._phase))
        self._phase = (self._phase + 1) % 4


__all__ = ["attach_chat"]
