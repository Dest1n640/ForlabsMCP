## Context

Today `tests/test_repo_privacy.py` scans `git ls-files "tests/fixtures/*.json"
"docs/*.md"` for name-shaped text and home paths, plus (since
`simplify-token-setup`) tracked `*.json` for a non-placeholder
`session_token`. It never sees README, reference doc, source or OpenSpec
artifacts, and nothing runs at commit time. An audit of all 60 commits,
the reflog and untracked files found no secrets, so this change adds
guardrails, not remediation. See proposal.md.

## Goals / Non-Goals

**Goals:**
- One scanner, two entry points (pytest, pre-commit), same rules.
- Zero false-positive noise on the current tree; no secret ever printed.

**Non-Goals:**
- No history rewrite or force-push, no token rotation.
- No third-party scanner dependency (gitleaks etc.); the project is
  dependency-light and the threat model is narrow.
- No touching files outside the repository.

## Decisions

**1. Scanner as a small pure module, reused by test and hook.** Put it in
`tools/leakscan.py` (stdlib only) with `scan_text(path, text) ->
list[Finding(path, line, rule)]`. `Finding` has no `value` field, so no
caller can print it by accident. The pytest test and the hook both import
it. Alternative: keep everything inside the test file - the hook would
then have to duplicate regexes or import from `tests/`.

**2. Rules (high confidence only).** Laravel remember value
(`\d+(\||%7C)[A-Za-z0-9]{40,}` and the hashed tail), encrypted-payload
cookies (`eyJ[A-Za-z0-9_-]{20,}` covers JWT and Laravel `eyJpdiI6`),
`XSRF-TOKEN=`/`forlabs_session=` with 20+ value chars, `gh[pousr]_`,
`sk-`, `AKIA`, `BEGIN ... PRIVATE KEY`, `Bearer <20+>`. Names and home
paths keep the existing regexes. Generic "password=..." heuristics are
excluded: the docs legitimately discuss passwords and placeholders, so a
loose rule would be noise that trains people to ignore failures.

**3. Allow-list is explicit and narrow.** The hardcoded
`REMEMBER_COOKIE_NAME` (a 40-hex cookie *name*, same for every account)
matches a naive `remember_lm_[0-9a-f]{20,}` rule, so that rule is not
used; the value rules above do not match a bare name. Placeholder and
synthetic names stay in constants. `uv.lock` and binary files are skipped;
`tests/fixtures` stay scanned.

**4. File enumeration from git.** `git ls-files -z`, decode as UTF-8 and
skip undecodable files. Keeps the existing "tracked only" property so
gitignored `forlabs-session.json` is never read. For the hook, read
`git show :<path>` (the index version) for each path from
`git diff --cached --name-only --diff-filter=ACMR`.

**5. Hook is opt-in.** Ship `.githooks/pre-commit` (POSIX sh calling
`python3 tools/leakscan.py --staged`), enable with
`git config core.hooksPath .githooks`. Auto-install is impossible without
a package manager hook, and the pytest scan remains the enforced backstop
in CI/local runs. Alternative considered: pre-commit framework - adds a
dependency and a config file for one hook.

**6. Committer email.** `git config user.email
<id>+Dest1n640@users.noreply.github.com`, with `<id>` from
`gh api user --jq .id`, set locally per repo (not global, to leave other
projects alone). Existing commits keep the old address.

**7. Manual steps are documented, not automated.** The old
`~/.config/forlabs-mcp/config.toml`, the cookie cache, and the dangling
blob live outside the tracked tree or outside published history; deleting
them is the user's call. README gets a short "Security" section with the
checklist.

## Risks / Trade-offs

- [False positive blocks a legitimate commit] -> Rules are high
  confidence; hook can be bypassed with `--no-verify` and the test names
  the rule so the allow-list can be extended deliberately.
- [False negative on an unfamiliar token shape] -> Accepted; the scanner
  is a tripwire for known shapes, not a proof of absence. README says so.
- [Hook not installed by contributors] -> pytest scan still fails in
  the normal test run.
- [Old email stays in 60 published commits] -> Stated openly in the
  README Security section; rewriting a public history was declined.
- [`tools/` shipped in the wheel] -> `tools/` is outside
  `packages = ["src/forlabs_mcp"]`, so it is not packaged.
