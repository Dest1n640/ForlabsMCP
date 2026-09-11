"""Layered, validated configuration for the Forlabs client.

Precedence: environment variable > TOML config file > built-in default.
See PROJECT-REFERENCE.md §7.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .errors import ConfigError

DEFAULT_BASE_URL = "https://bki.forlabs.ru"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_TZ = "Asia/Irkutsk"
DEFAULT_SESSION_PATH = "~/.local/state/forlabs-mcp/session.json"
DEFAULT_MAX_ITEMS = 200

_ENV_USERNAME = "FORLABS_USERNAME"
_ENV_PASSWORD = "FORLABS_PASSWORD"
_ENV_BASE_URL = "FORLABS_BASE_URL"
_ENV_TIMEOUT_SECONDS = "FORLABS_TIMEOUT_SECONDS"
_ENV_TZ = "FORLABS_TZ"
_ENV_SESSION_PATH = "FORLABS_SESSION_PATH"
_ENV_MAX_ITEMS = "FORLABS_MAX_ITEMS"
_ENV_CONFIG_FILE = "FORLABS_MCP_CONFIG"

_DEFAULT_CONFIG_FILE = "~/.config/forlabs-mcp/config.toml"


@dataclass(frozen=True)
class ForlabsConfig:
    username: str
    password: str
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    timezone: str = DEFAULT_TZ
    session_path: Path = Path(DEFAULT_SESSION_PATH).expanduser()
    max_items: int = DEFAULT_MAX_ITEMS

    def redacted(self) -> dict[str, object]:
        """Return this config as a dict safe to log: the password is masked."""
        return {
            "username": self.username,
            "password": "***",
            "base_url": self.base_url,
            "timeout_seconds": self.timeout_seconds,
            "timezone": self.timezone,
            "session_path": str(self.session_path),
            "max_items": self.max_items,
        }


def _config_file_path() -> Path:
    override = os.environ.get(_ENV_CONFIG_FILE)
    if override:
        return Path(override).expanduser()
    return Path(_DEFAULT_CONFIG_FILE).expanduser()


def _load_toml_table(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    table = data.get("forlabs", data)
    return table if isinstance(table, dict) else {}


def load_config() -> ForlabsConfig:
    """Resolve a ForlabsConfig: env var > TOML file > built-in default.

    Raises ConfigError if username/password are missing from every source,
    before any network call is made.
    """
    toml_table = _load_toml_table(_config_file_path())

    def resolve(key: str, env_var: str, default: object) -> object:
        env_value = os.environ.get(env_var)
        if env_value:
            return env_value
        if key in toml_table:
            return toml_table[key]
        return default

    username = resolve("username", _ENV_USERNAME, None)
    password = resolve("password", _ENV_PASSWORD, None)
    if not username:
        raise ConfigError("Missing required setting: username.", key="username")
    if not password:
        raise ConfigError("Missing required setting: password.", key="password")

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
        username=str(username),
        password=str(password),
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        timezone=timezone,
        session_path=session_path,
        max_items=max_items,
    )
