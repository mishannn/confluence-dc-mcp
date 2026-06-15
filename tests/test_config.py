from __future__ import annotations

import pytest

from confluence_dc_mcp.config import load_config


def test_load_config_with_pat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFLUENCE_BASE_URL", "https://confluence.example.com/")
    monkeypatch.setenv("CONFLUENCE_PAT", " token ")
    monkeypatch.setenv("CONFLUENCE_VERIFY_SSL", "false")
    monkeypatch.setenv("CONFLUENCE_TIMEOUT_SECONDS", "12.5")
    monkeypatch.delenv("CONFLUENCE_USERNAME", raising=False)
    monkeypatch.delenv("CONFLUENCE_PASSWORD", raising=False)

    config = load_config()

    assert config.base_url == "https://confluence.example.com"
    assert config.pat == "token"
    assert config.username is None
    assert config.password is None
    assert config.verify_ssl is False
    assert config.timeout_seconds == 12.5


def test_load_config_requires_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFLUENCE_BASE_URL", "https://confluence.example.com")
    monkeypatch.delenv("CONFLUENCE_PAT", raising=False)
    monkeypatch.delenv("CONFLUENCE_USERNAME", raising=False)
    monkeypatch.delenv("CONFLUENCE_PASSWORD", raising=False)

    with pytest.raises(RuntimeError, match="Configure either CONFLUENCE_PAT"):
        load_config()


def test_load_config_rejects_invalid_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFLUENCE_BASE_URL", "confluence.example.com")
    monkeypatch.setenv("CONFLUENCE_PAT", "token")

    with pytest.raises(RuntimeError, match="absolute http"):
        load_config()

