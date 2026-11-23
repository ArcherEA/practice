# Protecting `main` (GitHub ruleset) and the pull-request workflow

## Ruleset to create
GitHub → repository **Settings → Rules → Rulesets → New ruleset → New branch ruleset**

| Setting | Value |
|---|---|
| Ruleset name | `main` |
| Enforcement status | **Active** |
| Bypass list | empty (or *Repository admin*, for emergencies only) |
| Target branches | **Include default branch** (`main`) |
| Restrict deletions | ✅ |
| Block force pushes | ✅ |
| Require a pull request before merging | ✅ — required approvals **0** while working alone (raise to 1 when others join); allowed merge methods: merge and squash |
| Require status checks to pass | ✅ — add the three checks below; "Require branches to be up to date" optional |

**Required status checks** (type the job names; they appear in the picker after they have run once):

| Check | Workflow | Notes |
|---|---|---|
| `alls-green-backend` | Test Backend | lint/types/tests + 90 % coverage |
| `alls-green-docker-compose` | Test Docker Compose | the full stack builds and starts |
| `alls-green-playwright` | Playwright Tests | end-to-end tests (4 shards) |

Mark the **`alls-green-*`** jobs as required, not the test jobs themselves: each workflow first decides whether
anything besides documentation changed; for docs-only pull requests the test job is *skipped* and `alls-green-*` still
reports **success**, so the PR isn't stuck waiting for a check that never runs. If the tests run and fail,
`alls-green-*` fails too.

Not required (they only run when their files change): *Check requirements.txt*, *Zizmor*. *pre-commit* runs on
pull requests and is advisory.

## Day-to-day workflow with the ruleset
1. Work happens on a branch `feat/NNN-<slug>` (one task file = one branch).
2. Open a pull request into `main` (`gh pr create`, or GitHub's "Compare & pull request" button).
3. CI runs on the PR, and Vercel posts a **preview deployment** link — try the change there before merging.
4. When the checks are green and the change is approved, merge the PR (merge commit or squash) and delete the branch.
5. **Migrations:** apply them to Neon *before* merging the PR (see `docs/DATABASE.md`) — merging deploys to production.
