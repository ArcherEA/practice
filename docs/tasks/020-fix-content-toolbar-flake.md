# 020 — Fix: content editor link tests fail on `main` CI

**Status:** done 2026-11-23 · **Who:** lead (side session) · **Branch:** `fix/020-content-toolbar-flake` · **Size:** small

## Why
After PR #12 and PR #13 merged, Playwright on `main` failed in `frontend/tests/content.spec.ts` (runs 45288036239 and
45291045040, all 3 attempts each time):
- *Every toolbar action round-trips and the backend accepts it*: saved body has no `link` mark
  (`Received set: {"bold", "italic", "strike", "code"}`).
- *Editor writes a post with heading, list, link and image*: preview has no `a[href='https://example.com']`.

The same tests pass on the PR runs, so the failure depends on timing.

## Cause
The CI error snapshots show the linked text is **gone** and the image sits where it was (`paragraph / img / paragraph`).
After "Apply link" the link text stays selected, and Tiptap's `focus()` gives focus back to the editor only on
the **next animation frame**. Under CI load the test's `End` and `Enter` were pressed before that frame. They went to the page instead
of the editor, so the selection never collapsed and the image upload (`insertContent`) **replaced** the selected link
text. The earlier fix (task 019) only covered the selection *before* clicking "Link".

This is a test race, not an editor bug: a person can't press a key within one frame of clicking "Apply link".

## Scope
- `content.spec.ts`: a new `linkLineAndContinue()` helper, used by both tests. It waits until the editor shows the
  link, until the editor is focused again, and until the editor's own cursor sits collapsed at the end of the
  link text. Only then does it press `Enter`. A new `editorCursor()` helper reads the cursor from the Tiptap state.
  None of the assertions got weaker.
- `docs/TROUBLESHOOTING.md`: cause and fix.

## Verified
- Repro: throwaway copies of the old and new spec that slow `requestAnimationFrame` by 300 ms. The old spec fails
  both tests with exactly the CI errors, and the new spec passes.
- `content.spec.ts --repeat-each 20 --fail-on-flaky-tests` (local Chrome channel, whole spec,
  11 tests × 20 + setup): **221 passed**, 0 flaky.
- `bun run lint && bun run build` clean.
