#!/usr/bin/env python3
"""Interactive setup wizard: prompts for the Forlabs session token (and a
couple of common optional overrides), then writes them straight into
the local TOML config file - no code or MCP host config editing
required.

Dependency-free by design: only the standard library, so it runs even
before `uv sync` has been done. The token is read with getpass (not
echoed to the terminal) and is written only to the local config file -
never printed, logged, or sent anywhere. Treat it exactly like a
password: it grants full account access for as long as it's valid
(measured at ~5 years for the underlying Laravel remember cookie).
"""

from __future__ import annotations

import getpass
import os
from pathlib import Path

DEFAULT_BASE_URL = "https://bki.forlabs.ru"
DEFAULT_TZ = "Asia/Irkutsk"
DEFAULT_CONFIG_FILE = "~/.config/forlabs-mcp/config.toml"

_TOKEN_INSTRUCTIONS = """
Чтобы получить session_token:
  1. Откройте https://bki.forlabs.ru/app в браузере и залогиньтесь как обычно.
  2. Откройте DevTools -> вкладку Application (Chrome) или Storage (Firefox).
  3. Слева найдите Cookies -> https://bki.forlabs.ru.
  4. Найдите cookie, чьё имя начинается с "remember_lm_" - скопируйте его Value.
     (Он не виден в обычной консоли через document.cookie - это нормально,
     он специально помечен HttpOnly. В списке cookie в DevTools он всё
     равно отображается.)
""".strip()


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

    print(_TOKEN_INSTRUCTIONS)
    print()
    session_token = getpass.getpass("session_token (remember_lm_... значение): ")
    base_url = prompt_optional("Base URL", DEFAULT_BASE_URL)
    timezone = prompt_optional("Часовой пояс", DEFAULT_TZ)

    settings = {
        "session_token": session_token,
        "base_url": base_url,
        "timezone": timezone,
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_toml(settings), encoding="utf-8")
    path.chmod(0o600)

    print(f"Готово: токен сохранён локально в {path} (права доступа 0600).")
    print("Ничего никуда не отправлено — это просто файл на вашем диске.")
    print(
        "Обращайтесь с этим файлом как с паролем: значение session_token "
        "даёт полный доступ к аккаунту на весь срок его жизни (~5 лет)."
    )
    print(
        "Другие настройки (session_path, max_items, timeout_seconds) можно "
        "добавить в этот файл вручную при необходимости."
    )


def main() -> None:
    run()


if __name__ == "__main__":
    main()
