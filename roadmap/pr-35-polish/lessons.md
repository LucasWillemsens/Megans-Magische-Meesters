# pr-35-polish lessons

## 2026-11-25 — UX decisions confirmed by the user
- Enemy-phase End turn stays usable and acts as the working Skip button (disabled-button-affordance × enemy-turn-skip reconciliation).
- Draw stays available during the `playerMoves` animation; it is blocked only at zero draw allowance, empty deck, or a waiting special.

## 2026-11-25 — trusted-cards-sideways
- Board presentation composes through `--card-rotation`: the trusted sideways look is a `--card-rotation: 90deg` declaration scoped to `ul.cardRow[title="trustedCards"] li.cardContainer.trustedCard`, picked up by the base `.playingCards ul.cardRow li.cardContainer` transform — inline `--card-rotation` styles (like the old per-card wiggle) would override any class-scoped rule, so class-driven card presentation must not compete with inline rotation styles in the templates.
- Trusted rows are non-interactive by contract: no `tabindex`/`draggable` in their markup and no `:focus-within`/`.card-hover` CSS selectors for trusted rows — `test_trusted_cards_have_no_focus_or_hover_styling` guards it, so presentation-only changes there must not add interaction affordances.

## 2026-11-25 — disabled-button-affordance
- Disabled controls need truthful, state-specific explanations; derive the end-turn disabled reason from the active animation/special state and preserve a usable Skip control during the enemy phase. Remove dead controls rather than leaving misleading disabled affordances.
- Keep accessible state aligned between rendered markup and client-staged actions. Hand cards blocked by the play budget expose `aria-disabled`; face-down cards remain focusable while blocked, so do not apply `aria-disabled` where keyboard navigation treats it as a disabled-control target.
- When an animation dims or disables pointer events on a containing region, explicitly exempt controls that must remain actionable through that animation.

## 2026-11-25 — enemy-turn-skip
- The enemy phase already has a guarded animation-skip/reload path; reuse it for the Skip control instead of submitting `end_turn` again or changing the server phase/cookie flow. Bind the click handler only in the enemy-phase branch.
- Phase-critical controls must escape ancestor dimming as well as animation-handler restrictions; test visibility, pointer activation, single-reload behavior, and phase/cookie continuity together.

## 2026-11-25 — lanes-layout-contract
- Preserve responsive layout contracts by asserting effective overrides, not just the base rule: mobile width, padding, and gap can be explicitly restored after desktop lane changes, while higher-specificity enemy-board padding remains independently effective.
- Equal-width flex lanes should be expressed via shared flex sizing rather than fixed lane widths; contract tests should also guard against a competing max-width.
- Browser-level viewport sizing remains a separate visual confirmation when static CSS contracts cannot prove rendered dimensions.

## 2026-11-25 — zoom-selection-delay
- Synchronize card lift and zoom entry through one shared CSS timing custom property. A transition alone will not animate a newly inserted clone already styled at its final scale; use an entry keyframe starting at the unscaled state.
- Keep rapid hover transitions and cancellation in the existing clone lifecycle (`release()` removes stale stages); no second JS timer/state path is needed for this presentation timing.

## 2026-11-25 — shuffle-random-draw
- Shuffle the combined eligible board-and-hand card set once, then assign distinct negative deck lanes in shuffled order. Distinct positions ensure `getNextDeckCard()` follows the randomized ordering rather than falling back to an ID tie-break.
- Reuse the same eligible-card query for shuffle execution and animation timeline membership so the visual sequence and model mutation cannot drift. Keep trusted and face-down cards out of the eligible set.
- A drained-deck redraw has two visible legs when the drawn card is swept back: deck-to-hand and then hand-to-deck. Preserve the hand source lane/ordinal in the timeline and let the existing phase sequence reload only after the shuffle animation.
- Satisfies `roadmap/tests-and-reliability/random-shuffle-order`; that parallel goal's completion note records the implementation and the paired regression coverage.

## 2026-11-25 — focus-z-order
- Debug z-order across composed stacking contexts, not by comparing local `z-index` values. The fixed player mat, flex-item deck hand, and root-level enemy region formed separate contexts; raising the enemy region on focus and removing the unnecessary hand context made focus priority work across regions.
- Keep focus, hover, zoom, and root overlays on explicit tiers, with the zoom above focused cards and existing flight/arrow overlays preserved. A focused but blocked face-down card needs a deliberate stacking rule without changing its keyboard-focus contract.
- DOM/CSS contract harnesses need to model stacking-context boundaries and stylesheet order accurately; equal-specificity declarations use later rule order.

## 2026-11-25 — played-card-ghost-timing
- A staged-play ghost can be applied synchronously yet still appear wrong because of cascade precedence. Diagnose selector specificity and stacking before adding JS state or changing the cookie/action-animation handoff.
- Pin hand ghosts across rest, hover, and focus states with selectors strong enough to preserve their opacity, grayscale, and lower stacking position; leave board ghosts and hologram behavior isolated.
- Existing click-staging source ordinals are inconsistent with drag/keyboard ordinals: click staging writes a zero-based index while other paths use one-based values. `handSourceForOrdinal` currently normalizes only 0→1, so later click-staged cards may animate from one slot too far left. This remains an open follow-up, not changed by the ghost fix.

## 2026-11-25 — board-reload-flash
- Preload the shared backdrop from the same `static()` URL used by the visible image and provide a fallback color close to the image's dominant tone; retain the existing image element and layering to avoid disturbing board action, bot-turn, and animation flows.
- Verify that preload appears in the document head before the image and that every page inheriting the shared demo shell still renders the backdrop.

## 2026-11-25 — board-vertical-scroll
- For short-viewport scrolling, move the player table into document flow only below the height breakpoint while retaining `position: relative` so absolutely positioned end-turn controls remain anchored to the table. Keep the existing width-based mobile block later so its `position: static` override and 100dvh behavior still win.
- Scroll the player-board anchor instantly on DOM ready only for short viewports and non-enemy phases; smooth scrolling would race animation geometry measurement, while the enemy-phase focus path already owns its initial view.
- Source/render and JS harness checks do not prove real browser layout; the 1280×700 and taller-than-breakpoint visual check remains outstanding.
