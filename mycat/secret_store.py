"""Security helpers: owner-only config files and OS-keyring-backed secrets.

Keyring is optional — when it (or a backend) is missing every call degrades
gracefully so the app keeps working with plaintext config + chmod 600.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

KEYRING_SERVICE = "mycat"


def secure_file(path) -> None:
    """Restrict a file to the owner (chmod 600). No-op where unsupported (Windows)."""
    try:
        os.chmod(path, 0o600)
    except (OSError, NotImplementedError):
        pass


def keyring_available() -> bool:
    try:
        import keyring

        backend = keyring.get_keyring()
        # The "fail" backend is registered when nothing usable is installed.
        return backend is not None and "fail" not in type(backend).__name__.lower()
    except Exception:  # noqa: BLE001 - any import/backend error means "unavailable"
        return False


def get_secret(name: str) -> str:
    """Read a secret from the OS keyring, or "" when unavailable/absent."""
    try:
        import keyring

        return keyring.get_password(KEYRING_SERVICE, name) or ""
    except Exception:  # noqa: BLE001
        return ""


def set_secret(name: str, value: str) -> bool:
    """Store a secret in the OS keyring. Returns True on success."""
    try:
        import keyring

        keyring.set_password(KEYRING_SERVICE, name, value)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.debug("keyring set failed for %s: %s", name, exc)
        return False


def delete_secret(name: str) -> None:
    try:
        import keyring

        keyring.delete_password(KEYRING_SERVICE, name)
    except Exception:  # noqa: BLE001
        pass


__all__ = [
    "KEYRING_SERVICE",
    "secure_file",
    "keyring_available",
    "get_secret",
    "set_secret",
    "delete_secret",
]
