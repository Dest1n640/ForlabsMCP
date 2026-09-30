# repo-leak-guard Specification

## Purpose

Prevents credentials, personal names and local machine paths from being
committed to this public repository, by scanning tracked content both in
the test suite and at commit time, and by never echoing what it found.

## Requirements

### Requirement: Tracked-file secret scan
The repository test suite SHALL scan every git-tracked text file (lockfiles
and binary files excluded) and SHALL fail when any file contains a value
matching a high-confidence secret shape: a Laravel remember or session
cookie value, an XSRF cookie value, a JWT-like string, a GitHub, OpenAI or
AWS credential, a private key block, or a bearer token. Constants declared
safe by an explicit allow-list (the fixed `remember_lm_<hash>` cookie
name, the token placeholder) SHALL NOT be flagged.

#### Scenario: A real-looking cookie value in documentation fails the scan
- **WHEN** a tracked `README.md` contains a string shaped like a Laravel
  remember-cookie value
- **THEN** the scan fails and names the file, line and rule

#### Scenario: The allow-listed cookie name and placeholder pass
- **WHEN** tracked files contain the fixed `remember_lm_<hash>` cookie
  name and the token placeholder
- **THEN** the scan reports no violation for them

#### Scenario: Gitignored local files are not scanned
- **WHEN** an untracked, gitignored file such as `forlabs-session.json`
  contains a real token
- **THEN** the scan does not read it and does not fail

### Requirement: Scan covers all tracked text, not a fixed folder list
The scan SHALL enumerate files from git's tracked-file list rather than a
fixed set of directories or globs, so newly added files and directories
are covered without changing the scanner.

#### Scenario: A newly added directory is covered
- **WHEN** a new tracked file is added under a directory that did not
  exist before
- **THEN** the scan reads that file

### Requirement: Personal names and local paths are rejected
The scan SHALL fail on a Cyrillic full-name-shaped string that is not on
the synthetic-name allow-list, and on any absolute `/Users/<name>` or
`/home/<name>` path, in any tracked text file.

#### Scenario: Unlisted name fails
- **WHEN** a tracked file contains a full-name-shaped string not on the
  allow-list
- **THEN** the scan fails naming the file and line

#### Scenario: Home path fails
- **WHEN** a tracked file contains an absolute home-directory path
- **THEN** the scan fails naming the file and line

### Requirement: Findings never echo the matched value
Every scan failure message, whether from the test suite or from the
commit-time guard, SHALL identify the finding by file, line number and
rule name only, and SHALL NOT include the matched secret, name or path.

#### Scenario: Failure output omits the secret
- **WHEN** the scan flags a secret-shaped string
- **THEN** neither the assertion message nor the hook output contains any
  part of that string

### Requirement: Commit-time guard on staged content
The repository SHALL provide an opt-in pre-commit hook that runs the same
scan on the content staged for commit and blocks the commit when a rule
matches. The hook SHALL scan the staged version of each file, not the
working-tree version.

#### Scenario: Staged secret blocks the commit
- **WHEN** a file with a secret-shaped value is staged and the hook is
  enabled
- **THEN** the commit is rejected with a message listing file, line and
  rule

#### Scenario: Secret only in the working tree does not block
- **WHEN** the staged version of a file is clean but its working-tree copy
  contains a secret
- **THEN** the hook allows the commit

#### Scenario: Clean commit passes
- **WHEN** staged files contain no rule matches
- **THEN** the commit proceeds
