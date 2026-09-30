# forlabs-mcp — full project reference

Single-file reference for rebuilding this project from scratch without
recapturing anything. Everything quoted here (JSON payloads, field names,
endpoint paths) is either non-sensitive protocol detail or already-synthetic
fixture data — safe to reuse in a fresh repo under any account.

## 1. What this is

A local [MCP](https://modelcontextprotocol.io) server (`forlabs-mcp`) that logs
into the Forlabs/Lamotivo school-diary SPA at `https://bki.forlabs.ru/app` as a
student, and exposes four **read-only** tools — `reference`, `schedule`,
`grades`, `homework` — so an MCP-capable assistant can answer questions against
a real diary. Nothing is ever written back to Forlabs; the only file the
server writes locally is a session-cookie cache (mode `0600`).

## 2. Forlabs (Lamotivo) protocol

### 2.1 Transport

- **App**: AngularJS 1.x SPA ("Lamotivo", `ng-app="lmApp"`) at `/app`;
  unauthenticated requests 302-redirect to `/app/login`.
- **Backend**: Laravel. The page carries `<meta name="csrf-token">`; responses
  set an `XSRF-TOKEN` cookie (Laravel's Angular-friendly CSRF cookie).
  AngularJS `$http` echoes that cookie value back in the **`X-XSRF-TOKEN`**
  request header — the client must do the same.
- **Session**: cookie-based. A browser establishes it via the login form; this
  client instead seeds a long-lived remember cookie (§2.2a) and lets the
  backend renew the short session cookie **`forlabs_session`** itself.

### 2.2 Login flow (confirmed from a captured request) — historical, not used by this client

```
POST https://bki.forlabs.ru/app/login
Content-Type: application/json;charset=UTF-8
Accept: application/json, text/plain, */*
Origin: https://bki.forlabs.ru
Referer: https://bki.forlabs.ru/app/login
X-XSRF-TOKEN: <XSRF-TOKEN cookie value, URL-decoded (%3D -> =)>
Cookie: XSRF-TOKEN=…; forlabs_session=…

{ "username": "<login>", "password": "<password>", "remember": true }
```

- The `X-XSRF-TOKEN` header carries the **URL-decoded** `XSRF-TOKEN` cookie
  value (only `=` is percent-encoded in the cookie) — `unquote()` it.
- Bad credentials come back as `422 {"errors": {"username": ["Неверный логин или пароль"]}}`.
- "username" is the login string shown in the form's «Логин» field, not an
  email.
- First hit `GET /app/login` once to prime the `XSRF-TOKEN` cookie (Laravel
  sets it on any GET in the web middleware group) before posting.
- **This POST is documented for completeness only — `forlabs-mcp` never
  submits it.** The client authenticates by seeding a pre-existing
  long-lived cookie instead (§2.2a); this flow is how a real browser login
  originally obtains that cookie.

### 2.2a Cookie lifetimes and remember-me auth (confirmed live, this is what the client actually uses)

A real login was captured and its resulting cookies inspected directly
(not just read from a request log):

| Cookie | Domain | Measured lifetime |
|---|---|---|
| `XSRF-TOKEN` | `bki.forlabs.ru` | ~2.4 hours |
| `forlabs_session` | `bki.forlabs.ru` | ~2.4 hours |
| `remember_lm_<hash>` | `bki.forlabs.ru` | ~5 years (~1825 days) |

The `<hash>` suffix is a Laravel `Auth::viaRemember()` guard identifier
fixed by this application's own configuration — the same for every account
on this deployment, not derived per user. `forlabs-mcp` hardcodes the full
observed cookie name as `REMEMBER_COOKIE_NAME` in `client/session.py`.

A follow-up live test confirmed the mechanism `forlabs-mcp` relies on: a
request carrying **only** `remember_lm_<hash>` (no `forlabs_session`, just
a freshly primed `XSRF-TOKEN` from `GET /app/login`) against
`POST /lm-vendor/repositories/sched/get_schedule` returned `200` with real
data, and the response's `Set-Cookie` headers minted a fresh
`forlabs_session`. This is standard Laravel remember-me behavior operating
transparently on an ordinary authenticated request — no special keep-alive
call, endpoint, or timing is needed to trigger it.

**Practical consequence**: the user obtains the `remember_lm_<hash>` value
once from their own browser (DevTools → Application/Storage → Cookies →
`bki.forlabs.ru` — it is `HttpOnly` so it never appears via
`document.cookie`, but DevTools' cookie list shows it regardless) and
configures it as `session_token` (see §7). `forlabs-mcp` seeds it into its
cookie jar at startup and never submits a username or password anywhere.
Ordinary data calls renew the short-lived `forlabs_session`/`XSRF-TOKEN`
pair as a side effect. If a call ever comes back `401`/`419` it means the
`remember_lm_<hash>` value itself was rejected (not just the short
session) — treat this as a rare, ~5-year-horizon event requiring a fresh
value from the browser, not a routine retry.

A leaked `remember_lm_<hash>` value grants the same practical account
access as a leaked password, for its full measured lifetime — it is not
inherently safer to store, it just means this client itself never
transmits or holds the raw password.

### 2.3 Repository RPC envelope

Every data call, after login, has this exact shape:

```
POST https://bki.forlabs.ru/lm-vendor/repositories/<module>/<action>
Content-Type: application/json
X-XSRF-TOKEN: <decoded XSRF-TOKEN cookie value>
Accept: application/json

<JSON object of parameters, or {} when none>
```

Response: `200 OK`, `application/json`, gzip. The success body is the payload
**directly** — no `{status, data}` wrapper. Each action has its own top-level
shape. A Laravel error can come back as `200 {"message": "..."}` (no other
keys) or a non-2xx status; treat both as an application error.

### 2.4 Read-only allow-list

These are the only `(module, action)` pairs a read-only client should ever
call for the student role — reject everything else *before* any HTTP request:

```
sched/get_grid
sched/get_schedule
learning/get_streams
learning/get_studies
learning/get_scores
learning/get_tasks
```

`learning/get_streams` is on the allow-list (observed in traffic) but the
current client never actually calls it — the account's own stream and the
full stream list are already present in `sched/get_schedule`'s response
(`meta.stream_ids`, `streams[]`), so a separate call is redundant for the
current tool set.

Write actions on other Lamotivo modules (`assignments/post_comment`,
`assignments/post_assessment`, `study_students/save_attendance`, …) must never
be added to this list.

## 3. Full request/response JSON per endpoint

All payloads below are the **synthetic** fixtures used in this project's test
suite (`tests/fixtures/*.json`) — shaped exactly like real captured traffic,
with all names/titles replaced by fictional ones. Reuse them directly to bring
up parsers/tests in a fresh project with zero live capture needed.

### `sched/get_grid`

Request body: `{}`

```json
{
  "grid": {
    "days": {
      "mon": { "name": "Понедельник", "active": true },
      "tue": { "name": "Вторник", "active": true },
      "wed": { "name": "Среда", "active": true },
      "thu": { "name": "Четверг", "active": true },
      "fri": { "name": "Пятница", "active": true },
      "sat": { "name": "Суббота", "active": true },
      "sun": { "name": "Воскресенье", "active": false }
    },
    "positions": [
      { "start": "08:30", "end": "10:00" },
      { "start": "10:10", "end": "11:40" },
      { "start": "11:50", "end": "13:20" },
      { "start": "13:50", "end": "15:20" },
      { "start": "15:30", "end": "17:00" },
      { "start": "17:10", "end": "18:40" },
      { "start": "18:50", "end": "20:20" }
    ],
    "lesson_name": "пара",
    "type": 2,
    "upperweek": 2
  }
}
```

`positions` is 0-indexed by `position - 1`. `upperweek` is the number of
alternating week layouts (2 = a two-week rotating schedule).

### `sched/get_schedule`

Request body: `{}` (the SPA passes no explicit `stream_id`; `{}` returns the
account's own stream).

```json
{
  "meta": { "type": "stream", "is_own": true, "stream_ids": [205] },
  "streams": [
    { "id": 199, "name": "14321-ДБ (ПИ)" },
    { "id": 200, "name": "14322-ДБ (ПИ)" },
    { "id": 205, "name": "14323-ДБ (ПИ)" },
    { "id": 206, "name": "14324-ДБ (ПИ)" }
  ],
  "entries": [
    {
      "day": 1,
      "position": 2,
      "type": 1,
      "room_name": "ауд. 149",
      "lecturer_name": "Кравцова Наталья Игоревна",
      "study_id": 11590,
      "study_name": "Экономическая теория",
      "subgroup": "",
      "streams": [{ "id": 205, "name": "14323-ДБ (ПИ)" }]
    },
    {
      "day": 1,
      "position": 3,
      "type": 1,
      "room_name": "НБУ 303",
      "lecturer_name": "Тихонов Максим Олегович",
      "study_id": 11589,
      "study_name": "Интеллектуальные системы и анализ больших данных",
      "subgroup": "",
      "streams": [{ "id": 205, "name": "14323-ДБ (ПИ)" }]
    },
    {
      "day": 2,
      "position": 2,
      "type": 2,
      "room_name": "НБУ 303",
      "lecturer_name": "Голубев Артём Николаевич",
      "study_id": 11593,
      "study_name": "Архитектура вычислительных комплексов",
      "subgroup": "",
      "streams": [{ "id": 205, "name": "14323-ДБ (ПИ)" }]
    },
    {
      "day": 4,
      "position": 4,
      "type": 2,
      "room_name": "Онлайн",
      "lecturer_name": "Ковалёва Т. А.",
      "study_id": 11596,
      "study_name": "Отечественная история",
      "subgroup": "",
      "streams": [{ "id": 205, "name": "14323-ДБ (ПИ)" }]
    },
    {
      "day": 8,
      "position": 2,
      "type": 2,
      "room_name": "НБУ 104",
      "lecturer_name": "Тихонов Максим Олегович",
      "study_id": 11589,
      "study_name": "Интеллектуальные системы и анализ больших данных",
      "subgroup": "",
      "streams": [{ "id": 205, "name": "14323-ДБ (ПИ)" }]
    },
    {
      "day": 12,
      "position": 1,
      "type": 2,
      "room_name": "НБУ 110",
      "lecturer_name": "Семёнов Владимир Игоревич",
      "study_id": 11597,
      "study_name": "Формальные языки и трансляции",
      "subgroup": "",
      "streams": [{ "id": 205, "name": "14323-ДБ (ПИ)" }]
    }
  ]
}
```

Key derivation rules (see `dates.py`):

- `day` is 1..14: `weekday = (day - 1) % 7` (0 = Monday), `week_index = (day - 1) // 7` (0 or 1).
- Start/end clock time = `grid.positions[position - 1]`.
- Which calendar week is "week 0" vs "week 1" is **not** stated by the
  backend. This project assumes `(ISO week number - 1) % week_variants` and
  states that assumption in every schedule result — treat as provisional.
- `type` (lesson kind, 1 vs 2 seen) has no confirmed label map — pass the raw
  int through.

### `learning/get_scores`

Request body: `{ "stream_id": 205 }`

```json
{
  "scores": {
    "8919": { "study_id": 8919, "credits": 1, "status": 1, "grade": 0 },
    "8975": { "study_id": 8975, "credits": 93.56, "status": 5, "grade": 0 },
    "8983": { "study_id": 8983, "credits": 76.98, "status": 2, "grade": 0 },
    "8982": { "study_id": 8982, "credits": 100.9, "status": 5, "grade": 0 },
    "9480": { "study_id": 9480, "credits": 60, "status": 1, "grade": 0 },
    "9952": { "study_id": 9952, "credits": 100, "status": 5, "grade": 0 },
    "10412": { "study_id": 10412, "credits": 119.08, "status": 5, "grade": 0 },
    "11616": { "study_id": 11616, "credits": 1.2, "status": 1, "grade": 0 },
    "11584": { "study_id": 11584, "credits": 0.3, "status": 1, "grade": 0 }
  }
}
```

- Map keyed by `study_id` (string key == the numeric `.study_id` inside).
- `credits`: float — cumulative БРС rating points (~0–120+), not a 5-point mark.
- `status`: int, values 1/2/5 observed. Cross-referenced with
  `learning/get_studies`'s own `status` (2 = current semester, 3 = past):
  score `status` 1/2 land on current studies, 5 on past (completed). This
  project's label map: `{1: "in progress", 2: "in progress", 5: "completed"}`
  — provisional for any other value.
- `grade`: int, `0` throughout the sample; presumably the final 5-point grade
  once assigned.
- Join `study_id` → display name via `learning/get_studies`; an unresolved id
  keeps the numeric id plus a "name not found" note rather than failing.

### `learning/get_studies`

Request body: `{ "stream_id": 205 }`

```json
{
  "studies": [
    {
      "id": 11584,
      "stream_id": null,
      "subject_id": null,
      "course_id": 5,
      "semester": 305,
      "curr_year": 3,
      "curr_sem": 5,
      "status": 2,
      "verbose_name": "Технологии интерактивных медиасистем",
      "short_name": null,
      "type": 1,
      "year_id": 20,
      "year_name": "2026/2027",
      "session": 1,
      "lecturers": [
        { "id": 45, "department_id": 5, "verbose_name": "Орлов Пётр Андреевич", "title": "старший преподаватель", "role": 1 }
      ],
      "lecturers_count": 1,
      "posts_count": 0,
      "chapters_count": 0,
      "tasks_count": 1,
      "exams_count": 0,
      "attendance_count": 1
    },
    {
      "id": 11590,
      "stream_id": null,
      "subject_id": null,
      "course_id": 360,
      "semester": 305,
      "curr_year": 3,
      "curr_sem": 5,
      "status": 2,
      "verbose_name": "Экономическая теория",
      "short_name": null,
      "type": 1,
      "year_id": 20,
      "year_name": "2026/2027",
      "session": 1,
      "lecturers": [
        { "id": 38, "department_id": 4, "verbose_name": "Кравцова Наталья Игоревна", "title": "к.т.н., доцент", "role": 1 }
      ],
      "lecturers_count": 1,
      "posts_count": 0,
      "chapters_count": 0,
      "tasks_count": 0,
      "exams_count": 0,
      "attendance_count": 0
    },
    {
      "id": 10823,
      "stream_id": null,
      "subject_id": null,
      "course_id": 3,
      "semester": 204,
      "curr_year": 2,
      "curr_sem": 4,
      "status": 3,
      "verbose_name": "Управление базами данных",
      "short_name": null,
      "type": 1,
      "year_id": 19,
      "year_name": "2025/2026",
      "session": 2,
      "lecturers": [
        { "id": 45, "department_id": 5, "verbose_name": "Орлов Пётр Андреевич", "title": "старший преподаватель", "role": 1 }
      ],
      "lecturers_count": 1,
      "posts_count": 0,
      "chapters_count": 13,
      "tasks_count": 12,
      "exams_count": 6,
      "attendance_count": 26
    },
    {
      "id": 8975,
      "stream_id": null,
      "subject_id": null,
      "course_id": 940,
      "semester": 101,
      "curr_year": 1,
      "curr_sem": 1,
      "status": 3,
      "verbose_name": "Основы государственного управления",
      "short_name": null,
      "type": 1,
      "year_id": 18,
      "year_name": "2024/2025",
      "session": 1,
      "lecturers": [
        { "id": 3, "department_id": 1, "verbose_name": "Фомина Ольга Викторовна", "title": "", "role": 1 }
      ],
      "lecturers_count": 1,
      "posts_count": 0,
      "chapters_count": 4,
      "tasks_count": 2,
      "exams_count": 1,
      "attendance_count": 5
    }
  ]
}
```

- Returns the **whole enrolment history** (current + all past semesters),
  newest first. `status`: 2 = current semester, 3 = past.
- `exams_count > 0` on past studies confirms an exams surface exists in the
  data model even though no `study_exams` endpoint is called for students.
- `chapters_count` / `attendance_count` > 0 confirm the two backlog endpoints
  in §11 (`get_chapters`, `get_attendance`) have real data behind them.

### `learning/get_tasks`

Request body: `{ "stream_id": "205", "study_id": "10823" }` — **both values
are strings**, not integers, unlike every other endpoint's `stream_id`.

```json
{
  "tasks": [
    {
      "id": 5,
      "name": "Создание отчёта по таблице",
      "content": "<p>Подготовительный этап: установите MySQL, импортируйте customers.sql, составьте запросы.</p>",
      "type": 1,
      "course_id": 3,
      "chapter_id": 3,
      "chapter_title": "Запросы на выборку данных",
      "chapter_has_content": true,
      "level": 10,
      "files": [
        {
          "id": 6677,
          "type": "text",
          "filename": "customers.sql",
          "mime_type": "text/plain",
          "size": 22181,
          "url": "https://bki.matecdn.ru/-/a1b2c3d4-1111-2222-3333-444455556666/customers.sql",
          "human_size": "21,66 КБ"
        }
      ],
      "pivot_status": 3,
      "pivot_cost": 2,
      "pivot_sort": 1,
      "pivot_type": 1,
      "pivot_start_at": null,
      "pivot_end_at": "2026-03-02T16:00:00.000000Z",
      "pivot_description": null
    },
    {
      "id": 251,
      "name": "Форматы хранения данных",
      "content": "<ol><li>Составьте список песен, фильмов, книг.</li></ol>",
      "type": 1,
      "course_id": 3,
      "chapter_id": 2,
      "chapter_title": "Управление таблицами и форматами данных",
      "chapter_has_content": true,
      "level": 10,
      "files": [],
      "pivot_status": 3,
      "pivot_cost": 2,
      "pivot_sort": 2,
      "pivot_type": 1,
      "pivot_start_at": null,
      "pivot_end_at": "2026-03-11T16:00:00.000000Z",
      "pivot_description": null
    },
    {
      "id": 41,
      "name": "Курсовой проект по БД",
      "content": "<p>Выберите тематику и спроектируйте базу данных.</p>",
      "type": 1,
      "course_id": 3,
      "chapter_id": null,
      "chapter_title": null,
      "chapter_has_content": false,
      "level": 10,
      "files": [],
      "pivot_status": 3,
      "pivot_cost": 10,
      "pivot_sort": 12,
      "pivot_type": 1,
      "pivot_start_at": null,
      "pivot_end_at": null,
      "pivot_description": null
    }
  ],
  "assignments": [
    {
      "id": 940203,
      "task_id": 5,
      "status": 3,
      "choice": null,
      "variant": null,
      "options": null,
      "last_replied_at": "2026-02-18 11:02:38",
      "assessment_credits": 2,
      "assessment_date": "2026-03-12",
      "assessment_lecturer_id": 45,
      "responses_count": 1
    },
    {
      "id": 947033,
      "task_id": 251,
      "status": 3,
      "choice": null,
      "variant": null,
      "options": null,
      "last_replied_at": "2026-03-02 22:19:21",
      "assessment_credits": 2,
      "assessment_date": "2026-03-12",
      "assessment_lecturer_id": 45,
      "responses_count": 1
    },
    {
      "id": 987307,
      "task_id": 41,
      "status": 3,
      "choice": null,
      "variant": null,
      "options": null,
      "last_replied_at": "2026-06-07 16:53:59",
      "assessment_credits": 9,
      "assessment_date": "2026-06-10",
      "assessment_lecturer_id": 45,
      "responses_count": 2
    }
  ]
}
```

- Called **per study** — a "homework across the whole stream" tool must loop
  `learning/get_studies` and call this once per study id.
- `tasks[].id` joins to `assignments[].task_id`. A task absent from
  `assignments[]` = not started.
- `assignment.status` — only `3` (submitted & assessed) has ever been
  observed; other values are unconfirmed.
- `pivot_cost` = max points for the task; `pivot_end_at` = due date (ISO
  8601, nullable).

## 4. Architecture

```
+-----------------------------------------------------------------+
|  server.py            MCPServer("forlabs"), stdio transport      |
|    - loads ForlabsConfig via config.load_config()                |
|    - builds one lazily-created ForlabsClient (client_factory)     |
+------------------------------+-----------------------------------+
                                |
+------------------------------v-----------------------------------+
|  tools/register.py    4 MCP tools: reference, grades, homework,   |
|                        schedule. Each: validate args -> call      |
|                        client -> catch ForlabsError -> ToolError  |
+------------------------------+-----------------------------------+
                                |
+------------------------------v-----------------------------------+
|  client/client.py     ForlabsClient (domain layer): joins studies |
|                        to scores/tasks, resolves "own stream",    |
|                        returns Reference / ScoreRow / HomeworkRow |
+------------------------------+-----------------------------------+
                                |
        +-----------------------+------------------------+
        |                                                |
+-------v---------+                            +---------v----------+
| dates.py         |                            | client/parsers.py   |
| resolve_range,    |                            | payload -> typed    |
| resolve_lessons   |<---------------------------| models + warnings   |
| (calendar math)   |    client/models.py         | (PartialResult)     |
+-------------------+    (pydantic, extra=ignore) +---------+----------+
                                                             |
                                                  +----------v----------+
                                                  | client/repository.py |
                                                  | allow-listed RPC:     |
                                                  | POST .../<module>/    |
                                                  | <action>              |
                                                  +----------+-----------+
                                                             |
                                                  +----------v-----------+
                                                  | client/session.py     |
                                                  | httpx.Client, remember |
                                                  | cookie, XSRF header,   |
                                                  | cookie                 |
                                                  | persistence (0600)     |
                                                  +----------+-----------+
                                                             |
                                                  https://bki.forlabs.ru
```

Module responsibilities:

| Module | Responsibility |
|---|---|
| `config.py` | `ForlabsConfig` dataclass + `load_config()`. Precedence: env var > repo-local JSON token file > default. Validates and never lets a bad value reach the network layer. `redacted()` for safe logging. |
| `client/session.py` | `ForlabsSession`: one `httpx.Client` seeded with the remember cookie, XSRF header derivation, `AuthError` on a rejected token (no re-auth), cookie jar persisted to `session_path` (mode `0600`). |
| `client/repository.py` | `Repository.call(module, action, params)`: the one RPC primitive. Raises `ProgrammingError` for anything off `READ_ONLY_ACTIONS` **before** any request; raises `UpstreamError` for non-2xx or an in-body error shape. |
| `client/models.py` | Pydantic models (`extra="ignore"`) for `Stream`, `Study`, `ScheduleGrid`, `Lesson`, `Score`, `Task`, `TaskFile`, `Assignment`, `Identity`. |
| `client/parsers.py` | Tolerant `payload -> model` functions; a bad row becomes a warning string, never an exception that loses the rest of the response. |
| `client/partial.py` | `PartialResult[T]` — `data` + `warnings` + `is_partial`. The vocabulary every layer above uses to say "here's what I got, and here's what's incomplete." |
| `client/client.py` | `ForlabsClient` — the only class the tools call. `reference()`, `scores()`, `schedule_raw()`, `homework()`. Discovers "own stream" from `sched/get_schedule`'s `meta.stream_ids`. Joins study ids to names. |
| `dates.py` | `resolve_range()` (YYYY-MM-DD parsing + inclusive ranges + ISO-week default), `resolve_lessons()` (places abstract `day`/`position` lessons onto real calendar dates using the grid + a stated week-parity assumption). |
| `tools/register.py` | Registers the 4 tools on the `MCPServer`, shapes their JSON output, converts `ForlabsError` to a classified, credential-free `ToolError`. |
| `server.py` | CLI entry point (`forlabs-mcp`), builds the server + a lazy client factory, runs stdio transport. |
| `errors.py` | The `ForlabsError` taxonomy + `to_tool_error()` (see §8). |

## 5. Backend key → model field mapping

| Endpoint | Backend key | Model field |
|---|---|---|
| `learning/get_studies` | `verbose_name` | `Study.name` |
| | `curr_year` | `Study.study_year` |
| | `curr_sem` | `Study.semester` |
| | `status == 2` | `Study.is_current` |
| | `lecturers[].verbose_name` | `Study.teachers[]` |
| `sched/get_schedule` | `type` | `Lesson.kind` |
| `sched/get_grid` | `upperweek` | `ScheduleGrid.week_variants` |
| | `days.<key>.active` | `ScheduleGrid.active_weekdays` (list of ints, 0=Mon) |
| `learning/get_tasks` | `content` | `Task.description_html` |
| | `pivot_end_at` | `Task.due_at` |
| | `pivot_cost` | `Task.max_credits` |
| | `assessment_credits` | `Assignment.credits` |
| | `assessment_date` | `Assignment.assessed_at` |

Every model uses `extra="ignore"` — a new backend field never breaks parsing.

## 6. The 4 MCP tools — exact contracts

(Condensed from `openspec/specs/forlabs-diary-tools/spec.md` — see that file
for the full normative SHALL/scenario text if resuming inside OpenSpec.)

### `reference(stream_id?: int)`

Returns: `identity {name, role}`, `own_stream_id`, `streams[] {id, name,
is_own}`, `studies[] {id, name, teachers[], year, semester, is_current,
tasks_count, exams_count}`, `warnings[]`.
No identity endpoint exists — `identity` is always `{name: null, role: null}`;
this is documented behavior, not a bug.

### `grades(stream_id?: int, study_id?: int)`

Returns: `scores[] {study_id, study_name, credits, status, status_label,
grade?, name_note?}`, `warnings[]`, `note?` ("no grades found..." when empty).
`status_label` comes from `SCORE_STATUS_LABELS = {1: "in progress", 2: "in
progress", 5: "completed"}`.

### `homework(stream_id?: int, study_id?: int, only_outstanding?: bool)`

Without `study_id`, iterates every study of the target stream (one
`learning/get_tasks` call each) and unions the rows; a failure on one study
becomes a warning, not a total failure. Returns: `homework[] {task_id, title,
study_id, study_name, status, is_done, credits_earned?, max_credits?, due_at?,
assessed_at?, chapter?, files?}`, `warnings[]`, `note?`.
`is_done` = `status in {3}` (`HOMEWORK_DONE_STATUSES`).

### `schedule(date?: str, start?: str, end?: str)`

`date` is mutually exclusive with `start`/`end` (validation error otherwise,
checked before any backend call). Default range with no args: the current ISO
week (Mon–Sun). Returns: `range` (human string), `timezone`, `week_variants`,
`week_parity_basis` (states the ISO-week-parity assumption explicitly),
`lessons[] {date, weekday, start, end, position, subject, study_id, kind,
teacher, room, subgroup}`, `warnings[]`, `note?` ("no lessons..." when empty).

## 7. Configuration

Precedence: **environment variable > repo-local JSON token file > built-in default.**

| Setting | Env var | Default | Required |
|---|---|---|---|
| Session token (`remember_lm_<hash>` value) | `FORLABS_SESSION_TOKEN` | — | yes |
| Base URL | `FORLABS_BASE_URL` | `https://bki.forlabs.ru` | no |
| Timeout (s) | `FORLABS_TIMEOUT_SECONDS` | `30` | no |
| Time zone | `FORLABS_TZ` | `Asia/Irkutsk` | no |
| Session cache | `FORLABS_SESSION_PATH` | `~/.local/state/forlabs-mcp/session.json` | no |
| Max list items | `FORLABS_MAX_ITEMS` | `200` | no |

Token file: `forlabs-session.json` at the repo root (gitignored; copy from
the committed `forlabs-session.example.json`), path overridable via
`FORLABS_TOKEN_FILE`. It is a flat JSON object with the same keys as the
table (`session_token`, `base_url`, `timeout_seconds`, `timezone`,
`session_path`, `max_items`). The placeholder token value counts as missing.
The former `~/.config/forlabs-mcp/config.toml` source was removed and is
no longer read.

## 8. Error taxonomy

`errors.py` defines one `ForlabsError` base and these subclasses, each mapped
by `to_tool_error()` to a classified, credential-free, single-line message:

| Exception | Raised when | Extra field |
|---|---|---|
| `ConfigError` | missing/malformed setting at startup | `key` |
| `InvalidArgumentError` | bad tool argument, checked before any backend call | `argument` |
| `AuthError` | session token rejected by the backend | — |
| `ConnectivityError` | host unreachable / DNS / connection reset | — |
| `TimeoutError` | request exceeded configured timeout | — |
| `RateLimitError` | backend rate-limited | `retry_after` |
| `UpstreamError` | backend returned an application error | `module`, `action` |
| `ProgrammingError` | action not on the read-only allow-list, or client misuse | — |

`to_tool_error()` never lets a raw exception or stack trace reach tool output
— an unrecognized exception collapses to a generic "Unexpected error…" line.

## 9. Testing approach

- `tests/fixtures/*.json` — the synthetic payloads in §3, used with
  [`respx`](https://github.com/lundberg/respx) to mock the HTTP layer; no real
  network in the default test run.
- `uv run pytest` — unit + mocked-HTTP tests (fast, no credentials needed).
- `uv run pytest -m integration` (only runs when `FORLABS_SESSION_TOKEN` is
  set) — hits the real backend for a smoke check (`reference` + `schedule`).
- `tests/test_repo_privacy.py` — a guardrail test scanning every **git-tracked**
  `tests/fixtures/*.json` and `docs/*.md` (via `git ls-files`, so a gitignored
  local scratch file is never scanned) for:
  - Title-Case-Cyrillic name-shaped patterns (`[А-ЯЁ][а-яё]+ [А-ЯЁ][а-яё]+...`)
    outside a small hardcoded allow-list of the synthetic names already in
    use — anything else name-shaped fails the test;
  - absolute `/Users/<name>` or `/home/<name>` paths.

  Keep the allow-list in `tests/test_repo_privacy.py` in sync whenever a new
  synthetic name is introduced into a fixture.
- `uv run ruff check .` / `uv run ruff format .` — lint/format, `select = ["E",
  "F", "I", "UP", "B", "W"]`, line length 100.

## 10. MCP client registration

Every MCP host wants the same three things: a **command**, its **args** and
the **env** vars it needs. README ships one copy-paste `mcpServers` JSON
block (`command: uv`, `args: ["--directory", "<repo>", "run",
"forlabs-mcp"]`, `env.FORLABS_SESSION_TOKEN`) with two placeholders the user
replaces; hosts with another wrapper take the same three fields. As an
alternative to `env`, the token can live in the gitignored
`forlabs-session.json` (§7). There are no generator or wizard scripts.

## 11. Known gaps / backlog (not yet implemented)

A DevTools capture of live SPA traffic showed these repository calls exist but
have **no captured payload yet**, so none are spec'd or built:

| Endpoint | What's needed before it can be built |
|---|---|
| `learning/get_chapters` | Capture request+response while browsing a course; relates to `Study.chapters_count` already seen in `get_studies` (§3 shows non-zero values, e.g. study `10823` has `chapters_count: 13`) |
| `learning/get_attendance` | Capture while viewing an attendance page; relates to `Study.attendance_count` |
| `learning/get_scoring` | Capture; compare against `learning/get_scores` (already implemented) to determine what it adds |
| `learning/get_score` (singular) | Capture; determine its scoping params (per-task? per-lesson? per-study?) |
| `webinars/get_webinars` | Capture; distinct module from `sched`/`learning` — decide if in scope at all |

Each becomes its own follow-up change once a payload is captured: new fixture
→ new allow-list entry → new/extended tool → new spec delta. This backlog is
tracked as the OpenSpec change `forlabs-endpoint-backlog` (0/15 tasks; each
group is capture → document → decide).

## 12. Privacy lessons learned (read before recapturing anything)

- **Never commit raw DevTools capture output directly.** The very first
  fixtures/docs in this project's history were captured verbatim (real
  lecturer full names, real course titles, a real uploaded filename + GUID, a
  real local absolute path in a scratch note) and had to be anonymized after
  the fact — anonymize *before* the first commit instead.
- **A rebase/amend that "fixes" old commits does not remove the old data.**
  `git rebase` only moves refs; the original blobs/commits stay reachable via
  the **reflog** (default ~90 days) and as dangling objects until `git gc
  --prune=now` actually deletes them. `git show <old-sha>:<path>` still works
  until that's done. If a repo's history ever holds real data, plan for
  reflog expiry + aggressive gc (or a from-scratch reinit) as an explicit
  step — don't assume a history rewrite alone is sufficient.
- **Scan tracked files, not the working directory.** The privacy guardrail
  test (§9) deliberately reads `git ls-files`, not a filesystem glob, so a
  gitignored local note (this project's `docs/mcp-smoke.md`, which
  legitimately contains a real local path for one developer's own
  reference) is never flagged or forced to be sanitized.
- **A synthetic-name allow-list beats a one-time fix.** A regex heuristic
  ("does this look like a Russian full name shape?") that fails on anything
  *not* in a small maintained allow-list catches a *future* accidental
  reintroduction, not just the specific names that leaked once.

## 13. Repo state at the time this document was written

- Local git history (13 → 19 commits after later work) has been rewritten so
  no commit, at any revision, contains real names/paths (verified via `git
  log --all -p | grep ...` returning zero matches for the known real strings)
  — but see §12's reflog/gc caveat if this repo is ever reused as a template
  rather than started fresh.
- `origin` (`github.com/Dest1n640/ForlabsMCP`) is registered but **empty** —
  `git ls-remote origin` returns zero refs. Nothing has been pushed yet.
- Pending manual steps, blocked on the user running `gh auth login`
  interactively:
  1. Create the public GitHub repo under `Dest1n640` (already registered as
     `origin`, just needs content).
  2. Push the full local commit history.
  3. Create GitHub issues from the `forlabs-endpoint-backlog` OpenSpec change
     — one per endpoint in §11.
- OpenSpec state: `scrub-history-and-universal-mcp-config` is 14/14 done, not
  yet archived; `forlabs-endpoint-backlog` is 0/15 (by design — it's a
  tracking backlog for future GitHub issues, not something to implement via
  `/opsx:apply`); `add-forlabs-mcp-server` is already archived under
  `openspec/changes/archive/2026-09-11-add-forlabs-mcp-server/`.
