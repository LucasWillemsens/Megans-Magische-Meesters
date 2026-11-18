# Pre-battle deck flow scratchpad

## 2026-11-17 — PR review
- State: PR review reports no unresolved actual code-review comments; out-of-band user issues remain to be fixed.
- Discovered: Deck layout fixes restored `.players` to document flow, fit text sizing, and added `playingCards` to the deck card grid; game-page fix removed `.createButton max-height: 6rem`; `play()` now resumes the player's single unfinished game when its board is dealt via `resumable_begun_game()`.
- Decided: Do not redo the landed fixes. Track the rejected page-specific floating backlink and the title-page regression caused by the global `.title` restyle for a later coding pass.
- Next: Make `.backlink` consistent and non-overlapping on every page; repair title-page styling after the global `.title` restyle.

## 2026-11-17 — Title page actually fixed (second attempt)
- State: user reported the title page title still looked wrong after the watermark restore; fixed on the working tree — title now readable, centered, no broken-image glyph; full-suite failure set byte-identical to the 40-test baseline, plus one new GamePageStylingTests contract.
- Discovered: the title page stopped extending demo_shell in October (c7e6aa6), so the demo watermark never had its dark backdrop there — `#d3d3d3` on body `#fafafa` is 1.17:1 contrast, invisible; restoring pre-regression computed styles (the earlier "fix") faithfully restored a broken look. The page also referenced phantom assets never in git: `titlepageartWIP.png` (16×16 broken glyph above the title) and the `title.css` link (404). Body's `flex-wrap: wrap` + `align-content: flex-start` defeats cross-axis auto margins (free space lies outside the shrink-to-fit line), so centering needs a width:100% flex column with `align-items: center`. `favicon.png` is missing repo-wide and is pinned by the pre-existing PlayerPageToBoardEndToEnd failure — leave it or the baseline set changes.
- Decided: title.jinja2 carries plain `title` (watermark stays exclusive to the four demo-art pages, matching the existing test contract) and no phantom art img; `title.css` becomes a real page stylesheet in var/www/static holding the centered `.titlePage` column.
- Next: consolidate with the PR-28 thread into lessons; "computed-style parity with a pre-regression state is not a fix when that state was itself broken — verify the page reads correctly against its actual background" is a rule candidate worth raising with the user.

## 2026-11-17 — Back button and title page fix
- State: Both styling regressions fixed on PR 28; `GamePageStylingTests` updated to the new contracts (plus a `DemoNavigationTests` end-to-end pin); full-suite baseline unchanged at exactly 40 pre-existing failures, identical set.
- Discovered: deck/settings carry their visible content in `demo_content`, so an in-flow backlink rendered at the top of those pages until `base.jinja2` moved `back_button` after `demo_content`; the title-page breakage was the dropped `.title h1{height:50%}` — restored scoped to `.title.demoTitle h1`, and a headless-Chromium computed-style probe confirms identical values to the pre-regression CSS.
- Decided: One global in-flow `a.backlink`; one `.title.demoTitle` watermark carried explicitly by the four demo-art templates (deck, settings, board, result); both `body:has(...)` exceptions and the dead `a#back` rule deleted.
- Next: Consolidate this thread into lessons once PR 28 lands.
