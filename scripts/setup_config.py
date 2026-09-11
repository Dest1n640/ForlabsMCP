#!/usr/bin/env python3
"""Interactive setup wizard: prompts for Forlabs credentials (and a
couple of common optional overrides), then writes them straight into
the local TOML config file - no code or MCP host config editing
required.

Dependency-free by design: only the standard library, so it runs even
before `uv sync` has been done. The password is read with getpass (not
echoed to the terminal) and is written only to the local config file -
never printed, logged, or sent anywhere.
"""

from __future__ import annotations

import getpass
import os
from pathlib import Path

DEFAULT_BASE_URL = "https://bki.forlabs.ru"
DEFAULT_TZ = "Asia/Irkutsk"
DEFAULT_CONFIG_FILE = "~/.config/forlabs-mcp/config.toml"


def config_file_path() -> Path:
    override = os.environ.get("FORLABS_MCP_CONFIG")
    if override:
        return Path(override).expanduser()
    return Path(DEFAULT_CONFIG_FILE).expanduser()


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def render_toml(settings: dict[str, str]) -> str:
    lines = ["[forlabs]"]
    for key, value in settings.items():
        lines.append(f'{key} = "{_toml_escape(value)}"')
    return "\n".join(lines) + "\n"


def prompt_optional(label: str, default: str) -> str:
    raw = input(f"{label} [{default}]: ").strip()
    return raw if raw else default


def confirm_overwrite(path: Path) -> bool:
    answer = input(f"Файл {path} уже существует. Перезаписать? [y/N]: ").strip().lower()
    return answer in ("y", "yes", "д", "да")


def run() -> None:
    path = config_file_path()
    if path.is_file() and not confirm_overwrite(path):
        print("Отменено, файл не изменён.")
        return

    username = input("Логин Forlabs: ").strip()
    password = getpass.getpass("Пароль Forlabs: ")
    base_url = prompt_optional("Base URL", DEFAULT_BASE_URL)
    timezone = prompt_optional("Часовой пояс", DEFAULT_TZ)

    settings = {
        "username": username,
        "password": password,
        "base_url": base_url,
        "timezone": timezone,
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_toml(settings), encoding="utf-8")
    path.chmod(0o600)

    print(f"Готово: креды сохранены локально в {path} (права доступа 0600).")
    print("Ничего никуда не отправлено — это просто файл на вашем диске.")
    print(
        "Другие настройки (session_path, max_items, timeout_seconds) можно "
        "добавить в этот файл вручную при необходимости."
    )


def main() -> None:
    run()


if __name__ == "__main__":
    main()
