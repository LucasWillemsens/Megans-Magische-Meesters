# mobile-drag-drop scratchpad

## 2026-11-21 — PR #32 review
- State: Touch dragging exists, but the floating clone does not match mouse-drag appearance.
- Discovered: `liftTouchDragCard` moves a cloned `li.cardContainer` directly to `document.body`, losing `.playingCards` card styles and the `div.playerScreen`-scoped `--board-scale`; this also invalidates clone offset math. Mouse dragging uses `setDragImage` and is unaffected.
- Decided: Use a carrier wrapper with `playingCards touch-drag-clone`, copy the computed board scale, position the wrapper, retain its reference for cancellation cleanup, and adapt `.touch-drag-clone` styling to the wrapper.
- Next: Implement in `var/www/static/cardDragDrop.js` and `var/www/static/cardDragDrop.css`, then verify touch and mouse drag appearance and cleanup.
