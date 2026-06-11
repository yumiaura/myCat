"""Tests for config persistence: Ollama url/model and the LLM enabled flag."""

from mycat import llm_prompt


def use_tmp_config(monkeypatch, tmp_path):
    monkeypatch.setattr(llm_prompt, "CFG_DIR", tmp_path)
    monkeypatch.setattr(llm_prompt, "CFG_FILE", tmp_path / "config.ini")


def test_save_ollama_settings_roundtrip(monkeypatch, tmp_path):
    use_tmp_config(monkeypatch, tmp_path)
    monkeypatch.delenv("OLLAMA_URL", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)

    llm_prompt.save_ollama_settings("http://1.2.3.4:9999", "qwen3:8b")
    settings = llm_prompt.load_llm_settings()
    assert settings.ollama_url == "http://1.2.3.4:9999"
    assert settings.ollama_model == "qwen3:8b"


def test_save_ollama_settings_preserves_other_sections(monkeypatch, tmp_path):
    use_tmp_config(monkeypatch, tmp_path)
    (tmp_path / "config.ini").write_text("[window]\nx = 5\ny = 7\n")

    llm_prompt.save_ollama_settings("http://host:11434", "m")
    text = (tmp_path / "config.ini").read_text()
    assert "[window]" in text and "x = 5" in text
    assert "[ollama]" in text


def test_llm_enabled_default_true(monkeypatch, tmp_path):
    use_tmp_config(monkeypatch, tmp_path)
    monkeypatch.delenv("LLM_ENABLED", raising=False)
    assert llm_prompt.load_llm_enabled() is True


def test_llm_enabled_config_overrides_env(monkeypatch, tmp_path):
    use_tmp_config(monkeypatch, tmp_path)
    monkeypatch.setenv("LLM_ENABLED", "1")  # env says on

    assert llm_prompt.load_llm_enabled() is True
    llm_prompt.save_llm_enabled(False)
    assert llm_prompt.load_llm_enabled() is False  # config wins over env
    llm_prompt.save_llm_enabled(True)
    assert llm_prompt.load_llm_enabled() is True


def test_llm_enabled_reads_env_when_no_config(monkeypatch, tmp_path):
    use_tmp_config(monkeypatch, tmp_path)
    monkeypatch.setenv("LLM_ENABLED", "0")
    assert llm_prompt.load_llm_enabled() is False
