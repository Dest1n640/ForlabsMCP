# forlabs-mcp — full project reference

Single-file reference for rebuilding this project from scratch without
recapturing anything. Everything quoted here (JSON payloads, field names,
endpoint paths) is either non-sensitive protocol detail or already-synthetic
fixture data — safe to reuse in a fresh repo under any account.

## 1. What this is

A local [MCP](https://modelcontextprotocol.io) server (`forlabs-mcp`) that logs
into the Forlabs/Lamotivo school-diary SPA at `https://bki.forlabs.ru/app` as a
student. It registers eight safe tools for schedules, own subjects, tasks, and
assignment responses; an additional non-idempotent response-write tool is
registered only when explicitly enabled. The generic RPC path is read-only;
submission uses a separate fixed, opt-in lane. No exam workflows, grading
writes, attendance changes, edits, or arbitrary backend writes are exposed.

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
pair as a side effect. A `401`/`419` usually means the short-lived pair
went stale — in the cache file or in a long-running process — not that the
remember cookie died: a cached ~3-day-old pair was confirmed live to get
`419 {"message": "CSRF token mismatch."}` while the same remember cookie
alone got `200`. So on a `401`/`419` the client drops every cookie except
the remember cookie (re-seeded from `session_token`), re-primes
`XSRF-TOKEN`, and retries the call exactly once. Only a repeat on that
retry raises `AuthError`: `401` means the `remember_lm_<hash>` value itself
was rejected (a rare, ~5-year-horizon event requiring a fresh value from
the browser); `419` means a CSRF rejection that a new token would not fix.

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

The read-only repository allow-list contains these student-role calls; reject
every other action *before* any HTTP request:

```
sched/get_grid
sched/get_schedule
learning/get_streams
learning/get_studies
learning/get_scores
learning/get_tasks
learning/get_task
assignments/get_comments
```

`learning/get_streams` is on the allow-list (observed in traffic) but the
current client does not call it: it returns only the authenticated student's
own stream. The schedule endpoint supplies the selectable group catalog in
`streams[]`; that catalog is not a subject list.

Assignment writes use separate dedicated methods, never this allow-list:
`assignments/post_comment`, `uploads/store`, `uploads/delete`, and the fixed
FlowJS upload route. No assessment, attendance, edit, delete, or arbitrary
RPC write path is available.

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

The authenticated own-schedule request is `{}`; the live SPA also uses
`{"stream_id": 0}` for its default and `{"stream_id": <integer>}` for a
selected group. Empty-body and selected-group requests both succeeded live.
The response's `meta.stream_ids` marks the student's own group(s);
`streams[]` contains all schedule-selectable groups (42 in the captured
response), while `entries[]` is for the requested schedule. In contrast,
`learning/get_streams` returned a single own stream with student metadata;
it is not the source for schedule group options.

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

### Assignment workflow endpoint shapes

#### `learning/get_task`

Request body: all identifiers are strings:
`{"stream_id": "210", "study_id": "7210", "task_id": "7001"}`.

Response shape: `{"task": <task>, "assignment": <assignment>}`. The task
object uses the `learning/get_tasks` fields above; the assignment object
uses the fields in `assignments[]`. The implementation validates task
ownership against the own-study `learning/get_tasks` result before asking
for this detail.

#### `assignments/get_comments`

Request body uses mixed types:
`{"study_id": "7210", "task_id": 7001, "assignment_id": 8001}`.
The response is `{"comments": [...]}`; an empty comments array is valid.
Captured comment objects include `id`, `user_id`, `message`, `created_at`,
`user`, and `attachments`. Fixtures use synthetic authors and messages.

#### Assignment response writes (deployed frontend source)

Creating a new response calls
`assignments/post_comment({study_id, task_id, assignment_id, message,
files, mode})`; the UI's `id` field is omitted for a new response and its
student mode is `"student"`. File IDs are finalized with
`uploads/store({"files": [<id>, ...]})`; UI cancellation removes them with
`uploads/delete({"files": [<id>, ...]})`.

The assignment UI uses FlowJS at `/lm-vendor/upload`. Deployed source
(`lm-app-*.js` + the ng-flow library in `lm-vendor-*.js`) confirms:
`flowFactoryProvider.defaults` targets `lmVendorPrefix + '/upload'`, sends
`X-XSRF-TOKEN` (`Cookies.get('XSRF-TOKEN')`) on every request, and keeps the
library defaults `chunkSize: 1048576` (1 MiB), `fileParameterName: "file"`,
`testChunks: true` (a `GET` preflight per chunk), and
`successStatuses: [200, 201, 202]`. The multipart `file` field carries the
original filename, alongside FlowJS `flowChunk*`, `flowTotal*`, and
`flowIdentifier` fields. A live read-only `GET` preflight with a random
`flowIdentifier` returned `204` (chunk absent), matching the client's
"proceed only on 204" rule.

The final chunk response is JSON whose `attachment` object is the uploaded
file record: the dialog's `flow-file-success` handler does
`JSON.parse($message).attachment` and pushes it into the message's file list,
and those records' `id`s become the `files` array. Confirming the dialog runs
`uploads/store({"files": [<id>, ...]})` before `post_comment`, and detaching
or cancelling a file runs `uploads/delete({"files": [<id>, ...]})`.
The task dialog limits each attachment to 50 MiB (`max_size = 50 * 1024` KB)
and permits any extension. This upload sequence is confirmed from deployed
source, not from a live file upload. The only authorized live write is one
text-only `.` response to the user's first own 1C assignment; do not upload a
file.

### `learning/get_streams`

The captured response has a top-level `streams` array containing only the
authenticated student's own stream, including student-specific fields.
Do not expose those fields or treat this endpoint as the schedule group
catalog; schedule group options come from `sched/get_schedule.streams`.

## 4. Architecture

```
MCP stdio
  -> server.py
     -> tools/register.py (8 default tools; submit tool only when opted in)
        -> ForlabsClient (own-study scope, schedule group selection,
           assignment details/thread, one-use response preview/submit)
           -> dates.py / parsers.py / models.py
           -> client/submissions.py (preview state, file scope and integrity)
           -> client/repository.py
              -> read-only RPC allow-list
              -> fixed, gated assignment-write methods
                 -> client/session.py (XSRF/session cookies, no write retry)
                    -> https://bki.forlabs.ru
```

Reads and writes share the authenticated session, but not the RPC policy:
the generic repository call can invoke only the read allow-list; the
submission lane has fixed operations and cannot accept arbitrary modules,
actions, IDs, modes, or local paths from a submit call.

Module responsibilities:

| Module | Responsibility |
|---|---|
| `config.py` | `ForlabsConfig` + `load_config()`. Ordinary settings: env > repo-local JSON token file > default. Assignment writes and upload root are env-only; writes default off. |
| `client/session.py` | `ForlabsSession`: remember cookie, XSRF header, cookie persistence (`0600`). Safe reads may reset/retry once on `401`/`419`; writes disable auth retry to avoid duplicate non-idempotent requests. |
| `client/repository.py` | `Repository.call()` enforces `READ_ONLY_ACTIONS` before HTTP. Separate fixed methods allow only the opted-in assignment comment, upload finalize/delete, and FlowJS chunk protocol. |
| `client/models.py` | Pydantic models (`extra="ignore"`) for `Stream`, `Study`, schedule/score/task/assignment rows, `AssignmentComment`, and identity. |
| `client/parsers.py` | Tolerant `payload -> model` functions; malformed rows become warnings where partial results are safe. |
| `client/partial.py` | `PartialResult[T]` — parsed `data`, `warnings`, and partial-result state. |
| `client/submissions.py` | Ten-minute, one-use preview records; path containment beneath the configured upload root; regular-file, size, identity, modification-time, and SHA-256 checks. |
| `client/client.py` | Domain operations: own-stream discovery, own studies/grades/homework, schedule groups, task details/threads, and safe submission orchestration/read-back. |
| `dates.py` | `resolve_range()` and `resolve_lessons()` calendar and week-parity calculations. |
| `tools/register.py` | Registers eight default tools; conditionally registers the annotated non-idempotent submit tool. Converts `ForlabsError` to a classified `ToolError`. |
| `server.py` | CLI entry point. Reads the submission switch to shape the tool catalog, then loads credentials lazily on first invocation. |
| `errors.py` | `ForlabsError` taxonomy + `to_tool_error()` (see §8). |

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

## 6. MCP tools — exact contracts

The default catalog has eight tools. The ninth, non-idempotent write tool is
registered only when `FORLABS_ENABLE_ASSIGNMENT_SUBMISSION` is true.

### `reference()`

Returns `identity {name, role}`, `own_stream_id`,
`streams[] {id, name, is_own}` from the schedule-group catalog, own
`studies[]` for the authenticated student, and `warnings[]`. No identity
endpoint exists, so `identity` is `{name: null, role: null}`. There is no
group-selection argument.

### `schedule_groups()`

Returns `own_stream_id`, `groups[] {id, name, is_own}`, and `warnings[]`.
This catalog comes from `sched/get_schedule.streams`; it lists schedule
choices, not enrolled subjects.

### `schedule(date?: str, start?: str, end?: str, stream_id?: int)`

`date` is mutually exclusive with `start`/`end`; validation occurs before
backend calls. No range means the current ISO week (Mon–Sun). No `stream_id`
means the student's own schedule; a selected group ID must be in
`schedule_groups()`. Returns `range`, `timezone`, `week_variants`,
`week_parity_basis`, selected `stream_id`/`stream_name`,
`lessons[] {date, weekday, start, end, position, subject, study_id, kind,
teacher, room, subgroup}`, `warnings[]`, and optional `note`.

### `grades(study_id?: int)`

Returns grades only for the student's own studies, optionally filtered by
study: `scores[] {study_id, study_name, credits, status, status_label,
grade?, name_note?}`, `warnings[]`, optional `note`. `status_label` uses
`SCORE_STATUS_LABELS = {1: "in progress", 2: "in progress", 5: "completed"}`.

### `homework(study_id?: int, only_outstanding?: bool)`

Without `study_id`, iterates every own study (one `learning/get_tasks` call
each); a per-study failure becomes a warning. An explicit study must also
belong to the authenticated student. Returns `homework[] {task_id, title,
study_id, study_name, status, is_done, credits_earned?, max_credits?, due_at?,
assessed_at?, chapter?, files?}`, `warnings[]`, optional `note`.
`is_done` means `status in {3}`.

### `assignment_details(study_id: int, task_id: int)`

Accepts only a task in one of the student's own studies. Returns `study_id`,
`study_name`, `task_id`, typed `task`, `assignment` (or `null` when not yet
assigned), and `warnings[]`. Backend task/assignment IDs are cross-checked
against the own-study task list.

### `assignment_thread(study_id: int, task_id: int)`

Returns the own task and unique assignment identity/status plus
`comments[] {id, user_id, message, created_at, user, attachments}`,
`warnings[]`, and a no-responses `note` when empty.

### `preview_assignment_response(study_id, task_id, message, file_paths?)`

Validates own-study scope and requires a unique assignment. Trims the message
as the SPA does; text or at least one attachment is required. Returns a
10-minute, one-use `preparation_id`, task/assignment metadata, the exact
outgoing text, attachment names/sizes/MIME types (never local paths or
hashes), and warnings. Attachment paths must stay under
`FORLABS_UPLOAD_ROOT`; text-only previews need no upload root.

### `submit_assignment_response(preparation_id)`

Exists only when explicitly enabled. Consumes the matching preview once,
revalidates assignment and file fingerprints, uploads/finalizes selected
attachments if any, then posts `assignments/post_comment` in student mode
without an `id`. Write requests are never automatically retried. It reads the
thread after the request and reports `confirmed`, `accepted`, `uncertain`, or
`not_sent`; inspect the thread manually before retrying any uncertain result.

## 7. Configuration

For ordinary settings represented in JSON: **environment variable > repo-local
JSON token file > built-in default**. The security-sensitive assignment switch
and attachment root are environment-only.

| Setting | Env var | Default | Required |
|---|---|---|---|
| Session token (`remember_lm_<hash>` value) | `FORLABS_SESSION_TOKEN` | — | yes |
| Base URL | `FORLABS_BASE_URL` | `https://bki.forlabs.ru` | no |
| Timeout (s) | `FORLABS_TIMEOUT_SECONDS` | `30` | no |
| Time zone | `FORLABS_TZ` | `Asia/Irkutsk` | no |
| Session cache | `FORLABS_SESSION_PATH` | `~/.local/state/forlabs-mcp/session.json` | no |
| Max list items | `FORLABS_MAX_ITEMS` | `200` | no |
| Assignment response writes (`true`/`1`, `false`/`0`) | `FORLABS_ENABLE_ASSIGNMENT_SUBMISSION` | `false` | no |
| Allowed attachment root (environment only) | `FORLABS_UPLOAD_ROOT` | — | no |

Token file: `forlabs-session.json` at the repo root (gitignored; copy from
the committed `forlabs-session.example.json`), path overridable via
`FORLABS_TOKEN_FILE`. It contains the ordinary settings
`session_token`, `base_url`, `timeout_seconds`, `timezone`, `session_path`,
and `max_items`. The submission switch defaults to false and is not read
from the token file; `FORLABS_UPLOAD_ROOT` is also environment-only. The
placeholder token counts as missing; the former
`~/.config/forlabs-mcp/config.toml` source is no longer read.

## 8. Error taxonomy

`errors.py` defines one `ForlabsError` base and these subclasses, each mapped
by `to_tool_error()` to a classified, credential-free, single-line message:

| Exception | Raised when | Extra field |
|---|---|---|
| `ConfigError` | missing/malformed setting at startup | `key` |
| `InvalidArgumentError` | bad tool argument, checked before any backend call | `argument` |
| `AuthError` | `401`/`419`: safe reads retry once after a session reset; non-idempotent writes fail without retry | — |
| `ConnectivityError` | host unreachable / DNS / connection reset | — |
| `TimeoutError` | request exceeded configured timeout | — |
| `RateLimitError` | backend rate-limited | `retry_after` |
| `UpstreamError` | backend returned an application error | `module`, `action` |
| `ProgrammingError` | action off the read-only allow-list, disabled submission, or client misuse | — |

`to_tool_error()` never lets a raw exception or stack trace reach tool output
— an unrecognized exception collapses to a generic "Unexpected error…" line.

## 9. Testing approach

- Submission tests mock thread reads, the fixed comment write, FlowJS chunk
  requests, upload finalization/cleanup, file confinement, and ambiguous
  write outcomes. The only authorized live write is one text-only `.` to the
  user's first own 1C assignment; live file upload is not authorized.
- `tests/fixtures/*.json` — the synthetic payloads in §3, used with
  [`respx`](https://github.com/lundberg/respx) to mock the HTTP layer; no real
  network in the default test run.
- `uv run pytest` — unit + mocked-HTTP tests (fast, no credentials needed).
- `tests/test_repo_privacy.py` + `tools/leakscan.py` — a guardrail scanning
  **every git-tracked text file** (via `git ls-files`, so the gitignored
  `forlabs-session.json` is never read; `uv.lock` and binaries skipped) for:
  - high-confidence secret shapes (Laravel remember/session/XSRF cookie
    values, JWT-like strings, GitHub/OpenAI/AWS keys, private-key blocks,
    bearer tokens) and a non-placeholder `session_token` in tracked JSON;
  - Title-Case-Cyrillic name-shaped patterns outside a small hardcoded
    allow-list of the synthetic names already in use;
  - absolute `/Users/<name>` or `/home/<name>` paths.

  Findings are reported as `path:line: rule` only, never the value. The
  same scanner runs at commit time via the opt-in `.githooks/pre-commit`
  (`git config core.hooksPath .githooks`), on staged content. Keep the
  name allow-list in `tools/leakscan.py` in sync whenever a new synthetic
  name is introduced into a fixture. Test values that look like secrets
  must be assembled at runtime (see `tests/test_leakscan.py`), or the
  scanner flags the test file itself.
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
  (§9) deliberately reads `git ls-files`, not a filesystem glob, so a
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
