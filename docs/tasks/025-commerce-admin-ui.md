# 025 — Commerce: store admin screens

**Status:** approved 2026-11-23 · **Agent:** frontend-engineer · **Branch:** `feat/025-commerce-admin-ui` · **Needs:** 024 merged

## Scope
- New feature folder `frontend/src/features/commerce/` and routes in the app layout, shown only when the `commerce`
  module is on and the user is admin+ (sidebar entry "Store", like Content / Moderation).
- **Products list:** search by title, filter by type / status / category, paging; create a product (type first).
- **Product editor:** title, slug, category, description with the existing Tiptap editor (010), images (reuse the
  content upload + image picker), publish / unpublish / archive, SEO fields.
- **Options and variants:** up to 3 options with their values; generate the variant grid (all combinations) with SKU,
  stock (physical) and an active toggle; per variant a **price per currency** (one input per `STORE_CURRENCIES`
  entry, typed as normal money like `12.50`, sent as minor units; zero-decimal currencies have no decimals).
- **Digital files:** upload the private file per variant (bigger cap from 024), show name and size, replace it.
- **Service slots:** upcoming slots shown in `STORE_TIMEZONE`; add one slot or a simple repeat (e.g. every weekday at
  10:00 for N weeks, created one by one through the API); capacity; deactivate.
- **Categories** screen (create, edit, order, delete).
- API validation errors (422) shown at the right field.
- Playwright `tests/commerce-admin.spec.ts`: a physical product with Size × Color variants and two currencies,
  published; a digital product with a file; a service with slots; a member cannot open the store admin.

## Out of scope
Storefront (026), orders (028).

## New dependencies
None expected (native date/time inputs or existing shadcn components).
