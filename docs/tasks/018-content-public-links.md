# 018 — Make published content easy to find (view/copy links, blog link, pages menu)

**Status:** implemented 2026-11-23 · **Who:** lead (backend endpoint) + frontend-engineer · **Branch:** `feat/018-content-public-links`

## Why
After publishing, editors only see the editing URL (`/content/posts/<id>`); nothing links to the public page
(`/blog/<slug>`, `/p/<slug>`), the app has no link to the public blog, and published pages can't be found at all.

## Scope (all four agreed with the user)
1. **"View on site"** in the post/page editor (published items; drafts show "Not published yet") and a link icon per
   published row in the posts/pages lists — opens `/blog/<slug>` or `/p/<slug>` in a new tab.
2. **"Copy link"** next to it: copies the full public URL (`window.location.origin` + path) with a "Link copied" toast.
3. **"View blog"** link in the app sidebar (editors and everyone when `content` is enabled) and in the Content area header.
4. **Pages in the public menu:** new public endpoint `GET /api/v1/content/pages` (published pages, by title, no body,
   max 100) — done by the lead; the public header (or footer on narrow screens) lists published pages as links.

## Acceptance criteria
- Backend: endpoint returns published pages only, no auth needed; test added; client regenerated.
- Playwright: editor publishes a post → "View on site" opens its public page; "Copy link" puts the public URL on the
  clipboard; a published page appears in the public menu and a draft page doesn't; "View blog" opens `/blog`.

## Follow-up (user requests): plain public layout
After reviewing the pages the user asked to simplify the public site step by step; final result:
- **No page links** in the header (no "More" menu) or the footer, and **no sidebar**. The header keeps only site name,
  Blog, Log in/Dashboard and the theme switcher; the footer keeps only the copyright line; single-column layout.
- Published pages are reached by direct link (`/p/<slug>`) — e.g. via "View on site" / "Copy link" in the editor.
- Tried and removed again at the user's request: page links in the header/footer, a pages sidebar, and a post
  timeline. Their endpoints (`GET /content/pages`, `GET /content/posts/archive`) were removed too — no unused code left.
- Scope item 4 ("pages in the public menu") is therefore **dropped**; items 1–3 stand.
