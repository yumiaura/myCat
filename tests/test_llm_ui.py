"""Chat window show / minimize behavior."""

from PySide6 import QtCore, QtWidgets

from mycat import llm_prompt, llm_ui
from mycat.llm import LLMContext


class DummyBackend:
    def reply(self, user_text: str, system_prompt: str) -> str:
        return "ok"


def _attach(qapp, tmp_path, monkeypatch):
    history = tmp_path / "history.txt"
    history.write_text("", encoding="utf-8")
    monkeypatch.setattr(llm_prompt, "ensure_history_file", lambda: history)

    host = QtWidgets.QWidget()
    host.setGeometry(200, 200, 80, 80)
    host.show()
    context = LLMContext(
        backend_name="ollama",
        backend=DummyBackend(),
        settings=llm_prompt.LLMSettings(None, "m", "http://127.0.0.1:11434", "m", 5.0, 8),
        enabled=True,
    )
    llm_ui.attach_chat(host, context, enabled=True)
    qapp.processEvents()
    return host


def test_toggle_restores_a_minimized_chat(qapp, tmp_path, monkeypatch):
    host = _attach(qapp, tmp_path, monkeypatch)
    host.toggle_llm_chat()
    qapp.processEvents()
    dialog = host.llm_controller.chat_dialog
    assert dialog is not None and dialog.isVisible()

    dialog.setWindowState(QtCore.Qt.WindowState.WindowMinimized)
    qapp.processEvents()
    assert dialog.isMinimized()

    host.toggle_llm_chat()
    qapp.processEvents()
    assert dialog.isVisible()
    assert not dialog.isMinimized()

    host.toggle_llm_chat()
    qapp.processEvents()
    assert not dialog.isVisible()


def test_minimized_chat_is_not_dragged_back_onscreen(qapp, tmp_path, monkeypatch):
    host = _attach(qapp, tmp_path, monkeypatch)
    host.toggle_llm_chat()
    qapp.processEvents()
    dialog = host.llm_controller.chat_dialog
    dialog.setWindowState(QtCore.Qt.WindowState.WindowMinimized)
    qapp.processEvents()

    calls: list[str] = []
    host.llm_controller.position_dialog = lambda: calls.append("pos")
    dialog.move(dialog.x() + 40, dialog.y() + 40)
    qapp.processEvents()
    assert calls == []
