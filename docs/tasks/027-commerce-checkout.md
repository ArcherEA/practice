# 027 — Commerce: Stripe Checkout, webhooks and orders (backend)

**Status:** approved 2026-11-23 · **Agent:** backend-engineer · **Branch:** `feat/027-commerce-checkout` · **Needs:** 024 merged; **user:** a Stripe account (test-mode keys)

## Decisions
Guests may buy: Stripe Checkout collects the email, and the order is linked to the account when the buyer is logged
in. Refunds are made in the **Stripe dashboard**; our webhook records them. Stripe-hosted Checkout keeps card data
off our servers (D6).

## Scope
- **New dependency:** `stripe` (official Python SDK, MIT) — D21. Wrap it in `app/modules/commerce/payments.py` (create
  a session, verify a webhook) so tests use a fake and nothing else imports `stripe`. Timeouts and error handling on
  every call. Run `scripts/export-requirements.sh` after `uv add`.
- **Settings:** `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `SHIPPING_FLAT_RATES` (e.g. `usd:500,eur:450` in minor
  units, used when the cart has physical items), `CHECKOUT_HOLD_MINUTES` (default 30), `CHECKOUTS_PER_HOUR` (rate
  limit). Document them in `.env.example`, `compose.yml` and `docs/deploy-vercel.md` (Stripe test keys, the webhook
  endpoint `https://<site>/api/v1/commerce/stripe/webhook`, which events to enable). Checkout answers 503 when Stripe
  isn't configured.
- **Models** (migration): `Order` (public order number, user_id nullable, email, currency, status
  `pending|paid|fulfilled|cancelled|expired|refunded|partially_refunded`, subtotal, shipping, total, shipping address
  snapshot, Stripe session/payment ids, **hash** of the guest access token, created/paid at), `OrderLine`
  (product/variant/slot ids plus a **snapshot** of title, options, SKU, unit price, quantity and type), `StockHold`
  (variant or slot, quantity, order_id, expires_at), `StripeEvent` (processed event ids, for idempotency).
- **Availability** = stock (or slot capacity) − sold − active holds, computed under row locks (`SELECT … FOR UPDATE`)
  so two buyers can't both take the last item. The 024 public API now reports real remaining stock and capacity.
- **`POST /api/v1/commerce/checkout`** (anonymous or logged in), body `{currency, lines: [{variant_id, quantity, slot_id?}]}`:
  validate (published, active, priced in that currency, quantity limits, slot in the future), hold stock for
  `CHECKOUT_HOLD_MINUTES`, create a `pending` order, create a Stripe Checkout Session (`mode=payment`, `price_data` from
  **our** prices, `shipping_address_collection` and the flat shipping option only when there are physical items,
  `customer_email` when logged in, the order id in metadata, `expires_at` = end of the hold, success/cancel URLs on
  `FRONTEND_HOST`) and return `{checkout_url}`. 409 lists the lines that are no longer available or changed price.
- **`POST /api/v1/commerce/stripe/webhook`** (no auth, **signature verified** on the raw body):
  - `checkout.session.completed` (and `checkout.session.async_payment_succeeded`) → order `paid`, holds become sold,
    store email and address, create the guest access token, emit an `order_paid` event (028 sends the email);
  - `checkout.session.expired` / `async_payment_failed` → release holds, order `expired`;
  - `charge.refunded` → `refunded` / `partially_refunded` (028 turns downloads off).
  Idempotent (the same event twice changes nothing); unknown events → 200 and ignored. Holds also expire by time, so
  a missed webhook never locks stock forever; add a housekeeping command that marks old pending orders expired
  (DATABASE.md).
- **Order read APIs:** `GET /commerce/orders` (mine), `GET /commerce/orders/{number}` (owner or admin),
  `GET /commerce/orders/by-token/{token}` (guest link), `GET /commerce/checkout/{session_id}/status` for the success
  page to poll; admin list/filter and order detail.
- Tests: availability races (two holds for the last item), currency and price snapshot, shipping only with physical
  items, webhook signature valid/invalid (with `stripe`'s own verification and a test secret — no network),
  idempotency, expiry, refunds, guest token access (wrong token → 404), rate limit, module or Stripe not configured.
  Manual local check with the **Stripe CLI** (`stripe listen --forward-to localhost:8000/api/v1/commerce/stripe/webhook`)
  and the test card `4242 4242 4242 4242`, documented in `docs/` (a dev tool, not a dependency).
- Migration → Neon **before merging**.

## Out of scope
Order UI, downloads, booking confirmations and emails (028); tax (Stripe Tax later); coupons; refunds from our admin.

## New dependencies
`stripe` (MIT) — reason above; recorded as D21.
