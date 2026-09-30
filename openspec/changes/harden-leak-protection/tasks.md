## 1. Branch setup

- [x] 1.1 Create and check out branch `harden-leak-protection` off an
      up-to-date `main`; verify with `git branch --show-current`.

## 2. Scanner

- [x] 2.1 Add `tools/leakscan.py` (stdlib only): rule table, `Finding`
      with `path`, `line`, `rule` and no value field, `scan_text()`,
      allow-lists (safe cookie name, placeholder, synthetic names), and a
      CLI (`--all` for tracked files, `--staged` for the index) that exits
      non-zero and prints `path:line: rule` only. Verify with the unit
      tests in 2.2.
- [x] 2.2 Add `tests/test_leakscan.py`: each rule has a positive and a
      negative case using clearly synthetic values; allow-listed cookie
      name and placeholder pass; a failure message never contains the
      matched string. Verify `uv run pytest tests/test_leakscan.py`
      passes.
- [x] 2.3 Rewrite `tests/test_repo_privacy.py` to call the scanner over
      `git ls-files` (all tracked text, lockfile and binary skipped),
      keeping the existing name/path and JSON-token cases; verify the
      current tree passes and that a temporary tracked file with a
      secret-shaped value makes the test fail without printing it.

## 3. Commit-time guard

- [x] 3.1 Add `.githooks/pre-commit` (executable) running
      `python3 tools/leakscan.py --staged`, reading index content via
      `git show :<path>`; verify with a throwaway repo test or manual
      check: staged secret blocks, clean-staged/dirty-worktree allows,
      clean commit passes.
- [x] 3.2 Add a test for the `--staged` code path using a temporary git
      repo fixture; verify it passes in `uv run pytest`.

## 4. Docs

- [x] 4.1 Add a "Безопасность" section to `README.md`: what the guard
      does and does not catch, the opt-in
      `git config core.hooksPath .githooks`, and the manual checklist
      (move token from old `~/.config/forlabs-mcp/config.toml` and delete
      it; `~/.local/state/forlabs-mcp/session.json` holds live cookies
      with mode `0600`; optional `git gc --prune=now`; optional GitHub
      "Block command line pushes that expose my email"). Verify no real
      values or home paths appear in it.
- [x] 4.2 Update `PROJECT-REFERENCE.md` §9 and §12 to describe the new
      scanner scope and the hook; verify the scan still passes.

## 5. Identity and verification

- [x] 5.1 Set this repo's `user.email` to the GitHub noreply address
      (id from `gh api user --jq .id`) with `git config --local`; verify
      `git config --local user.email` shows it and that the next commit
      is authored with it. Do not rewrite history.
- [x] 5.2 Run `uv run pytest`, `uv run ruff check .`,
      `uv run ruff format --check .`; verify all pass.
- [ ] 5.3 Open a PR from `harden-leak-protection` to `main` and merge it
      (per the project's per-stage auto-PR/merge convention); verify
      `git log main` shows the merge.

## 6. Manual, performed by the user (agent does not do these)

- [ ] 6.1 Move the token from `~/.config/forlabs-mcp/config.toml` into
      `forlabs-session.json` or the MCP host `env`, then delete the old
      file.
- [ ] 6.2 Optionally run `git gc --prune=now` to drop the local dangling
      blob, and enable GitHub's email-exposure push block.
