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

## Follow-up (user requests): pages sidebar, no page links in header/footer
- Every public page (`/blog`, `/blog/$slug`, category, tag, `/p/$slug`) has a sidebar (`PublicSidebar.tsx`) with a
  **Pages** section listing published pages (hidden when there are none; current page highlighted).
- A post **timeline** (year/month archive) was added and then **removed at the user's request**, together with its
  `GET /content/posts/archive` endpoint (reverted), so no unused code remains.
- Desktop (`lg`+): two columns, content plus a 17rem sticky sidebar on the right. Narrow screens: sidebar below the content.
- The header keeps only site name, Blog, Log in/Dashboard and the theme switcher (no "More" menu); the footer keeps only
  the copyright line.
- Note: the not-found page (`PublicNotFound`) replaces the whole public layout (pre-existing), so it has no sidebar.
- Tests: `frontend/tests/blog.spec.ts` (no page links in header/footer, sidebar pages only, layout at 375px/1280px).
