## Context

`Dockerfile` (two-stage: `uv` builder → `python:3.11-alpine3.23` runtime,
UID 65532, entrypoint `forlabs-mcp`) already exists from commit "Added docker
container". There is no `.github/workflows/` yet. The tracked `Dockerfile`
sets a `HOME` under `/home`, which `tools/leakscan.py`'s `ABSOLUTE_PATH_RE`
flags, so `tests/test_repo_privacy.py` currently fails. Session cache path is
`~/.local/state/forlabs-mcp/session.json` (`config.py` `DEFAULT_SESSION_PATH`),
resolved via `HOME`.

## Goals / Non-Goals

**Goals:**
- One workflow file, standard Docker actions, no new secrets.
- Make the suite green again without weakening the leak scanner.

**Non-Goals:**
- Docker Hub or other registries.
- Image signing/attestations, SBOM, vulnerability scanning.
- Automated release/version bumping; tags are pushed by hand.
- Changing the `pyproject.toml` version; image version comes from the git tag.

## Decisions

- **Workflow:** single `.github/workflows/docker.yml` with two jobs:
  `test` (`astral-sh/setup-uv`, `uv sync --frozen`, `uv run ruff check .`,
  `uv run pytest -q`) and `image` (`needs: test`). Triggers: `push` on
  `main` and tags `v*`, `pull_request` on `main`. Alternative: separate CI
  and publish workflows. Rejected: `needs:` across workflows requires
  `workflow_run` plumbing; one file is simpler.
- **Image job:** `docker/setup-qemu-action`, `docker/setup-buildx-action`,
  `docker/login-action` (ghcr.io, `github.actor`, `secrets.GITHUB_TOKEN`,
  skipped on PRs), `docker/metadata-action`, `docker/build-push-action`
  with `push: ${{ github.event_name != 'pull_request' }}`,
  `platforms: linux/amd64,linux/arm64`, GHA cache (`cache-from/to: type=gha`).
  Job permissions: `contents: read`, `packages: write`.
- **Tags:** `metadata-action` with `type=raw,value=latest,enable={{is_default_branch}}`,
  `type=sha` (default `sha-<7>` format), `type=semver,pattern={{version}}`,
  `type=semver,pattern={{major}}.{{minor}}`. Image name hardcoded lowercase
  `ghcr.io/dest1n640/forlabsmcp`. GHCR rejects uppercase, and
  `${{ github.repository }}` is `Dest1n640/ForlabsMCP`.
- **Labels:** put `org.opencontainers.image.source` and `.description` as
  `LABEL` in the `Dockerfile` runtime stage, so local builds are linked too.
  `metadata-action` labels are also passed by `build-push-action` and add
  revision/created. Alternative: rely only on metadata-action. Rejected:
  local `docker build` + manual push would then be unlinked.
- **HOME path:** `/var/lib/forlabs`, created and chowned to 65532 as before.
  Alternative: add that `/home` path to the leak-scan allow-list. Rejected:
  widens a security control to save one path rename.
- **arm64 build cost:** QEMU emulation. Native deps (`pydantic-core`, `rpds-py`, etc.) are expected
  to ship musllinux aarch64 wheels, so nothing should compile under
  emulation. Alternative: native arm64 runners. Not needed at this size.

## Risks / Trade-offs

- [First push creates a **private** GHCR package; anonymous `docker pull`
  fails] → README and tasks include a one-time manual step: Package settings →
  Change visibility → Public, and confirm the repo link under "Manage Actions
  access".
- [A dependency without a musllinux aarch64 wheel would build from source
  under QEMU, slowly or not at all] → `uv sync --frozen` fails loudly in CI.
  Pin or drop arm64 if it happens.
- [`latest` moves on every merge, so users on `latest` get untested-in-prod
  changes] → README recommends a version tag once releases exist.

## Migration Plan

Merge → workflow publishes `latest` → owner makes the package public once.
Rollback: delete the workflow file; previously pushed tags stay pullable.
Users of `forlabs-mcp:local` are unaffected; the README keeps local build.
