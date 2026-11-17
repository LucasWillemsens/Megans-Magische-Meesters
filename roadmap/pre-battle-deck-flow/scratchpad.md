# Pre-battle deck flow scratchpad

## 2026-11-17 — PR review
- State: PR review reports no unresolved actual code-review comments; out-of-band user issues remain to be fixed.
- Discovered: Deck layout fixes restored `.players` to document flow, fit text sizing, and added `playingCards` to the deck card grid; game-page fix removed `.createButton max-height: 6rem`; `play()` now resumes the player's single unfinished game when its board is dealt via `resumable_begun_game()`.
- Decided: Do not redo the landed fixes. Track the rejected page-specific floating backlink and the title-page regression caused by the global `.title` restyle for a later coding pass.
- Next: Make `.backlink` consistent and non-overlapping on every page; repair title-page styling after the global `.title` restyle.

## 2026-11-17 — Back button and title page fix
- State: Both styling regressions fixed on PR 28; `GamePageStylingTests` updated to the new contracts (plus a `DemoNavigationTests` end-to-end pin); full-suite baseline unchanged at exactly 40 pre-existing failures, identical set.
- Discovered: deck/settings carry their visible content in `demo_content`, so an in-flow backlink rendered at the top of those pages until `base.jinja2` moved `back_button` after `demo_content`; the title-page breakage was the dropped `.title h1{height:50%}` — restored scoped to `.title.demoTitle h1`, and a headless-Chromium computed-style probe confirms identical values to the pre-regression CSS.
- Decided: One global in-flow `a.backlink`; one `.title.demoTitle` watermark carried explicitly by the four demo-art templates (deck, settings, board, result); both `body:has(...)` exceptions and the dead `a#back` rule deleted.
- Next: Consolidate this thread into lessons once PR 28 lands.
