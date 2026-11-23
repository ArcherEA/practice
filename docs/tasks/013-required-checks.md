# 013 — Required status checks and the pull-request workflow

**Status:** in review (PR) · **Who:** lead (CI config + docs) · **Branch:** `feat/013-required-checks` · **Size:** small

## Why
The user will protect `main` with a GitHub ruleset that requires CI checks. `Test Backend` and `Test Docker Compose`
skipped docs-only changes with `paths-ignore`, so as *required* checks they would never report and block docs PRs.

## Scope
- Both workflows: always start; a `changes` job (dorny/paths-filter, same pin as Playwright) detects non-docs changes;
  the test job runs only then; an always-running `alls-green-*` job (re-actors/alls-green, same pin) reports the result.
- `docs/BRANCH-PROTECTION.md`: exact ruleset settings and the PR workflow. `CLAUDE.md`: changes reach `main` via PRs.

## Acceptance criteria
- On this PR (code changes): tests run; `alls-green-backend`, `alls-green-docker-compose`, `alls-green-playwright` green.
- On a docs-only PR: test jobs skipped, the three `alls-green-*` checks still **green**.
