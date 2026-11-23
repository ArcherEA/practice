# 019 — Fix: "Copy link" on non-HTTPS pages and flaky link insertion

**Status:** done 2026-11-23 · **Who:** lead · **Branch:** `fix/019-ci-copy-link-and-link-bar` · **Size:** small

## Why
After PR #9 merged (the `main` ruleset was still *disabled*, so a running Playwright shard didn't block it), CI on
`main` failed:
- **Copy link** always failed in CI: the test browser opens the app at `http://backend:8000`, which is not a secure
  context, so `navigator.clipboard` doesn't exist. The same would happen on an own server without HTTPS.
- **Link insertion** in the editor was flaky (link mark sometimes missing) under CI load.

## Fix
- `PublicLinkActions`: use the Clipboard API on secure pages, otherwise fall back to a temporary `<textarea>` +
  `document.execCommand("copy")`.
- `RichTextEditor`: remember the selection when the link bar opens and re-apply the link to exactly that range.
- Tests wait until the text is really selected before clicking "Link". On insecure pages (CI's
  `http://backend:8000`) the Copy-link test checks the toast only, since the clipboard can't be read back there; on
  secure pages (local) it also checks the copied URL. (A Chromium flag to treat backend:8000 as secure was tried in CI
  and had no effect, so it was removed.)

## Verified
`content.spec.ts` 3× with `--fail-on-flaky-tests`: 34/34 passed; lint + build clean.
