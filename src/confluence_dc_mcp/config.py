from __future__ import annotations

import os
from dataclasses import dataclass
from typing import NoReturn
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class ConfluenceConfig:
    base_url: str
    pat: str | None
    username: str | None
    password: str | None
    verify_ssl: bool
    timeout_seconds: float

    @property
    def has_pat_auth(self) -> bool:
        return self.pat is not None

    @property
    def has_basic_auth(self) -> bool:
        return self.username is not None and self.password is not None


def load_config() -> ConfluenceConfig:
    base_url = _required_env("CONFLUENCE_BASE_URL").rstrip("/")
    _validate_http_url(base_url, "CONFLUENCE_BASE_URL")

    config = ConfluenceConfig(
        base_url=base_url,
        pat=_optional_env("CONFLUENCE_PAT"),
        username=_optional_env("CONFLUENCE_USERNAME"),
        password=_optional_env("CONFLUENCE_PASSWORD"),
        verify_ssl=_parse_bool(os.getenv("CONFLUENCE_VERIFY_SSL", "true")),
        timeout_seconds=_parse_float(os.getenv("CONFLUENCE_TIMEOUT_SECONDS", "30")),
    )

    if not config.has_pat_auth and not config.has_basic_auth:
        _die(
            "Configure either CONFLUENCE_PAT or both "
            "CONFLUENCE_USERNAME and CONFLUENCE_PASSWORD."
        )

    return config


def _optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _required_env(name: str) -> str:
    value = _optional_env(name)
    if value is None:
        _die(f"Missing required environment variable: {name}")
    return value


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    _die(f"Expected boolean value, got: {value!r}")


def _parse_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError:
        _die(f"Expected numeric timeout value, got: {value!r}")

    if parsed <= 0:
        _die("CONFLUENCE_TIMEOUT_SECONDS must be greater than zero.")
    return parsed


def _validate_http_url(value: str, name: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        _die(f"{name} must be an absolute http(s) URL.")


def _die(message: str) -> NoReturn:
    raise RuntimeError(message)

