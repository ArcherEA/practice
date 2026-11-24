# 024 — Commerce: catalog backend (products, variants, prices, stock, slots)

**Status:** approved 2026-11-23 · **Agent:** backend-engineer · **Branch:** `feat/024-commerce-catalog` · **Needs:** —

## Decisions (agreed with the user, 2026-11-23 — see DECISIONS D20/D21)
| Topic | Decision |
|---|---|
| What we sell | **Digital downloads, physical goods and services (bookings)** — one `Product` with a `type`. |
| Catalog | **Products with variants** (options such as Size / Color), each variant with its own SKU, stock and prices. |
| Currencies | **Several, picked from a list.** Admin sets a price **per currency** per variant; no exchange-rate conversion. Allowed currencies come from `STORE_CURRENCIES`. |
| Bookings | **Fixed time slots** created by the admin (start, end, capacity); a slot is bought like stock. |
| Who manages | **Admins** (`require_role(UserRole.admin)`, superuser included). No new role. |
| Checkout / refunds | Later tasks: guests may buy (027); refunds in the Stripe dashboard (027). |

## Scope
- New module `commerce` (`backend/app/modules/commerce/`), registered like `content`/`community`, enabled via
  `MODULES` (add it to `.env.example` and the local docs). No dependency on other modules.
- **Rich-text descriptions:** product descriptions use the same Tiptap JSON format as posts (D15). Move the body
  allow-list validator from `app/modules/content/body.py` into `app/core/richtext.py` (content then imports it — a
  pure refactor, its tests keep passing) so commerce does not depend on the content module.
- **Models** (one migration; plain VARCHAR enums like `User.role`; money as **integer minor units**, never floats):
  - `ProductCategory` (name, slug, position).
  - `Product`: type `digital|physical|service`, slug (unique), title, description (Tiptap JSON), status
    `draft|published|archived`, category_id (nullable), image file ids (ordered list of **public** image files),
    optional SEO title/description, created/updated, published_at.
  - `ProductOption` (product_id, name, position) with its allowed values — at most 3 options per product.
  - `Variant`: product_id, sku (unique), option values (e.g. `{"Size": "M"}` — must match the product's options; the
    combination is unique per product), `stock` (int ≥ 0 for physical; `null` = unlimited, the default for
    digital/service), `file_id` (digital only: the **private** file delivered after payment), is_active, position.
  - `VariantPrice`: variant_id, currency (lower-case ISO 4217 from `STORE_CURRENCIES`), amount (int minor units, > 0);
    unique (variant, currency). A variant is sold in a currency only if it has a price in it.
  - `ServiceSlot` (service products): product_id, starts_at / ends_at (UTC, timezone-aware), capacity (≥ 1),
    is_active. Booked counts arrive in 027 (sold + held); here capacity is only stored.
- **Money helpers** `app/modules/commerce/money.py`: allowed currencies from settings, minor-unit exponent (hard-code
  Stripe's zero-decimal list, e.g. `jpy`, `krw` — no new dependency), formatting for emails.
- **Settings** (env, documented in `.env.example`, passed in `compose.yml`): `STORE_CURRENCIES` (default `usd`),
  `STORE_DEFAULT_CURRENCY` (default: first of the list), `STORE_TIMEZONE` (default `UTC`, used to show slots),
  `PRODUCT_FILE_MAX_BYTES` (digital product files may be bigger than the 10 MiB member cap; default 100 MiB, admins
  only — reuse the 006 presigned upload flow with this cap; the global storage limit still applies).
- **Admin API** (`/api/v1/commerce/admin/...`): CRUD for categories, products (+ publish / unpublish / archive),
  options, variants, prices, slots. Validation errors are 422 with clear messages: unknown currency, option values
  that don't match, publishing a digital variant without a file, a physical variant without stock, slot end ≤ start,
  identical duplicate slots.
- **Public API** (`/api/v1/commerce/...`, no auth): list published products (filter by category and type, paging),
  product by slug with active variants, prices **in a requested currency** (`?currency=eur`, default the store
  default; variants without that price are marked unavailable), availability (`in_stock`, `stock` for physical,
  upcoming active slots with remaining capacity — equal to capacity until 027), image URLs via the stable public file URL.
- **File safety:** a digital product's file must not disappear when the admin who uploaded it is deleted
  (`File.owner_id` cascades). Handle it (e.g. refuse to delete a user who owns product files, or move ownership to the
  superuser doing the delete) and test it. Product files are never public.
- Tests: roles (anonymous / member / editor / moderator → 403 on the admin API), the validation rules above, currency
  handling including a zero-decimal currency, drafts invisible publicly, module disabled → 404, migration
  up/down/up locally. Apply the migration to **Neon before merging** (DATABASE.md).

## Out of scope
UI (025/026), cart/checkout/orders (027), fulfilment and emails (028), tax, discounts/coupons, reviews, product search.

## New dependencies
None.
