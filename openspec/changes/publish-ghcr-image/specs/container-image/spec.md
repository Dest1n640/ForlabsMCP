## Purpose

Ships the MCP server as a ready-to-run container image published to GitHub
Container Registry and linked to this repository, so users can register the
server without cloning or building it.

## ADDED Requirements

### Requirement: Image is published to GHCR from main and release tags
CI SHALL publish the image to `ghcr.io/dest1n640/forlabsmcp`. A push to
`main` SHALL publish tags `latest` and `sha-<short-commit>`. A pushed git
tag `vX.Y.Z` SHALL publish tags `X.Y.Z` and `X.Y`. Pull requests SHALL build
the image without publishing it.

#### Scenario: Merge to main publishes latest
- **WHEN** a commit lands on `main` and CI succeeds
- **THEN** `ghcr.io/dest1n640/forlabsmcp:latest` and
  `ghcr.io/dest1n640/forlabsmcp:sha-<short-commit>` point to an image
  built from that commit

#### Scenario: Release tag publishes a version
- **WHEN** tag `v0.2.0` is pushed
- **THEN** tags `0.2.0` and `0.2` are published for that commit

#### Scenario: Pull request builds but does not push
- **WHEN** a pull request is opened or updated
- **THEN** CI builds the image and no tag in the registry changes

### Requirement: Publishing is gated on tests and lint
CI SHALL NOT publish an image when the test suite or the linter fails for
the same commit.

#### Scenario: Failing test blocks publish
- **WHEN** a commit on `main` fails `pytest`
- **THEN** no image tag is published for that commit

### Requirement: Image is linked to the repository
The image SHALL carry the OCI label `org.opencontainers.image.source` set to
`https://github.com/Dest1n640/ForlabsMCP`, so the registry lists the package
under this repository.

#### Scenario: Label present
- **WHEN** a published image is inspected
- **THEN** its `org.opencontainers.image.source` label equals the
  repository URL

### Requirement: Image runs on amd64 and arm64
Each published tag SHALL be a multi-platform image covering `linux/amd64`
and `linux/arm64`.

#### Scenario: Apple Silicon pull
- **WHEN** a user on an arm64 host runs `docker pull` for a published tag
- **THEN** the native `linux/arm64` variant is pulled without emulation

### Requirement: Runtime contract
The image SHALL start the MCP server over stdio as its entrypoint, SHALL
run as a non-root user, and SHALL NOT contain a session token or session
file; the token SHALL be supplied only at run time via the environment.

#### Scenario: Stdio server with runtime token
- **WHEN** a user runs `docker run --rm -i --env FORLABS_SESSION_TOKEN
  ghcr.io/dest1n640/forlabsmcp:latest` with the variable set
- **THEN** the MCP server speaks the protocol over stdin/stdout as a
  non-root process

#### Scenario: No credentials baked in
- **WHEN** the image filesystem and its config are inspected
- **THEN** no session token or session file is present

### Requirement: Image source complies with the repo leak scan
Container build files SHALL pass the repository leak scan, including the
absolute home-path rule.

#### Scenario: Dockerfile passes the scan
- **WHEN** the test suite runs the tracked-file leak scan
- **THEN** the `Dockerfile` produces no finding
