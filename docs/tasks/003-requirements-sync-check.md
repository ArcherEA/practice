# 003 — Keep `requirements.txt` in sync with `uv.lock`

**Status:** draft (needs user approval) · **Agent:** backend-engineer · **Branch:** `feat/003-requirements-sync` · **Size:** small

## Why
Vercel installs Python packages from `requirements.txt`, which is generated from `uv.lock`. Dependabot (and any
`uv add`) only updates `uv.lock`, so Vercel would silently deploy old or missing packages. This guards every later task.

## Scope
- Add a script `scripts/export-requirements.sh` that runs the exact `uv export` command from `docs/deploy-vercel.md`.
- Add a CI job (in `test-backend.yml` or a new small workflow) that regenerates `requirements.txt` and fails if it differs from the committed file, with a message telling you to run the script.
- Add the script to `CLAUDE.md` ("after changing backend dependencies, run …").
- Update `.github/dependabot.yml` so the `uv` group no longer opens PRs that can never pass this check, OR document how to fix such a PR (run the script on the PR branch). Pick the simpler option and explain why.

## Out of scope
Changing how Vercel installs dependencies.

## New dependencies
None.

## Acceptance criteria
- CI fails on a branch where `uv.lock` changed but `requirements.txt` didn't, and passes after running the script.
- Current `main` passes.
