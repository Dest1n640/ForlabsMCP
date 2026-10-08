## Why

The repo has a `Dockerfile`, but the image exists only as a local build:
every user has to clone and `docker build` before registering the server,
and nothing on GitHub links an image to the repository. Publishing the image
to GitHub Container Registry from CI gives users a ready `docker run` target
that shows up as a package on the repo page. Separately, the current
`Dockerfile` sets a `HOME` under `/home`, which the repo leak scan flags as
an absolute home path, so the test suite fails once it lands.

## What Changes

- Add a GitHub Actions workflow that builds the image on every PR (no push)
  and publishes it to `ghcr.io/dest1n640/forlabsmcp` on push to `main`
  (`latest` + `sha-<short>`) and on `v*` tags (`X.Y.Z`, `X.Y`).
- Gate publishing on the test suite and lint (`pytest`, `ruff`) passing in
  the same workflow.
- Publish for `linux/amd64` and `linux/arm64`.
- Add the OCI `org.opencontainers.image.source` label (plus a description)
  so GHCR links the package to the repository.
- Move the container `HOME` from under `/home` to `/var/lib/forlabs` so the
  leak scan passes; runtime behaviour (non-root UID, session cache location
  under `$HOME`) is unchanged.
- Update the README Docker section to use the published image as the default,
  keeping local build as an alternative.

## Capabilities

### New Capabilities
- `container-image`: published container image for the MCP server: registry
  location, tag scheme, repository linkage, platforms, and runtime contract
  (stdio, non-root, token only from runtime env).

### Modified Capabilities
<!-- none: repo-leak-guard behaviour is unchanged; the Dockerfile is fixed to comply with it -->

## Impact

- New: `.github/workflows/docker.yml`.
- Changed: `Dockerfile` (labels, `HOME` path), `README.md` (Docker section).
- External: GHCR package `dest1n640/forlabsmcp`. First publish creates it as
  private; the owner must switch visibility to public once in GitHub
  package settings (not automatable with `GITHUB_TOKEN`).
- No Python code or dependency changes.
