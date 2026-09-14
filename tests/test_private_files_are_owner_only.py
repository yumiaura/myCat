"""Every file myCat creates that holds private data is owner-only.

`secret_store.secure_file` already existed and was already called from config_store,
github_notify, llm_prompt and main. These assert the whole population rather than one
member of it, so a new writer joins the check the day it is added.
"""

from __future__ import annotations

import ast
import configparser
import stat
import sys
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "mycat"
OWNER_ONLY = 0o600


def config_writers() -> list[str]:
    """Every `open(<a config path>, 'w')` in the package, as file:line."""
    found = []
    for path in sorted(SOURCE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        lines = path.read_text(encoding="utf-8").splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id != "open" or len(node.args) < 2:
                continue
            mode = node.args[1]
            if not (isinstance(mode, ast.Constant) and "w" in str(mode.value)):
                continue
            target = ast.unparse(node.args[0]).lower()
            if "cfg" not in target and "config" not in target:
                continue
            window = "\n".join(lines[node.lineno - 1: node.lineno + 6])
            if "secure_file" not in window:
                found.append(f"{path.name}:{node.lineno}")
    return found


def test_every_config_writer_restricts_the_file_it_wrote():
    """A config holding an api_key must not be left at the umask default."""
    assert config_writers() == []


def test_the_sweep_found_writers_to_check():
    """Guard the guard: a sweep that matches nothing would pass silently."""
    total = 0
    for path in sorted(SOURCE.rglob("*.py")):
        total += path.read_text(encoding="utf-8").count("secure_file(")
    assert total >= 8, f"only {total} secure_file call sites found — has the helper been renamed?"


@pytest.mark.skipif(sys.platform.startswith("win"), reason="Windows has no POSIX mode bits")
def test_saving_a_vendor_key_leaves_an_owner_only_file(tmp_path, monkeypatch):
    from mycat import llm_prompt, llm_vendors

    cfg = tmp_path / "config.ini"
    monkeypatch.setattr(llm_prompt, "CFG_DIR", tmp_path)
    monkeypatch.setattr(llm_prompt, "CFG_FILE", cfg)
    monkeypatch.setattr(llm_vendors, "CFG_FILE", cfg)

    llm_vendors.save_vendor(
        llm_vendors.Vendor("acme", llm_vendors.KIND_OPENAI, "https://api.example.com/v1",
                           model="m", api_key="sk-test-not-a-real-key"),
        make_active=True,
    )

    assert cfg.exists()
    assert stat.S_IMODE(cfg.stat().st_mode) == OWNER_ONLY

    parser = configparser.ConfigParser()
    parser.read(cfg, encoding="utf-8")
    assert parser.get("vendor:acme", "api_key") == "sk-test-not-a-real-key"


@pytest.mark.skipif(sys.platform.startswith("win"), reason="Windows has no POSIX mode bits")
def test_activity_database_is_owner_only(tmp_path):
    """It records per-minute keyboard and mouse counts for the history window."""
    from mycat import activity_store

    store = activity_store.ActivityStore(db_path=tmp_path / "activity.db")
    try:
        assert stat.S_IMODE((tmp_path / "activity.db").stat().st_mode) == OWNER_ONLY
    finally:
        store.connection.close()
