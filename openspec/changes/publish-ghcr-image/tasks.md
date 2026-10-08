## 1. Dockerfile

- [x] 1.1 Change `HOME` to `/var/lib/forlabs` and the matching `mkdir`/`chown` lines; verify `uv run pytest -q tests/test_repo_privacy.py` passes
- [x] 1.2 Add `LABEL org.opencontainers.image.source="https://github.com/Dest1n640/ForlabsMCP"` and `org.opencontainers.image.description` to the runtime stage; verify with `docker build -t forlabs-mcp:local . && docker inspect -f '{{json .Config.Labels}}' forlabs-mcp:local`
- [x] 1.3 Smoke-test the local image: `docker run --rm -i --env FORLABS_SESSION_TOKEN=x forlabs-mcp:local` starts, `id -u` inside is 65532, and the session cache is written under `/var/lib/forlabs/.local/state/forlabs-mcp`

## 2. Workflow

- [x] 2.1 Add `.github/workflows/docker.yml` with a `test` job (setup-uv, `uv sync --frozen`, `ruff check .`, `pytest -q`) and an `image` job (`needs: test`, permissions `contents: read` + `packages: write`, QEMU + buildx, GHCR login skipped on PRs, metadata-action tags per design, build-push with `linux/amd64,linux/arm64`, gha cache, push only when not a PR); verify the YAML with `actionlint` if available, otherwise `python -c "import yaml; yaml.safe_load(open('.github/workflows/docker.yml'))"`
- [x] 2.2 Open the PR and verify both jobs pass and the `image` job builds without a login/push step running

## 3. Docs

- [x] 3.1 Update the README Docker section: published image `ghcr.io/dest1n640/forlabsmcp:latest` as the default in the `mcpServers` example, `docker pull` instructions, local build kept as an alternative, version-tag recommendation; verify the leak-scan test still passes

## 4. Publish (after merge)

- [ ] 4.1 Confirm the run on `main` pushed `latest` and `sha-<short>`: `docker buildx imagetools inspect ghcr.io/dest1n640/forlabsmcp:latest` lists both `linux/amd64` and `linux/arm64`
- [ ] 4.2 Owner, one-time: set GHCR package visibility to Public and confirm it appears under the repo's "Packages"; verify with an anonymous `docker pull` (after `docker logout ghcr.io`)
