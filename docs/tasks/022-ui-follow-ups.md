# 022 — UI follow-ups: comment links, moderation paging, return after login

**Status:** done 2026-11-23 · **Agent:** frontend-engineer · **Branch:** `feat/022-ui-follow-ups` · **Size:** small ·
**Needs:** 016 and 017 merged

## Goal
Close three small gaps left by the community UI (016/017) and the login flow, and bring the roadmap up to date.

## Scope (frontend only, no backend changes, no new dependencies)
1. **Scroll to a comment from a link.** Notification and profile links go to `/blog/<slug>#comment-<id>` or
   `/p/<slug>#comment-<id>`. Comments load after the page, so the browser cannot scroll by itself. Once the list has
   loaded, scroll the comment into view and highlight it briefly. Replies are found inside their parent thread; if the
   comment is not on the pages loaded so far, keep loading "Load more" pages until it appears, up to a cap of 10 pages;
   after that stop quietly.
2. **Moderation lists page through everything.** The Reported, Hidden and Suspensions tabs on `/moderation` stop asking
   for `limit=100` and use `skip`/`limit` with a "Load more" button until `count` is reached.
3. **Return to the page after login.** `src/routes/_layout.tsx` (logged-out visitor) and `handleApiError` in
   `src/main.tsx` (session ended) send people to `/login?redirect=<current path>`. Only same-site paths are used
   (`safeRedirect` from `features/auth/redirect.ts`).
4. **Docs:** tick 016 and 017 and mark Phase 3 Community complete in `docs/ROADMAP.md`; set 016 and 017 to done; list
   020, 021, 022 and 023 under Project process.
5. **Playwright:** extend `community.spec.ts`, `community-profiles.spec.ts` and `login.spec.ts`: a notification link
   scrolls to and highlights the comment; moderation "Load more" shows items beyond the first page; a protected page
   visited logged out is shown after login.

## Out of scope
Backend changes, new dependencies, switching the comment sort to find a comment, "jump to comment" beyond the page cap,
redirects for the public-site login links (already handled by 016).

## Acceptance
- Opening a notification or profile link to a comment scrolls it to the middle of the screen and highlights it for
  about 3 seconds, also for replies and for comments beyond the first page.
- Each moderation tab shows 20 items first and loads the rest on request.
- `/login?redirect=...` is used by both logout paths; after logging in the visitor is back on the page; unsafe values
  fall back to `/`.
- `bun run lint`, `bun run build` and the touched Playwright specs pass.
