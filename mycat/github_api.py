"""Shared GitHub REST helper — the one place the auth token is attached.

If a token is configured — the ``[github]`` section's ``token`` (the same one the
notifications feature uses), or the ``GITHUB_TOKEN`` env var — every GitHub
request goes out authenticated, lifting the anonymous 60 req/h per-IP cap to
5000 req/h. Both the notifications poller and the update check build their
requests here, so a token set once is used for every GitHub call.
"""

from __future__ import annotations

import logging
import os
import urllib.request

from . import config_store, paths

logger = logging.getLogger(__name__)

ACCEPT = "application/vnd.github+json"
API_VERSION = "2022-11-28"
USER_AGENT = "mycat-desktop-pet"
DEFAULT_TOKEN_ENV = "GITHUB_TOKEN"


def resolve_token(config_token: str = "", token_env: str = DEFAULT_TOKEN_ENV) -> str:
    """A literal config token wins; otherwise fall back to the env var."""
    return config_token or os.getenv(token_env, "")


def github_token() -> str:
    """The token to authenticate GitHub calls, read from the ``[github]`` config
    (or ``GITHUB_TOKEN``) — for callers without a loaded settings object."""
    config = config_store.read_config(paths.config_file())
    if config is None or "github" not in config:
        return resolve_token()
    section = config["github"]
    return resolve_token(section.get("token", ""), section.get("token_env", DEFAULT_TOKEN_ENV))


def build_request(url: str, *, token: str = "", etag: str = "", last_modified: str = "") -> urllib.request.Request:
    """A GitHub API request with the standard headers, plus the ``Authorization``
    header when a token is given (so it counts against the 5000/h authed limit)."""
    request = urllib.request.Request(url)
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", ACCEPT)
    request.add_header("X-GitHub-Api-Version", API_VERSION)
    request.add_header("User-Agent", USER_AGENT)
    if etag:
        request.add_header("If-None-Match", etag)
    if last_modified:
        request.add_header("If-Modified-Since", last_modified)
    return request
