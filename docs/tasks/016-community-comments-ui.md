# 016 — Community: comments, likes, reporting and moderation UI

**Status:** draft (needs user approval) · **Agent:** frontend-engineer · **Branch:** `feat/016-community-comments-ui` ·
**Needs:** 014 merged

## Scope
- **Under each public blog post and page** (`/blog/$slug`, `/p/$slug`): comment list (newest/oldest toggle), one level
  of replies, like buttons (post + comments) with counts, "Report" menu, edit (within 15 min) / delete own comments,
  "removed by a moderator" placeholders. Anonymous visitors read; "Log in to comment" link returns to the post after login.
  Suspended members see a clear notice instead of the form. Character counter (5000).
- **Moderation screen** for moderators/admins/superusers in the logged-in app (`/moderation`, sidebar entry only for
  them, module-guarded): reported and hidden comments with context (post, author, reports), hide / restore / delete,
  resolve report, suspend / unsuspend member.
- Friendly errors for 429 (rate limit) and 403 (suspended) via the existing toast pattern.
- Playwright: member comments + replies + likes; anonymous sees comments but no form; member reports; moderator hides
  and restores; suspended member can't comment; editor (not moderator) has no moderation entry.

## Out of scope
Profiles, follows, notifications UI (017).

## New dependencies
None expected.
