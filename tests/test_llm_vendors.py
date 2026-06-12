"""Tests for the vendor registry: presets, key resolution, save/load."""

from mycat import llm_vendors


def use_tmp_config(monkeypatch, tmp_path):
    monkeypatch.setattr(llm_vendors, "CFG_DIR", tmp_path)
    monkeypatch.setattr(llm_vendors, "CFG_FILE", tmp_path / "config.ini")


def test_builtin_presets_present():
    vendors = llm_vendors.builtin_vendors()
    for name in ("ollama", "openai", "grok", "groq", "deepseek", "openrouter"):
        assert name in vendors
    assert vendors["ollama"].kind == llm_vendors.KIND_OLLAMA
    assert vendors["openai"].kind == llm_vendors.KIND_OPENAI
    assert vendors["ollama"].needs_key is False
    assert vendors["grok"].needs_key is True


def test_resolve_key_prefers_literal_then_env(monkeypatch):
    literal = llm_vendors.Vendor("x", llm_vendors.KIND_OPENAI, "http://x", api_key="lit", api_key_env="X_KEY")
    assert literal.resolve_key() == "lit"

    from_env = llm_vendors.Vendor("x", llm_vendors.KIND_OPENAI, "http://x", api_key_env="X_KEY")
    monkeypatch.setenv("X_KEY", "from-env")
    assert from_env.resolve_key() == "from-env"
    monkeypatch.delenv("X_KEY", raising=False)
    assert from_env.resolve_key() == ""


def test_save_and_load_custom_vendor(monkeypatch, tmp_path):
    use_tmp_config(monkeypatch, tmp_path)
    vendor = llm_vendors.Vendor("myco", llm_vendors.KIND_OPENAI, "https://api.myco.ai/v1", api_key="sk-1", model="m1")
    llm_vendors.save_vendor(vendor, make_active=True)

    vendors = llm_vendors.load_vendors()
    assert "myco" in vendors
    assert vendors["myco"].base_url == "https://api.myco.ai/v1"
    assert vendors["myco"].api_key == "sk-1"
    assert vendors["myco"].model == "m1"
    assert llm_vendors.active_vendor_name() == "myco"


def test_save_without_literal_key_keeps_it_off_disk(monkeypatch, tmp_path):
    use_tmp_config(monkeypatch, tmp_path)
    vendor = llm_vendors.Vendor(
        "openai", llm_vendors.KIND_OPENAI, "https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY", model="gpt-4o-mini",
    )
    llm_vendors.save_vendor(vendor, make_active=True)
    text = (tmp_path / "config.ini").read_text()
    assert "api_key =" not in text
    assert "model = gpt-4o-mini" in text


def test_default_active_vendor_is_ollama(monkeypatch, tmp_path):
    use_tmp_config(monkeypatch, tmp_path)
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    assert llm_vendors.active_vendor_name() == "ollama"
