"""Tests for the vendor settings dialog (Qt offscreen, no network)."""

from PySide6 import QtWidgets

from mycat import llm_settings_ui


def make_window():
    return QtWidgets.QWidget()


def test_vendor_dropdown_lists_presets_and_custom(qapp):
    dialog = llm_settings_ui.LLMSettingsDialog(make_window())
    items = [dialog.vendor_combo.itemText(i) for i in range(dialog.vendor_combo.count())]
    assert items[-1] == llm_settings_ui.ADD_CUSTOM
    assert any("Ollama" in t for t in items)
    assert any("OpenAI" in t for t in items)
    assert any("Grok" in t for t in items)


def test_key_field_hidden_for_ollama_shown_for_openai(qapp):
    dialog = llm_settings_ui.LLMSettingsDialog(make_window())
    dialog.vendor_combo.setCurrentIndex(dialog.vendor_combo.findData("ollama"))
    assert dialog.key_edit.isHidden() is True
    dialog.vendor_combo.setCurrentIndex(dialog.vendor_combo.findData("openai"))
    assert dialog.key_edit.isHidden() is False
    assert dialog.base_url_edit.text() == "https://api.openai.com/v1"


def test_custom_mode_makes_name_editable(qapp):
    dialog = llm_settings_ui.LLMSettingsDialog(make_window())
    dialog.vendor_combo.setCurrentIndex(dialog.vendor_combo.findText(llm_settings_ui.ADD_CUSTOM))
    assert dialog.is_custom_mode() is True
    assert dialog.name_edit.isReadOnly() is False
    assert dialog.kind_combo.isEnabled() is True


def test_model_text_toggles_actions(qapp):
    dialog = llm_settings_ui.LLMSettingsDialog(make_window())
    dialog.model_combo.setCurrentText("")
    dialog.on_model_changed()
    assert dialog.save_btn.isEnabled() is False
    assert dialog.test_btn.isEnabled() is False
    dialog.model_combo.setCurrentText("some-model")
    assert dialog.save_btn.isEnabled() is True
    assert dialog.test_btn.isEnabled() is True


def test_effective_key_uses_field_then_env(qapp, monkeypatch):
    dialog = llm_settings_ui.LLMSettingsDialog(make_window())
    dialog.vendor_combo.setCurrentIndex(dialog.vendor_combo.findData("openai"))
    dialog.key_edit.setText("typed-key")
    assert dialog.effective_key() == "typed-key"
    dialog.key_edit.setText("")
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    assert dialog.effective_key() == "env-key"


def test_switching_vendor_clears_stale_models(qapp):
    dialog = llm_settings_ui.LLMSettingsDialog(make_window())
    dialog.vendor_combo.setCurrentIndex(dialog.vendor_combo.findData("ollama"))
    dialog.on_models(["llama3.1", "qwen3:8b"])
    assert dialog.model_combo.count() == 2

    dialog.vendor_combo.setCurrentIndex(dialog.vendor_combo.findData("openai"))
    items = [dialog.model_combo.itemText(i) for i in range(dialog.model_combo.count())]
    assert "llama3.1" not in items
    assert "qwen3:8b" not in items
