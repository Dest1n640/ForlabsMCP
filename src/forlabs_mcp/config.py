"""Layered, validated configuration for the Forlabs client.

Precedence: environment variable > repo-local JSON token file > built-in default.
See PROJECT-REFERENCE.md §7.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .errors import ConfigError

DEFAULT_BASE_URL = "https://bki.forlabs.ru"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_TZ = "Asia/Irkutsk"
DEFAULT_SESSION_PATH = "~/.local/state/forlabs-mcp/session.json"
DEFAULT_MAX_ITEMS = 200

_ENV_SESSION_TOKEN = "FORLABS_SESSION_TOKEN"
_ENV_BASE_URL = "FORLABS_BASE_URL"
_ENV_TIMEOUT_SECONDS = "FORLABS_TIMEOUT_SECONDS"
_ENV_TZ = "FORLABS_TZ"
_ENV_SESSION_PATH = "FORLABS_SESSION_PATH"
_ENV_MAX_ITEMS = "FORLABS_MAX_ITEMS"
_ENV_TOKEN_FILE = "FORLABS_TOKEN_FILE"

# Repo root, resolved from the package location so it does not depend on
# the working directory the MCP host starts the server in.
_DEFAULT_TOKEN_FILE = Path(__file__).resolve().parents[2] / "forlabs-session.json"

# Value shipped in forlabs-session.example.json; a copied-but-unedited
# template must read as "token missing", not as a real token.
TOKEN_PLACEHOLDER = "PASTE_YOUR_remember_lm_COOKIE_VALUE_HERE"


@dataclass(frozen=True)
class ForlabsConfig:
    session_token: str
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    timezone: str = DEFAULT_TZ
    session_path: Path = Path(DEFAULT_SESSION_PATH).expanduser()
    max_items: int = DEFAULT_MAX_ITEMS

    def redacted(self) -> dict[str, object]:
        """Return this config as a dict safe to log: the session token is masked."""
        return {
            "session_token": "***",
            "base_url": self.base_url,
            "timeout_seconds": self.timeout_seconds,
            "timezone": self.timezone,
            "session_path": str(self.session_path),
            "max_items": self.max_items,
        }


def _token_file_path() -> Path:
    override = os.environ.get(_ENV_TOKEN_FILE)
    if override:
        return Path(override).expanduser()
    return _DEFAULT_TOKEN_FILE


def _load_json_table(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        # Never echo the file's contents: it holds the session token.
        raise ConfigError(
            f"Token file {path.name} is unreadable or not valid JSON.", key="session_token"
        ) from exc
    if not isinstance(data, dict):
        raise ConfigError(
            f"Token file {path.name} must contain a JSON object.", key="session_token"
        )
    return data


def load_config() -> ForlabsConfig:
    """Resolve a ForlabsConfig: env var > JSON token file > built-in default.

    Raises ConfigError if session_token is missing from every source,
    before any network call is made.
    """
    file_table = _load_json_table(_token_file_path())

    def resolve(key: str, env_var: str, default: object) -> object:
        env_value = os.environ.get(env_var)
        if env_value:
            return env_value
        if key in file_table:
            return file_table[key]
        return default

    session_token = resolve("session_token", _ENV_SESSION_TOKEN, None)
    if not session_token or session_token == TOKEN_PLACEHOLDER:
        raise ConfigError("Missing required setting: session_token.", key="session_token")

    base_url = str(resolve("base_url", _ENV_BASE_URL, DEFAULT_BASE_URL))
    timeout_seconds = float(
        resolve("timeout_seconds", _ENV_TIMEOUT_SECONDS, DEFAULT_TIMEOUT_SECONDS)
    )
    timezone = str(resolve("timezone", _ENV_TZ, DEFAULT_TZ))
    session_path = Path(
        str(resolve("session_path", _ENV_SESSION_PATH, DEFAULT_SESSION_PATH))
    ).expanduser()
    max_items = int(resolve("max_items", _ENV_MAX_ITEMS, DEFAULT_MAX_ITEMS))

    return ForlabsConfig(
        session_token=str(session_token),
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        timezone=timezone,
        session_path=session_path,
        max_items=max_items,
    )
