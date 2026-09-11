# forlabs-mcp

Локальный сервер [MCP](https://modelcontextprotocol.io), который заходит в
SPA школьного дневника Forlabs/Lamotivo (`bki.forlabs.ru/app`) под учётной
записью студента и предоставляет четыре **только для чтения** tool'а —
`reference`, `schedule`, `grades`, `homework` — чтобы MCP-совместимый
ассистент мог отвечать на вопросы по реальному дневнику.

**Только чтение — это гарантировано архитектурой.** Каждый вызов к
backend'у проходит через единственный примитив, который перед любым
запросом проверяет захардкоженный allow-list из шести действий на чтение
— ничто в этом сервере не может писать, изменять или удалять данные в
Forlabs. Единственный файл, который сервер пишет локально — кеш
сессионных cookie (права доступа `0600`).

## Требования

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/)
- Учётная запись студента Forlabs/Lamotivo (логин/пароль, которые вы
  используете на `bki.forlabs.ru/app/login` — это не email)

## Установка

```bash
git clone https://github.com/Dest1n640/ForlabsMCP.git
cd forlabs-mcp
uv sync
```

После этого проверить, что всё встало корректно, можно так:

```bash
uv run pytest
```

Все тесты работают на синтетических фикстурах, без обращения к реальному
backend'у и без необходимости иметь настроенные креды.

## Конфигурация

Каждая настройка резолвится с таким приоритетом: **переменная окружения >
TOML-файл конфигурации > встроенное значение по умолчанию.**

| Настройка | Переменная окружения | По умолчанию | Обязательна |
|---|---|---|---|
| Логин | `FORLABS_USERNAME` | — | да |
| Пароль | `FORLABS_PASSWORD` | — | да |
| Base URL | `FORLABS_BASE_URL` | `https://bki.forlabs.ru` | нет |
| Таймаут (сек.) | `FORLABS_TIMEOUT_SECONDS` | `30` | нет |
| Часовой пояс | `FORLABS_TZ` | `Asia/Irkutsk` | нет |
| Путь к кешу сессии | `FORLABS_SESSION_PATH` | `~/.local/state/forlabs-mcp/session.json` | нет |
| Максимум элементов в списке | `FORLABS_MAX_ITEMS` | `200` | нет |

Проверка логина/пароля происходит до любого сетевого запроса — если их
нет ни в одном источнике, сервер сразу завершается с ошибкой конфигурации,
не пытаясь залогиниться.

### Вариант A: переменные окружения

Задайте `FORLABS_USERNAME` и `FORLABS_PASSWORD` (и любые опциональные
переопределения) в окружении, где запускается сервер. Именно под это
`scripts/print_mcp_config.py` (см. ниже) генерирует шаблон.

### Вариант Б: TOML-файл конфигурации

По умолчанию сервер ищет файл `~/.config/forlabs-mcp/config.toml`
(путь можно переопределить через `FORLABS_MCP_CONFIG`). Подходит как
таблица `[forlabs]`, так и просто плоская таблица верхнего уровня:

```toml
[forlabs]
username = "ваш.логин"
password = "ваш-пароль"
# base_url, timeout_seconds, timezone, session_path, max_items — все опциональны
```

## Регистрация в MCP-хосте

Любому MCP-хосту нужны одни и те же три вещи: **command**, его **args** и
переменные **env**. Сгенерировать этот объект можно так:

```bash
uv run python scripts/print_mcp_config.py
```

Это выведет (поля с кредами всегда плейсхолдеры — впишите свои
логин/пароль после того, как вставите результат). Для Claude Desktop и
Claude Code скрипт умеет сразу печатать готовую под них форму — см.
`--host claude-desktop` / `--host claude-code` ниже.

```json
{
  "command": "uv",
  "args": ["--directory", "<абсолютный-путь-к-этому-репозиторию>", "run", "forlabs-mcp"],
  "env": {
    "FORLABS_USERNAME": "your.login",
    "FORLABS_PASSWORD": "your-password"
  }
}
```

### Claude Desktop

```bash
uv run python scripts/print_mcp_config.py --host claude-desktop
```

Это сразу выведет готовый блок — просто вставьте его в
`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "forlabs": {
      "command": "uv",
      "args": ["--directory", "<абсолютный-путь-к-этому-репозиторию>", "run", "forlabs-mcp"],
      "env": {
        "FORLABS_USERNAME": "your.login",
        "FORLABS_PASSWORD": "your-password"
      }
    }
  }
}
```

### Claude Code

```bash
uv run python scripts/print_mcp_config.py --host claude-code
```

Это выведет уже готовую к запуску команду — скопируйте и выполните её
целиком:

```bash
claude mcp add-json forlabs '{"command":"uv","args":["--directory","<абсолютный-путь-к-этому-репозиторию>","run","forlabs-mcp"],"env":{"FORLABS_USERNAME":"your.login","FORLABS_PASSWORD":"your-password"}}'
```

### Hermes Agent

Те же три поля в виде YAML:

```yaml
forlabs:
  command: uv
  args: ["--directory", "<абсолютный-путь-к-этому-репозиторию>", "run", "forlabs-mcp"]
  env:
    FORLABS_USERNAME: your.login
    FORLABS_PASSWORD: your-password
```

### Любой другой MCP-клиент

Любой хост, принимающий определение сервера в форме command/args/env,
может использовать этот же сгенерированный объект напрямую — чтобы
поддержать новый, ещё не задокументированный клиент, менять сам проект
не нужно.

## Tool'ы

- **`reference(stream_id?)`** — плейсхолдер идентичности, id своего
  потока, все известные потоки, полная история обучения студента.
- **`schedule(date?, start?, end?)`** — занятия, размещённые на реальных
  календарных датах для заданного диапазона (по умолчанию — текущая
  неделя). `date` и `start`/`end` взаимоисключающие.
- **`grades(stream_id?, study_id?)`** — оценки, объединённые с названиями
  предметов и человекочитаемыми метками статуса.
- **`homework(stream_id?, study_id?, only_outstanding?)`** — домашние
  задания по всем предметам потока (или по одному предмету), опционально
  с фильтром только невыполненных.

## Тестирование

```bash
uv run pytest              # юнит-тесты на фикстурах, без обращения к сети
uv run ruff check .        # lint
uv run ruff format --check .  # проверка форматирования
```
