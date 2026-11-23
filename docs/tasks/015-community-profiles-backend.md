# 015 — Community: usernames, public profiles, follows and notifications (backend)

**Status:** draft (needs user approval) · **Agent:** backend-engineer · **Branch:** `feat/015-community-profiles` ·
**Needs:** 014 merged

## Scope
- **Usernames** (needed for `/u/<username>`): `User.username` — unique, 3–30 chars `[a-z0-9_]`, case-insensitive
  unique, reserved words blocked (admin, api, blog, content, settings, login, …). Migration backfills existing users
  from their email/full name (+ number on clashes). Chosen at signup (optional → generated) and changeable in Settings
  (at most once per 30 days).
- **Profile fields:** `bio` (≤ 500 chars, plain text). Public profile endpoint by username: display name, username,
  avatar URL, bio, joined date, counts (comments, followers, following), recent visible comments (with the post they
  belong to). Suspended members' profiles still show, marked as such only to moderators.
- **Follows:** follow/unfollow members (not yourself; idempotent), followers/following lists (paginated).
  "Activity of people I follow" endpoint: their recent comments.
- **Notifications** (in-app only, email later): `Notification` (recipient, type, actor, target, created_at, read_at).
  Types: reply to my comment, like on my comment, new follower, moderation action on my comment. Implement the 014
  event hook to create them (no self-notifications; collapse duplicate likes). Endpoints: list (paginated), unread
  count, mark one / all read. Keep 90 days (cleanup command, like `cleanup_files`).
- Tests for username rules + backfill, profile privacy (no email exposed), follow rules, notification creation for each
  event, unread count. Migration up/down/up; apply to Neon before merging the PR.

## Out of scope
UI (017), email/push notifications, blocking/muting, private profiles.

## New dependencies
None.
