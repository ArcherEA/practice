# 023 — Dependency updates (Dependabot PR #3 npm group + PR #1 Playwright image)

**Status:** done 2026-11-23 · **Who:** frontend-engineer · **Branch:** `chore/023-dependency-updates` · **Size:** small

## Why
Dependabot opened ArcherEA/practice#3 (npm group, 19 updates) and #1 (`frontend/Dockerfile.playwright` image
`v1.64.1-noble` to `v1.65.1-noble`). The Playwright npm version and the Docker image must match, so both land together.

## Scope
- Apply the bumps from #3 in `frontend/package.json` and `packages/react-email/package.json`; regenerate `bun.lock`.
- Apply the image bump from #1 in `frontend/Dockerfile.playwright`; keep every other Playwright pin consistent.
- Majors (`@hookform/resolvers` 6 to 7, `typescript` 6 to 7): check they work with our tooling. A major that needs more than
  a small, clean fix stays on its current major and becomes a follow-up.
- `frontend/biome.json` `$schema` URL follows the Biome version.
- No new dependencies, no source changes unless a major needs a small fix.

## Acceptance
- `bun run lint` and `bun run build` pass.
- `scripts/generate-client.sh` leaves `frontend/src/client` unchanged.
- `bunx playwright --version` is 1.65.1. The lead runs the Playwright specs at review.

## Result
See the report of the task: `typescript` is held on 6.x (the client generator `@hey-api/openapi-ts` needs the TypeScript JS API, which TS 7 no longer ships).
