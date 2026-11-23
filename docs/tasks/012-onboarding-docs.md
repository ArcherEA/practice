# 012 — A fresh clone can be set up from the README alone

**Status:** approved 2026-11-23 · **Who:** lead (docs/config) · **Branch:** `feat/012-onboarding-docs` · **Size:** small

## Why
The README was still the template's (no tool list, FastAPI Cloud), `development.md` claimed `.env` is tracked (it
isn't — secrets), and `frontend/.env` was never in the repo (our `.env` ignore rule matched it), so a fresh clone
couldn't start without help.

## Scope
- `README.md` for this project: what it is, required/optional tools, a copy-paste **Quick start** that works in
  Windows PowerShell and macOS/Linux shells, where configuration and the database live, links to the other guides.
  Keep the template credit and license.
- `frontend/.env.example` (non-secret dev values) tracked in git.
- `development.md`: `.env` comes from `.env.example`; storage service; commands that don't need `bash`.

## Acceptance criteria
- Clone the branch into an empty folder, follow **only** the README Quick start, and: containers healthy, migrations to
  head, admin can log in via the API and in the browser, an avatar upload works (storage), Items and Admin pages load.
