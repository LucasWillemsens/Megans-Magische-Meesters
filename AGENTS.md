# Repository guidance

## Commands
- Run `python3 manage.py check` before `python3 manage.py test`.
- The check currently warns `staticfiles.W004` because configured `assets/downloaded/` is absent; it is ignored by Git.
- Run one test with `python3 manage.py test MMM.tests.BattleFlowTests.test_end_turn_defers_bot_turn_to_enemy_phase_get`. Frontend contract assertions are also in `MMM/tests.py`; there is no separate app frontend test runner.

## Architecture and behavior
- `mysite/settings.py` wires the root URLs to `MMM.urls` and configures Django's Jinja2 backend with `mysite.jinja2.environment`. Templates live under `MMM/jinja2/MMM/`, use Jinja2 syntax, and the environment uses `StrictUndefined`.
- `MMM/models.py` owns game state and rules; `MMM/views.py` orchestrates requests, bot turns, and specials; `MMM/special_timeline.py` builds special-action animation timelines. Board interaction JS/CSS lives in `var/www/static/`.
- Card state uses negative lanes for deck positions (`inDeck=True`), lane `0` for hand, and lanes `1–4` for the board. Card types `0–3` map to lanes `1–4` in order.
- Turn limits are enforced by `BattleParticipant.drawCard()` / `playCard()`; `getTurnAllowances()` feeds the board's `#turnLimits` data and client-side staged-action guards. Keep these limits in sync.
- Plays/flips are staged in cookies keyed by `GameCard` ID with a JSON payload (`laneValue`, `sourceLane`, `sourceOrdinal`, `flipFaceUp`); `boardAction()` consumes them via `playcards()`. On `end_turn`, the POST does not run the bot: it marks the enemy phase, and the next `viewBoard()` GET runs `_run_bot_turn()`. Preserve this phase/animation flow when changing board actions.

## Generated roadmap and CI
- `README.md`'s `## Roadmap` section is generated from `roadmap/` and `done/` by `python3 scripts/update_roadmap.py`; edit those source descriptions instead. The updater also moves flat `done/` entries into the roadmap's nested structure.
- `python3 scripts/ci.py` can fetch, update `done/` and the README, stage **all** changes, commit, push, and open a PR; run it only when explicitly requested. `--dry-run` still runs tests and the README updater, which can move `done/` entries.

## OpenCode
- Root `opencode.json` selects the `devops` agent; roadmap and CI workflow instructions are in `.opencode/agent/devops.md`.
