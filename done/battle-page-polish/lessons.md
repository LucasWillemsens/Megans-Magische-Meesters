# battle-page-polish lessons

## 2026-11-18 — bot deck->lane play rendered its card face broken
- Flight clones appended to `document.body` fall outside the board's `.playingCards` scope, so every card rule scoped to it (`.playingCards .card .rank/.suit` block layout, suit colors, `.suit:after` symbols, `.smallCardInfo` positioning) silently stops applying — the bot's deck→lane play flew a card whose rank and suit collapsed into one unstyled inline line. Flight clones must live inside the board root; only pure card backs can survive on the body via the unscoped `.duplicate-deck-flight .card.back` rules.
- The bot's turn intentionally merges its draw and play of the same card into one deck→lane move via the `plays_by_card` dedupe in `viewBoard` (asserted by `test_enemy_phase_get_runs_bots_and_marks_moves_loading`); the enemy hand stays hidden, so the enemy play is presented deck→lane, not hand→lane.
- Frontend testing methods (Django-client rendered-HTML E2E, node fake-DOM execution of the real static JS, JS/CSS source contracts, board hook reference, future Playwright direction) are catalogued in `frontend-tests.txt` at the repo root — read it before writing board-frontend tests.
