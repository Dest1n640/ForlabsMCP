## Why

A credential audit found no leaked secrets in the working tree or in any
commit, but it exposed weak spots that make a future leak likely: the
privacy test only scans `tests/fixtures/*.json` and `docs/*.md` (a
non-existent directory), so `README.md`, `PROJECT-REFERENCE.md`, `src/`
and `openspec/` are never checked; nothing runs at commit time; the
committer email is a personal address in a public repository; and
leftover copies of the real token sit in local files outside the repo
with no documented cleanup.

## What Changes

- **Leak scanner**: replace the narrow privacy test with a scanner over
  every git-tracked text file (except lockfile and binary files) that
  flags high-confidence secret shapes (Laravel remember/session cookie
  values, XSRF cookie values, JWT-like strings, GitHub/OpenAI/AWS keys,
  private key blocks, bearer tokens), non-allow-listed personal names, and
  absolute home paths. Known-safe constants (the fixed
  `remember_lm_<hash>` cookie *name*, the token placeholder, synthetic
  names) are explicitly allow-listed.
- **Pre-commit guard**: a `.githooks/pre-commit` script that runs the same
  scanner on staged content, plus a documented one-time
  `git config core.hooksPath .githooks`. **Opt-in**: git does not install
  hooks automatically.
- **Non-leaking failures**: scanner output reports file, line and rule
  name only, never the matched value.
- **Committer identity**: switch `user.email` for this repo to the GitHub
  noreply address so new commits stop carrying the personal email. No
  history rewrite and no force-push.
- **Manual cleanup checklist** (README "Security" section + a task the
  user performs; the agent does not touch these files): move the token from
  the now-unused `~/.config/forlabs-mcp/config.toml` to
  `forlabs-session.json` or `env` and delete the old file; know that
  `~/.local/state/forlabs-mcp/session.json` holds live cookies (`0600`);
  optionally run `git gc --prune=now` to drop one local dangling blob;
  optionally enable GitHub's "Block command line pushes that expose my
  email".
- Non-goals: rewriting published history, rotating the token (no leak was
  found), deleting files outside the repository.

## Capabilities

### New Capabilities
- `repo-leak-guard`: automated detection, at test time and at commit time,
  of credentials, personal names and local paths in tracked files, without
  echoing the offending value.

### Modified Capabilities
<!-- none -->

## Impact

- Code/tests: `tests/test_repo_privacy.py` (rewritten around a reusable
  scanner), new scanner module under `tests/` or `tools/` (see design),
  new `.githooks/pre-commit`.
- Docs: `README.md` (Security section), `PROJECT-REFERENCE.md` §9/§12
  (scanner scope).
- Local config: `git config user.email` for this repo (not tracked).
- No change to runtime behavior of the MCP server.
