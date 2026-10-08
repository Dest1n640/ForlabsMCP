# Design

## Attachment objects vs ids

`POST /lm-vendor/upload` returns `{"attachment": {...}}`. The web client feeds
`$scope.form.files` — that whole array of attachment objects — into
`assignments/post_comment`, while `POST /lm-vendor/repositories/uploads/store`
takes a list of ids (`{files: ids}`). The reference client had used ids for both,
so `post_comment` posted with an ignored `files` list and the comment showed no
attachments (no error). The fix keeps both shapes: `_upload_attachment` returns
the object, the caller derives ids for `store`/`delete`, and passes the objects
to `post_assignment_comment`. The read-back visibility check still compares ids,
because the comment's `attachments[]` carry ids.

## Own user id for `has_feedback`

Feedback and the student's own replies live in the same thread and comment
objects carry no role flag, only `user_id`. `GET /app/profile/user` is the SPA's
own current-user endpoint and returns the numeric `id`, so the filter flags a
comment as feedback when its `user_id` differs from the profile id. It is a plain
app GET, not an `lm-vendor` RPC, so it is called directly and is not added to the
read-only allow-list. If the profile cannot be read, `has_feedback` is skipped
with a warning rather than mis-filtering.

## Materials merge

`learning/get_chapters` supplies the course header and the chapter list, but the
list's chapters carry only metadata (`id`, `title`, `has_content`,
`blocks_count`). Annotation/content/files live in `learning/get_chapter`, which
has **no** `has_content` field — the merge keeps the list's `has_content` and
takes the rest from the detail. Chapters that advertise no content skip the
detail call. A failed chapter becomes a warning, never a failed call.
