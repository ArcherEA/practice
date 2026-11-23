# 011 — Content module: public pages and SEO

**Status:** approved 2026-11-23, in progress · **Agents:** backend-engineer (meta injection, sitemap), then frontend-engineer
(public pages) · **Branch:** `feat/011-content-public` · **Needs:** 009 and 010 merged

## Decision (agreed with the user)
**Inject meta tags:** the app stays a single-page app; for public content URLs FastAPI returns the normal `index.html`
with the right `<title>`, description, canonical URL and Open Graph / Twitter tags filled in, so Google and link
previews (Slack, X, WhatsApp…) show the real post. Content itself is rendered by the SPA.

## Scope — backend
- **Spike first (report before building the rest):** prove on **Vercel** (preview deploy) and in **Docker** that a
  FastAPI route like `/blog/{slug}` wins over the static `index.html` fallback, and that the injected HTML still loads
  the app. If Vercel's CDN fallback wins, propose the smallest alternative (e.g. `vercel.json` rewrite of `/blog/*` and
  `/p/*` to the function) and confirm with the lead before continuing.
- Routes (only when the `content` module is enabled): `/blog`, `/blog/{slug}`, `/blog/category/{slug}`,
  `/blog/tag/{slug}`, `/p/{slug}` → built `index.html` with injected tags (HTML-escaped; values from the published
  post/page; unknown or draft slug → same page with `noindex` and a 404 status). Cover image via the stable
  `/api/v1/files/{id}/content` URL.
- `GET /sitemap.xml` (published posts, pages, categories, tags with `lastmod`) and `GET /robots.txt` (points to the
  sitemap; disallow `/content/`, `/admin`, `/settings`, `/api/`).
- A `SITE_URL` setting (public base URL, e.g. the Vercel URL / custom domain) used for canonical and `og:url`.
- In local dev (Vite on :5173) injection doesn't apply — document how to test it (`docker compose watch` on :8000 or
  `bun run build` + `fastapi dev`).

## Scope — frontend
- Public layout **without login** (header with site name, nav links to Blog and published pages, footer) — the app's
  logged-in layout stays as is. Logged-in users see a link to the dashboard.
- `/blog` (paginated list: cover, title, excerpt, date, category), `/blog/$slug` (cover, title, author, date, category,
  tags, body via the read-only renderer from task 010), `/blog/category/$slug`, `/blog/tag/$slug`, `/p/$slug`;
  friendly not-found for unknown slugs. Client-side `head()` keeps `<title>` and description correct during SPA navigation.
- Responsive, readable typography for long text (Tailwind `prose` only if `@tailwindcss/typography` is already
  installed; otherwise simple custom styles — no new dependency without approval).
- Playwright: anonymous visitor opens /blog, opens a post, follows a category and a tag; a draft is not visible;
  page title equals the post's SEO title.

## Out of scope
RSS feed, comments, search, multilingual content, server-rendered HTML for the body.

## New dependencies
None expected (backend uses the standard library for HTML escaping and the sitemap XML).

## Acceptance criteria
- `curl` of a published post URL against Docker **and** the Vercel preview returns HTML containing the post's
  `<title>`, `og:title`, `og:description`, `og:image` and canonical URL; a draft URL returns 404 with `noindex`.
- `/sitemap.xml` lists published content only. Checks and touched Playwright specs pass; CI green.
