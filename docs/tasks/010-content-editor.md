# 010 — Content module: editor UI (admin side)

**Status:** implemented · **Agent:** frontend-engineer · **Branch:** `feat/010-content-editor` · **Needs:** 009 merged

## Why
Editors need screens to write and manage posts, pages, categories and tags.

## Scope
- Feature folder `frontend/src/features/content/` + routes under the logged-in layout, e.g. `/content/posts`,
  `/content/posts/$id`, `/content/pages`, `/content/pages/$id`, `/content/taxonomy` (categories + tags).
  Guarded with `requireModule("content")` **and** an editor+ check (editor, admin, superuser); sidebar entry
  "Content" via `moduleNavItems`, visible only to editor+.
- **Lists:** title, status badge (Draft/Published), category, updated date; filter by status; search by title.
- **Editor screen:** title, slug (auto from title, editable), excerpt, category select, tags (create on the fly),
  cover image (upload via `useFileUpload`, `public: true`), SEO title/description with character counters,
  body editor, Save draft / Publish / Unpublish / Delete (confirm dialog), unsaved-changes warning.
- **Body editor: Tiptap** (open-source MIT packages only — no Tiptap Pro/paid extensions): StarterKit (headings 1–3,
  lists, blockquote, code block, bold/italic/strike/code, horizontal rule), Link (http/https/mailto only), Image,
  Placeholder. Toolbar with those actions. **Insert image** uploads through `useFileUpload` (`public: true`, images
  only) and inserts an image node with `attrs.fileId` (+ display `src` from the API). Output matches the backend
  allow-list from task 009 exactly.
- Preview toggle that renders the body read-only with the same component task 011 will use publicly
  (put the read-only renderer in `features/content/` so 011 reuses it).
- Playwright: editor creates a post with heading, list, link and image → publishes → it appears as Published;
  member doesn't see Content in the sidebar and `/content/posts` is not accessible.

## Out of scope
Public pages and SEO (011), autosave, collaborative editing, scheduled publishing, revisions.

## New dependencies (MIT, from the Tiptap open-source packages)
`@tiptap/react`, `@tiptap/pm`, `@tiptap/starter-kit`, `@tiptap/extension-link`, `@tiptap/extension-image`,
`@tiptap/extension-placeholder` — the most-used headless React editor, Tailwind-friendly, already chosen in D5.

## Acceptance criteria
- Lint + build pass; Playwright specs for the touched flows pass (tiered rules in `CLAUDE.md`).
- A post written in the editor round-trips (save → reload) without losing formatting; the backend accepts every node
  the toolbar can produce.
