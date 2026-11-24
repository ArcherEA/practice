# 014 — Community: comments, likes, reports and moderation (backend)

**Status:** implemented 2026-11-23 (approved 2026-11-23) · **Agent:** backend-engineer · **Branch:** `feat/014-community-comments`

## Decisions (agreed with the user, 2026-11-23)
| Topic | Decision |
|---|---|
| Core activity | **Comments on published blog posts** (and pages), with **one level of replies**. Forum and social feed: later. |
| Moderation | **Publish, then moderate:** comments appear immediately; members **report**; moderators/admins **hide**, **restore** or **delete**, and can **suspend** a member from participating. |
| Extras in Phase 3 | Public profiles, likes, notifications, follows (likes here; the rest in 015). |
| Sign-up | **Open sign-up** (already exists); abuse is limited by rate limits + moderation. |

## Scope
- New module `community` (`backend/app/modules/community/`), registered like `content`; enable in `.env.example`
  (`MODULES=items,content,community`) and `compose.yml` passes the two new limits (MODULES is already passed). Depends on
  `content` being enabled (fail at startup with a clear message if `community` is on without `content`).
- **Comments:** `Comment` (id, target type `post`|`page`, target id, author_id, parent_id (null or a top-level comment
  → max depth 1), body (plain text, 1–5000 chars, no HTML/markdown rendering), status `visible`|`hidden`,
  created_at, edited_at, like_count). Only on **published** posts/pages. Authors can edit within 15 minutes and delete
  their own (soft delete: body replaced by "[deleted]" if it has replies, otherwise removed).
- **Likes:** like/unlike posts and comments (one per user per target; idempotent); counts stored for fast lists.
- **Reports:** any logged-in member can report a comment once (reason: spam | abuse | other + optional note).
- **Moderation** (role **moderator**, admin, superuser — `require_role(UserRole.moderator)`; note editor ≠ moderator):
  queue of reported/hidden comments, hide/restore/delete, resolve reports, **suspend/unsuspend** a member from
  participation (a separate `community_suspension` table, so core `User` stays untouched — no effect on login or other modules;
  suspended members get 403 on comment/like/report). Moderators can't act on admins/superusers (same rule as 005).
- **Rate limits** (env vars, DB-count based like uploads): `COMMENTS_PER_USER_PER_HOUR` (default 30),
  `REPORTS_PER_USER_PER_DAY` (default 20) → 429.
- **Public reads:** list comments for a post/page (visible only; hidden shown as "removed by a moderator" placeholder
  when they have replies), with author display name + avatar URL, like counts, and `liked_by_me` when logged in.
- Hooks for notifications (015): emit simple domain events from the service (e.g. `comment_replied`, `liked`,
  `comment_hidden`) through a tiny in-process function that 015 will implement — keep it a no-op here.
- Tests: permissions per role (member / moderator / editor / admin / superuser / suspended / anonymous), depth limit,
  edit window, soft delete, like idempotency, report once, rate limits, moderation can't target admins, module
  disabled → 404. Migration with up/down/up on the local DB. After merge: apply to Neon **before** merging the PR.

## Out of scope
UI (016), profiles/follows/notifications (015), forum/feed, rich text or images in comments, email.

## New dependencies
None.

## Implementation notes (2026-11-23)
Full description: `docs/ARCHITECTURE.md`, section "Community module". Choices made while building it:
- `comment` has `post_id` / `page_id` (exactly one, real foreign keys ON DELETE CASCADE) instead of a polymorphic
  `target_type` + `target_id`, so deleting a post/page deletes its comments in the database. The API still exposes
  `target_type` and `target_id`.
- Comments of an unpublished post are not listed (404, like a draft) and come back on republish.
- Suspended members can still delete their own comments and remove likes (undoing is harmless).
- Reports are unique per (comment, reporter) forever; deleting a comment that has replies closes its open reports.
- Like counters for posts live in `post_like_count`; the content module is unchanged.
