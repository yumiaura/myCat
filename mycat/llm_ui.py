"""Chat UI layer for PixelCat."""

from __future__ import annotations

import html
import logging
import time
from datetime import datetime
from typing import List, Optional, TYPE_CHECKING

from PySide6 import QtCore, QtGui, QtWidgets

from . import llm_prompt

if TYPE_CHECKING:
    from .llm import LLMContext

logger = logging.getLogger(__name__)


def attach_chat(window: QtWidgets.QWidget, context: "LLMContext") -> None:
    controller = _LLMController(window, context)
    setattr(window, "_llm_controller", controller)
    logger.debug("Chat controller attached to window %s", window)


class _LLMController(QtCore.QObject):
    """Owns the chat dialog lifecycle and keeps it anchored to the cat window."""

    def __init__(self, window: QtWidgets.QWidget, context: "LLMContext") -> None:
        super().__init__(window)
        self.window = window
        self.context = context
        self.chat_dialog: Optional[ChatDialog] = None
        self._press_pos: Optional[QtCore.QPoint] = None
        self._press_time: Optional[float] = None
        self.history_file = llm_prompt.ensure_history_file()

        window.installEventFilter(self)
        window.destroyed.connect(self._on_window_destroyed)
        logger.debug("LLM controller initialised with history file %s", self.history_file)

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if watched is self.window:
            if event.type() == QtCore.QEvent.Type.MouseButtonPress:
                self._handle_press(event)
            elif event.type() == QtCore.QEvent.Type.MouseButtonRelease:
                self._handle_release(event)
            elif event.type() in (QtCore.QEvent.Type.Move, QtCore.QEvent.Type.Resize):
                self._position_dialog()
        return super().eventFilter(watched, event)

    def _handle_press(self, event: QtCore.QEvent) -> None:
        if not isinstance(event, QtGui.QMouseEvent):
            return
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return
        self._press_pos = event.globalPosition().toPoint()
        self._press_time = time.monotonic()

    def _handle_release(self, event: QtCore.QEvent) -> None:
        if not isinstance(event, QtGui.QMouseEvent):
            return
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return
        if self._press_time is None or self._press_pos is None:
            return
        duration = time.monotonic() - self._press_time
        distance = (event.globalPosition().toPoint() - self._press_pos).manhattanLength()
        self._press_time = None
        self._press_pos = None

        if duration < 0.25 and distance < 6:
            self._toggle_chat()

    def _toggle_chat(self) -> None:
        if self.chat_dialog:
            if self.chat_dialog.isVisible():
                logger.debug("Hiding chat dialog")
                self.chat_dialog.hide()
                return
            logger.debug("Showing existing chat dialog")
            self.chat_dialog.show()
            self._position_dialog()
            self.chat_dialog.raise_()
            self.chat_dialog.activateWindow()
            return

        logger.debug("Creating new chat dialog")
        dialog = ChatDialog(self)
        dialog.show()
        dialog.destroyed.connect(self._on_chat_destroyed)
        self.chat_dialog = dialog
        self._position_dialog()

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
        logger.debug("Chat dialog destroyed")
        self.chat_dialog = None

    def _on_window_destroyed(self, *_args) -> None:
        self.chat_dialog = None


