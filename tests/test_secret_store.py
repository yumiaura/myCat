"""Tests for the security helpers (chmod 600 + keyring fallback)."""

import os
import stat
import sys

import pytest

from mycat import secret_store


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX file modes")
def test_secure_file_sets_owner_only(tmp_path):
    path = tmp_path / "config.ini"
    path.write_text("secret = 1\n")
    os.chmod(path, 0o644)
    secret_store.secure_file(path)
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600


def test_secure_file_missing_path_is_noop(tmp_path):
    # Must not raise even when the file does not exist.
    secret_store.secure_file(tmp_path / "nope.ini")


def test_secret_helpers_degrade_without_keyring(monkeypatch):
    # Simulate keyring being unavailable: every call should be a safe no-op.
    import builtins

    real_import = builtins.__import__

    def block_keyring(name, *args, **kwargs):
        if name == "keyring":
            raise ImportError("no keyring")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", block_keyring)
    assert secret_store.keyring_available() is False
    assert secret_store.get_secret("openai_api_key") == ""
    assert secret_store.set_secret("openai_api_key", "x") is False
    secret_store.delete_secret("openai_api_key")  # no raise
