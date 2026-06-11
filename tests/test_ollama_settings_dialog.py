"""Tests for the Ollama settings dialog logic (Qt offscreen, no network)."""

from PySide6 import QtWidgets

from mycat import llm_settings_ui


def make_window():
    return QtWidgets.QWidget()


def test_buttons_disabled_until_model_selected(qapp):
    dialog = llm_settings_ui.OllamaSettingsDialog(make_window())
    assert dialog.test_btn.isEnabled() is False
    assert dialog.save_btn.isEnabled() is False


def test_on_models_populates_and_preselects(qapp):
    dialog = llm_settings_ui.OllamaSettingsDialog(make_window())
    dialog.saved_model = "b"
    dialog.on_models(["a", "b", "c"])
    assert dialog.model_combo.isEnabled()
    assert dialog.model_combo.currentText() == "b"
    assert dialog.test_btn.isEnabled()
    assert dialog.save_btn.isEnabled()


def test_invalidate_models_disables_actions(qapp):
    dialog = llm_settings_ui.OllamaSettingsDialog(make_window())
    dialog.on_models(["a", "b"])
    dialog.invalidate_models()
    assert dialog.model_combo.count() == 0
    assert dialog.test_btn.isEnabled() is False
    assert dialog.save_btn.isEnabled() is False


def test_base_url_from_host_and_port(qapp):
    dialog = llm_settings_ui.OllamaSettingsDialog(make_window())
    dialog.host_edit.setText("example.local")
    dialog.port_spin.setValue(12345)
    assert dialog.base_url() == "http://example.local:12345"


class Backend:
    chat_url = "http://old/api/chat"
    model = "old"


class Settings:
    ollama_url = "http://old"
    ollama_model = "old"
    ollama_timeout = 60.0


class Context:
    backend_name = "ollama"
    backend = Backend()
    settings = Settings()
    enabled = True


class Controller:
    def __init__(self):
        self.context = Context()
        self.enabled_calls = []

    def is_enabled(self):
        return True

    def set_enabled(self, value):
        self.enabled_calls.append(value)


def test_apply_live_updates_existing_backend(qapp):
    window = make_window()
    window._llm_controller = Controller()
    dialog = llm_settings_ui.OllamaSettingsDialog(window)

    dialog.apply_live("http://1.2.3.4:9999", "qwen3:8b", False)

    controller = window._llm_controller
    assert controller.context.backend.chat_url == "http://1.2.3.4:9999/api/chat"
    assert controller.context.backend.model == "qwen3:8b"
    assert controller.context.settings.ollama_url == "http://1.2.3.4:9999"
    assert controller.context.enabled is False
    assert controller.enabled_calls == [False]