class ChatDialog(QtWidgets.QDialog):
    """Frameless chat dialog with message history and async LLM requests."""

    def __init__(self, controller: _LLMController):
        super().__init__(controller.window)
        self.controller = controller
        self.backend = controller.context.backend
        self.settings = controller.context.settings
        self.history_file = controller.history_file
        self.message_count = 0
        self._waiting_for_response = False
        self._thread_pool = QtCore.QThreadPool.globalInstance()
        self._pending_worker: Optional[_LLMWorker] = None
        self._pending_request_started: Optional[float] = None
        self._pending_request_text: Optional[str] = None
        self._suspend_anchor = False
        self._messages: List[tuple[str, str, str]] = []

        self.setWindowFlags(
            QtCore.Qt.WindowType.Window
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
        )
        title_suffix = controller.context.backend_name.capitalize()
        self.setWindowTitle(f"Chat with a cat ({title_suffix})")
        self.resize(360, 420)
        self.setMinimumSize(320, 260)
        self.setSizeGripEnabled(True)
        self.setModal(False)

        self._build_ui()
        self._load_history()

    def _build_ui(self) -> None:
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(2)

        self.scroll_area = QtWidgets.QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        main_layout.addWidget(self.scroll_area, 1)

        self.messages_widget = QtWidgets.QWidget()
        self.messages_layout = QtWidgets.QVBoxLayout(self.messages_widget)
        self.messages_layout.setContentsMargins(6, 6, 6, 6)
        self.messages_layout.setSpacing(4)
        self.messages_layout.insertStretch(0, 1)
        self.scroll_area.setWidget(self.messages_widget)
        self.scroll_area.verticalScrollBar().rangeChanged.connect(
            lambda *_: QtCore.QTimer.singleShot(0, self._scroll_to_bottom)
        )

        input_layout = QtWidgets.QHBoxLayout()
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(2)

        button_style = """
            QPushButton {
                background-color: #dfdfdf;
                border: 1px solid #b0b0b0;
                border-radius: 0;
                padding: 0 6px;
                min-width: 32px;
            }
            QPushButton:hover {
                background-color: #cecece;
            }
            QPushButton:pressed {
                background-color: #bdbdbd;
            }
        """

        self.input_field = QtWidgets.QLineEdit()
        self.input_field.setPlaceholderText("Write a message…")
        self.input_field.setMinimumHeight(34)
        self.input_field.setStyleSheet(
            """
            QLineEdit {
                background-color: white;
                border: 1px solid #b0b0b0;
                border-radius: 0;
                padding-left: 10px;
                padding-right: 10px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #8a8a8a;
            }
        """
        )
        input_layout.addWidget(self.input_field, 1)

        self.send_button = QtWidgets.QPushButton("Send")
        self.send_button.setMinimumHeight(34)
        self.send_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.send_button.setStyleSheet(button_style)
        self.send_button.setDefault(True)
        self.send_button.setAutoDefault(True)
        self.send_button.clicked.connect(self._send_message)
        input_layout.addWidget(self.send_button)

        self.history_button = QtWidgets.QPushButton("📁")
        self.history_button.setMinimumHeight(34)
        self.history_button.setDefault(False)
        self.history_button.setAutoDefault(False)
        self.history_button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.history_button.setToolTip("Open history/config folder")
        self.history_button.clicked.connect(self._open_history_folder)
        self.history_button.setStyleSheet(button_style)
        input_layout.addWidget(self.history_button)

        main_layout.addLayout(input_layout)
        self.input_field.returnPressed.connect(self._send_message)
        self._typing_indicator: Optional[TypingIndicator] = None

    def _load_history(self) -> None:
        entries = llm_prompt.parse_history_file(self.history_file)
        self._messages = entries
        self.message_count = len(entries)
        logger.debug("Loaded %d history entries", self.message_count)
        self._render_messages()

    def _show_welcome_message(self) -> None:
        self._messages = []
        self._clear_message_widgets()
        label = QtWidgets.QLabel("Write something...")
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: #888; font-style: italic; margin-top: 40px;")
        self.messages_layout.addWidget(label)
        self.message_count = 0

    def _open_history_folder(self) -> None:
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(llm_prompt.CFG_DIR)))

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self.controller.window.isVisible():
            event.ignore()
            self.hide()
        else:
            super().closeEvent(event)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        if not getattr(self, "_suspend_anchor", False):
            self.controller._position_dialog()

    def moveEvent(self, event: QtGui.QMoveEvent) -> None:
        super().moveEvent(event)
        if not getattr(self, "_suspend_anchor", False):
            self.controller._position_dialog()

    def _send_message(self) -> None:
        text = self.input_field.text().strip()
        if not text or self._waiting_for_response:
            return
        logger.info("Request: %s", text)
        self._append_message("user", text)
        QtCore.QTimer.singleShot(0, self._scroll_to_bottom)
        self.input_field.clear()
        self._set_input_enabled(False)
        self._waiting_for_response = True
        self._request_ai_response(text)
        self._show_typing_indicator()
        self._schedule_scroll()

    def _request_ai_response(self, text: str) -> None:
        history_lines = llm_prompt.get_history_tail(self.history_file, self.settings.history_messages)
        system_prompt = llm_prompt.render_prompt(history_lines, self.settings.history_messages)
        self._pending_request_started = time.monotonic()
        self._pending_request_text = text
        worker = _LLMWorker(self.backend, text, system_prompt)
        worker.signals.result.connect(self._on_ai_success)
        worker.signals.error.connect(self._on_ai_error)
        worker.signals.finished.connect(self._on_ai_finished)
        self._thread_pool.start(worker)
        self._pending_worker = worker

    def _on_ai_success(self, answer: str) -> None:
        self._append_message("cat", answer)
        self._schedule_scroll()
        self._log_request_summary(answer, success=True)

    def _on_ai_error(self, message: str) -> None:
        logger.error("LLM backend error: %s", message)
        self._append_message("cat", f"Error: {message}")
        self._schedule_scroll()
        self._log_request_summary(message, success=False)

    def _on_ai_finished(self) -> None:
        self._pending_worker = None
        self._waiting_for_response = False
        self._set_input_enabled(True)
        self._pending_request_started = None
        self._pending_request_text = None
        self._hide_typing_indicator()

    def _set_input_enabled(self, enabled: bool) -> None:
        self.input_field.setEnabled(enabled)
        self.send_button.setEnabled(enabled)
        self.history_button.setEnabled(enabled)

    def _append_message(
        self,
        role: str,
        text: str,
        timestamp: Optional[str] = None,
        persist: bool = True,
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
        for index in range(self.messages_layout.count() - 1, 0, -1):
            item = self.messages_layout.takeAt(index)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._typing_indicator = None

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

    def _log_request_summary(self, response: str, success: bool) -> None:
        if self._pending_request_started is None or self._pending_request_text is None:
            return
        duration = time.monotonic() - self._pending_request_started
        status = "success" if success else "error"
        logger.info("Request: %s", self._pending_request_text)
        logger.info("LLM request %s in %.2fs", status, duration)
        logger.info("Response: %s", response)


class _LLMWorkerSignals(QtCore.QObject):
    """Qt signals emitted by the background worker."""
    result = QtCore.Signal(str)
    error = QtCore.Signal(str)
    finished = QtCore.Signal()


class _LLMWorker(QtCore.QRunnable):
    """Runs LLM requests off the UI thread and streams results via signals."""
    def __init__(self, backend, user_text: str, system_prompt: str) -> None:
        super().__init__()
        self.backend = backend
        self.user_text = user_text
        self.system_prompt = system_prompt
        self.signals = _LLMWorkerSignals()

    def run(self) -> None:
        try:
            answer = self.backend.reply(self.user_text, self.system_prompt)
        except Exception as exc:  # pragma: no cover
            self.signals.error.emit(str(exc))
        else:
            self.signals.result.emit(answer)
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
        color = "#e0f5e0" if role == "user" else "#e0ebff"
        self.frame.setStyleSheet(
            f"""
            QFrame {{
                background-color: {color};
                border: none;
            }}
            """
        )
        self.frame.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Minimum)
        inner = QtWidgets.QVBoxLayout(self.frame)
        inner.setContentsMargins(6, 4, 6, 4)
        inner.setSpacing(2)

        header = QtWidgets.QLabel("Request" if role == "user" else "Response")
        header.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        header.setStyleSheet("font-size: 13px; color: #1c1c1c;")

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
        self.frame.setMinimumWidth(min(width, 200))
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
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        frame = QtWidgets.QFrame()
        frame.setStyleSheet(
            """
            QFrame {
                background-color: #e0ebff;
                border: none;
            }
            """
        )
        inner = QtWidgets.QHBoxLayout(frame)
        inner.setContentsMargins(12, 6, 12, 6)
        self.label = QtWidgets.QLabel("⋯")
        self.label.setStyleSheet("font-size: 14px; color: #1c1c1c;")
        inner.addWidget(self.label)
        layout.addWidget(frame)

        self._phase = 0
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._timer.start(1000)

    def _advance(self) -> None:
        if self._phase < 3:
            opacity = 1.0
        else:
            opacity = 0.5
        self.label.setStyleSheet(f"font-size: 14px; color: rgba(28,28,28,{opacity});")
        self._phase = (self._phase + 1) % 4


__all__ = ["attach_chat"]
