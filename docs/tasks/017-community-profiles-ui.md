# 017 — Community: profiles, follows and notifications UI

**Status:** done 2026-11-23 · **Agent:** frontend-engineer · **Branch:** `feat/017-community-profiles-ui` ·
**Needs:** 015 and 016 merged

## Scope
- **Public profile** `/u/$username` (public layout from 011): avatar, display name, @username, bio, joined date,
  counts, follow/unfollow button (logged in, not self), recent comments linking to their posts. Comment authors link to
  their profiles everywhere. Server-side meta tags for `/u/{username}` (title "Name (@username)", description = bio)
  following the 011 pattern. Profiles are **not** listed in the sitemap (privacy); a per-member `noindex` option can
  come later.
- **Settings:** username (with the 30-day rule shown) and bio fields.
- **Following:** followers/following lists on the profile; a "Following" page with recent activity of people I follow.
- **Notifications:** bell in the app header and the public header with unread badge (refresh every 60 s and on window
  focus — no websockets, Vercel-friendly), dropdown with the latest items and "Mark all read", full `/notifications` page.
- Playwright: set username + bio → profile shows them; follow/unfollow; reply/like/follow produce notifications and the
  badge clears after "Mark all read".

## Out of scope
Email/push notifications, real-time updates, blocking/muting.

## New dependencies
None expected.
