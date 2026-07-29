# 🪄 Megans Magische Meesters

![status](https://img.shields.io/badge/status-experimental-orange)
![python](https://img.shields.io/badge/python-3.x-blue)
![license](https://img.shields.io/badge/license-unlicensed-lightgrey)

> A cozy, deadly card game inspired by D&D — magic, strategy, bluffing and dark rituals.

---

## ✨ At a Glance

- **Project:** A digital card-battle tabletop that tests intelligence, speed, danger and determination.
- **Goal:** Build an approachable web prototype (Django) that scales into tournaments, bot opponents and exportable decks.
- **Repo:** https://github.com/LucasWillemsens/Megans-Magische-Meesters
  
---

## Roadmap

### Current state

Current state captured: a working human-vs-bot match loop (create challenge → confirm → board actions → result) on a Django + Jinja2 + vanilla JS stack, documented under done/. Next steps are prioritized in roadmap/ (battle page polish first).

### Prototype target

Define the prototype target for the project: a reliable 1v1 demo with clear visuals, a readable match flow, and a polished battle experience. Deployment requirements

### Top priority: Battle page polish

Polish the battle page to make the game feel responsive, readable, and exciting.

- [x] Show hologram cards in a dedicated row above the lane cards so the board layout is clearer and holograms stand out, and add a flip hologram that shows a face-up preview when a lane card is flipped.

#### Defer Enemy Turn Calculation

Remove the action-URL board veil again and defer the enemy turn calculation: 'end turn' renders only the player's own moves, and the bot moves are computed in the board GET that renders the enemy phase (after the browser has left the action URL), passed straight into that render via the server-side actionPlays mechanism instead of bot action cookies.

- [x] Remove the board veil end to end: the "obfuscateBoard" context flag, the #boardVeil template block, the .boardVeil CSS rules, the liftVeil()/veil wiring in loadingAnimations.js, and the two veil tests - while leaving action_render, sequence_render and nextUrl (the deferred-result machinery) fully intact.
- [x] Remove the now-dead bot action cookie transport (_set_bot_action_cookies, _has_enemy_play_cookies), rebase the remaining bot-cookie test onto a manually staged foreign cookie, and do the done/ bookkeeping so the generated README stops claiming the board veil exists.
- [x] Defer the enemy turn calculation: boardAction(end_turn) stops running _run_bot_turn(), setting bot action cookies and incrementing roundNumber; instead viewBoard() runs the bots inside the board GET that carries the "enemy" phase cookie - before finished and the boards are computed - and marks the recorded bot actions loading through the existing server-side actionPlays path.

#### Enemy Turn Indicators

There should not be an action log. Enemy turns should work in the same way as if a player had executed them. When the player presses 'end turn' cookies should be created for the enemy actions. Animations should be set up based on the cookies and the player should get a timeframe to view the enemy actions before being redirected to the board url, just like when player draws a card.

- [x] Animate the recorded enemy actions on the board, the same way player actions animate.
- [x] Record each bot action as an animation cookie when the player presses 'end turn', in the same format as player play cookies.
- [x] Give the player a clear timeframe to watch the enemy actions before the board reloads.

#### Implement Draw Card Animation

Animate drawn cards flying from the top of the deck into the player's and enemy's hand, and stop short-circuiting to the result page when the game ends so the turn sequence plays out first. (The action-URL board veil this goal originally added was later reverted and removed - see defer-enemy-turn-calculation.)

- [x] Teach duplicateCard() the player's deck source so a drawn card's clone starts at the top of the deck stack and flies into its hand slot, showing the card back during the flight - mirroring the enemy draw animation that already works.
- [x] Stop viewBoard() from redirecting to the result page mid-sequence: game-ending actions render their animations, the turn-phase chain plays out ("move through the turns and move cards over until special moves play"), and the final JS navigation targets /result/ instead of the board.
- [x] Record the player's draw in boardAction() as a first-class play with the deck card as animation source, so the drawn hand card renders loading with a negative data-source-lane (mirroring the existing bot draw flow).

#### Lane Card Stacking

Render multiple cards in a lane with a consistent partly stacked visual style, also update hologram cards to match this style.

- [x] Change `.cardRow` from flexbox layout to absolute-positioned overlapping cards with ordinal-based z-index and small random rotation angles.
- [x] Apply the same stacking layout, multi-row overflow, and hover behavior from the previous subgoals to the `.hologramRow` elements. Currently holograms in the hologram row use `display: flex; flex-wrap: nowrap;` (from `cardDragDrop.css`), which lays them side-by-side without overlap. They should match the lane card stacking style: absolute positioning, ordinal-based z-index, small random rotation, overflow to multiple rows, and hover-to-front.
- [x] When a lane card is hovered, bring it fully into view before any card that overlaps it — matching the behavior of hand cards. Cards with lower ordinal (behind the hovered card) stay hidden underneath; cards above (higher ordinal) are pushed aside or visually appear behind the hovered card.
- [x] Add JavaScript logic that measures available lane width on page load and window resize, calculates how many overlapping cards fit per row, and splits excess cards into additional `.cardRow` elements below the first row.

#### Special Draw Sequence

Animate specials with correct sequences, activated when the last card is drawn from a deck. Play special move animations in order while highlighting the active lane special, and show a shuffle-back effect at the end before starting the next player's / enemy turn.

- [x] Transport the server-built timeline to the client and implement a step-by-step sequencer in JavaScript that plays each timeline step sequentially, waiting for animations to finish before advancing to the next step.
- [x] Integrate bot specials into the same timeline pipeline so enemy special sequences animate identically to player special sequences. The enemy-phase GET in viewBoard() calls _run_bot_turn(), which must now produce timeline steps for bot specials just like boardAction does for player specials.
- [x] Implement per-special vignette animations: banner display with the existing sentence-style messages from views.py print statements, lane highlighting for the winning stat, and card-specific visual effects (flight, flip, trust glow, attack flash). Each special kind (int, spd, vis, res) gets its own look and feel while sharing the common sequencer infrastructure.
- [x] Create a server-side timeline data structure that records what happens during special execution as a flat, ordered list of steps. Modify specialActions(), intSpecial(), spdSpecial(), visSpecial(), resSpecial(), and shuffleBoard() to produce timeline steps instead of (or in addition to) their current side-effect execution. Flatten the spdSpecial recursion so opponent specials produce steps in the same timeline.
- [x] Animate the shuffle-back effect that sweeps all untrusted face-up board cards and hand cards back into the deck after a special sequence completes. Show a deck-shuffle wiggle after all cards return. The wave must compress as the card count grows so a huge shuffle never drags.
- [x] Write unit tests for the timeline construction pipeline. Verify that a last-card draw produces the expected ordered step list for each special type, that spdSpecial recursion flattens correctly, that shuffle-back steps contain the right cards, and that the timeline integrates with the existing actionPlays/loading pipeline without breaking existing tests.

#### Turn Affordances

Display clear turn affordances for draw, play, and flip actions so the player understands what they can do and why. Use the existing stats calculation and subtract plays already made by user. Grey out the moves the player can't make anymore this turn: no more draw -> grey out deck. No more flip -> grey out cards in lanes. No more plays -> grey out cards in hand and tilt them slightly upwards. Add a blocked mouse pointer on hover of these elements. Hide the ugly text and numbers from sight (but keep them for testing).

- [x] Grey out the deck, hand cards and face-down lane cards when their action budget is exhausted — with `cursor: not-allowed` on hover and rule-teaching tooltips ("Draw limit reached (Intelligence + 1 per turn)") — tilt blocked hand cards slightly upwards, hide the d/p/f counter text (kept in DOM for tests), and make the server-rendered blocked state non-interactive.
- [x] Keep the affordances truthful while the player stages cookie plays/flips client-side: `cardDragDrop.js` tracks staged plays/flips against the `#turnLimits` budgets (same formulas), blocks the hand/lane cards/deck the moment a budget runs out mid-turn, and refuses new drags/flips once blocked.
- [x] Compute remaining draw/play/flip allowances from the existing getStats() turn-limit formulas, expose them to the board template as a hidden #turnLimits data block (the backend→frontend contract for all affordance work), and pin parity with the enforcement checks in drawCard()/playCard().


### Pre-battle and deck flow

Build the pre-battle experience, including deck ordering, challenge management, active games, and deck metadata.

- [ ] Show active games in the UI instead of only pending challenges, making it easier to discover and resume live play.
- [ ] Support canceling a pending challenge cleanly in the UI.
- [ ] Allow the player to set a custom deck order before battle begins.
- [ ] Add roaming challenge flow so players can send and accept challenges while traveling, including trusted card and deck order adjustments.

#### Deck page

Create a deck page that lets players manage decks with ordering, artwork, metadata, and creation support.

- [ ] Show card artwork previews on the deck page to make each deck easier to scan and personalize.
- [ ] Support creating new decks from the deck page to let players experiment with multiple strategies.
- [ ] Add drag-and-drop deck ordering to make reordering cards intuitive and efficient.
- [ ] Allow deck name and description editing so players can label their decks clearly.

#### Game page metadata

Improve game page metadata so each match feels like a distinct playable entry.

- [ ] Ensure bot rematches shuffle the board and use a fresh deck automatically.
- [~] Add artwork, name, and description support to the game page to make matches easier to identify. _(Artwork (Game.artSource with fallback image) and an auto-generated name ("<challenger> vs <opponent>" title) are shown on the game page; a game description field is still missing.)_
- [ ] Make the "Play again" action create a new challenge instead of reusing the old one.

#### History Page

Move completed games and challenges into a dedicated history page for better post-game navigation.

- [ ] Record a per-round snapshot of each participant's board as a battle log so completed games can be reviewed round by round.


### Tests and reliability

Add tests and reliability work to make the prototype stable before sharing. Create more cards for testing and automate complete end-to-end tests using a real front-end in addition to unit testing.
Also add an efficient way to create cards in general and allow use efficient client computed assets. These can be especially usefull for testing or as a fallback when asset loading fails.

- [ ] Add tests for active game discovery so live sessions are shown accurately in the UI.
- [ ] Test challenge send, cancel, accept, and resolution paths to ensure reliable match setup.
- [ ] Prevent duplicate confirms and accidental double submit behavior in challenge and game flows.
- [ ] Build and verify the full match loop so a game can be played from start to finish without breaking.
- [ ] Make shuffleBoard return cards to the deck in a random order instead of queryset order so deck exhaustion shuffles stay fair.

### Multiplayer and account model

Clarify multiplayer and account behavior to support both asynchronous battle flow and secure identity.

- [ ] Prevent cookies from consuming state incorrectly when the opponent is not active.
- [ ] Consider encrypting frontend account keys before sending them to the server to protect account operations.
- [ ] Resolve special actions correctly when more than two participants are in a game, checking every opponent's status before chaining effects.
- [ ] Implement login through secure account links or email key tokens for account-based play.
- [ ] Clarify turn order, allow asynchronous play, and define reset behavior when a player is not active.
- [ ] Define win and loot rules, including split loot, card returns, lootpile drafting, and passing behavior.

### Low priority

#### Customization and card systems

Develop customization systems that grow the game beyond simple battles, including symbol-driven behavior, links, upgrades, and future card-soul mechanics.

- [ ] Consider AI-assisted image generation and approval workflows for creating unique card upgrades.
- [ ] Make card links followable via middle-click to support quick navigation and preservation of the current board.
- [ ] Remember recent symbol history instead of only the last symbol to support richer upgrade and action mechanics.
- [ ] Explore card-soul and trial mechanics as a future expansion path for manifesting cards and symbols.
- [ ] Design how symbols modify special actions and gate upgrades, so cards evolve meaningfully over time.
- [ ] Define upgrade requirements based on symbol history, card art, or card name to make special upgrades feel earned.

#### Sound design

Add sound design to support the game's atmosphere, feedback, and rhythm.

- [ ] Balance audio levels and playback triggers so sound effects are satisfying without overpowering the gameplay.
- [ ] Add supportive interaction sounds such as paper shuffle, writing, clicks, sparkles, and rolls.
- [ ] Record and integrate sound effects for draws, plays, challenges, holograms, wins, and losses.


### Later actions

Capture later action items that improve match polish and post-game flow after the core prototype is stable.

- [ ] Improve click and drag interactions across hand, lanes, and board for more natural gameplay control.
- [ ] Finish win rules and show the lootpile on the results screen so victory feels complete and transparent.
- [ ] Implement pursuit and flee rules for chase sequences in multiplayer battles and split-out outcomes.
- [ ] Offer a rematch when games are even and all cards are on the board, making tied matches feel satisfying.
- [~] Add load, refresh, sync, and lane flip animations for smoother state updates and board transitions. _(Play-to-lane movement animations via .duplicate card clones and the post-action board reload are done; refresh, sync and lane-flip visuals remain.)_
- [ ] Replace random card selection in special actions with deliberate tactical choices so specials feel intelligent for bots and meaningful for players.

### Refactor: parallel project

Rebuild the project as a clean parallel codebase with every existing feature present, refactored into readable, testable modules with less code clutter and no duplicate lines.

- [ ] The rules of the game should become mostly dynamicly loaded. For example: the amount of starting draw / play / flip a player can play during its turn should be configurable.
Also, The maximum number of cards a player can hold in their hand or have in their deck should be configurable as well.
When the specials are executed is another rule that is now hardcoded to be when a player draws their last card in the deck, but this should work based on a trigger. Drawing your last card should fire this trigger by default, but other events should also be able to trigger it.
When the game is lost should be a rule. Right now, it is when someone escapes sucessfully. The others lose at that moment. Or when someone uses the visciousness special successfully, they win. When someone does not have enough resolve during their visciousness special, they lose however. These rules should be configured as defaults but be able to be changed in game.
There should also be a setting to activate losing your trusted cards after a game. When enabled, the cards you trust during your game should be captured in the lootpile. The winner gets the cards lootpile. When someone escapes, they get their own cards back from the lootpile, but they manage to steal one of the cards of their opponent from the lootpile. The amount of cards stolen should also be configurable.
Any setting like this should be stored as a rule in a new database table called rules.
- [ ] Prove the parallel project has every existing functionality by porting the test suite and completing a feature-parity checklist.
- [ ] Create the parallel Django app skeleton that hosts the refactored codebase alongside the existing MMM app.
- [ ] Rebuild the Jinja2 templates in the parallel app with shared macros and includes so no card or board markup is duplicated.
- [ ] Rebuild the view layer in the parallel app as a package of focused modules where thin views delegate to unit-testable game-logic functions.

### Battle Interaction

Battle board rendering and the cookie-driven play/flip/animation system. Template: MMM/jinja2/MMM/battle/viewBoard.jinja2. Frontend: var/www/static/cardDragDrop.js, cardDragDrop.css, loadingAnimations.js, cards.css.

- [x] viewBoard.jinja2 renders enemy boards (name, deck/hand counts, lanes with face-down backs, revealed smallCards, trusted-card rows) above the player board: four lanes each with a cards row, a lane value (revealed count) and a trustedCards row, a deck stack whose last card carries the Draw button, the hand, per-turn drawn/played/flipped counters, and the End turn form.
- [x] Clicking a face-down card container on the player board (or a hologram) writes a flip cookie (flipFaceUp=true) targeting its current lane and reveals the card client-side; the server applies the reveal on the next action POST. Listeners are one-shot ({once: true}) so a card can only be flipped once per render.
- [x] cardDragDrop.js appends a drop-zone div to each player lane; dragging a hand card highlights all zones, dropping removes the card from the hand DOM, adds a hologram preview to the zone, and writes a play cookie for the card id. Nothing is submitted until the next action POST.
- [x] On drop, a face-down non-draggable copy of the card is appended to the lane's drop-zone as a .hologram; cardDragDrop.css stacks holograms with nth-child left offsets so multiple pending plays peek out of one zone. Holograms are excluded from normal face-down click handling and get their own one-shot click-to-flip listener.
- [x] After an action, _addLoadingAnimations() parses the consumed cookies into plays and marks the affected GameCards cssClass="loading" with their source lane/ordinal (_update_played_cards, _update_drawn_hand_cards). loadingAnimations.js clones each .loading element back into its source position (.duplicate), CSS transitions the clone to the card's new position (.to-original with --move-x/y in cards.css), hides the original, then redirects to the clean board URL after (element count × delay / 2) ms.
- [x] Plays and flips are staged client-side as cookies: name = GameCard id, value = URL-encoded JSON {laneValue, sourceLane, sourceOrdinal, flipFaceUp}, path-scoped to the board URL. On the next action POST, playcards() executes each cookie as participant.playCard(); _parse_play_cookie_value() also accepts the legacy "<lane>f" format. _render(clear_cookies=True) deletes all non-session cookies after rendering so stale plays never re-execute.

### Client Side Asset Generation

Allow usage of efficient client computed assets. These can be especially useful for testing or as a fallback when asset loading fails.

- [~] Add CSS rules so the CSS Playing Cards framework rendering (rank/suit classes, rank/suit spans, and the framework's `:after` pseudo-element suit symbols) fits within the existing `.smallCard` layout alongside `.smallCardInfo` without visual overlap or broken sizing. _(Add CSS rules so the CSS Playing Cards framework rendering (rank/suit classes, rank/suit spans, and the framework's `:after` pseudo-element suit symbols) fits within the existing `.smallCard` layout alongside `.smallCardInfo` without visual overlap or broken sizing.)_
- [~] Create Jinja2 filter functions that compute CSS playing card rank/suit classes and default card names from a Card model instance. All go into `mysite/jinja2.py`. _(Create Jinja2 filter functions that compute CSS playing card rank/suit classes and default card names from a Card model instance. All go into `mysite/jinja2.py`.)_
- [~] Update all templates that render card faces to show CSS playing card markup (from the cards.css framework) instead of the fallback placeholder image `1flubeltje.jpg` when `artSource == ""`. The playing card rendering applies the rank class, suit class, rank span, and suit span on the `.card` element so the CSS framework generates the visual appearance. _(Update all templates that render card faces to show CSS playing card markup (from the cards.css framework) instead of the fallback placeholder image `1flubeltje.jpg` when `artSource == ""`. The playing card rendering applies the rank class, suit class, rank span, and suit span on the `.card` element so the CSS framework generates the visual appearance.)_

### Core Data Model

Data layer for players, cards, decks, games, and in-play card state. Django models in MMM/models.py with migrations 0001–0014.

- [x] CardState (inDeck, lane, laneOrdinal, faceDown, trusted) tracks a card in play. Lane semantics: <0 = position in deck (more negative = deeper), 0 = hand, 1–4 = play lanes. Guarded transitions: draw() deck→hand, play() hand→lane, reveal() face-down→face-up, trust() locks a revealed lane card, shuffleBack() resets an untrusted revealed card to the deck, updateOrdinal() sets position. GameCard (card/game/user/state FKs + cssClass scratch field for animations) is the per-game instance of a Card, deleted when the game completes.
- [x] Deck (title, description, artSource, cards M2M, player FK) groups cards for battle. Deck.create() defaults to the player's full collection with generated title/description. Deck.available() returns false when any card is no longer owned or already in use as a GameCard.
- [x] Game (title, artSource, history FK, roundNumber, freeForAll) is the master object; BattleHistory (challenger FK, participants M2M, lootPile M2M of Cards) stores participants and loot; BattleParticipant (player/startingCard/deck FKs; joinedBattle; fled, defeated, computerControlled flags; per-turn counters drawn/played/flippedCardsAmount) links a player to one battle. Factories: createHuman, createRobot, createRandomDeck (min 3 cards incl. starting card), addHumanChallenger/addRobotChallenger (starting card joins the lootPile).
- [x] Player (name, profilePictureSource), Symbol (iconName, effectDescription), and Card (title, artSource, cardType 0–3 = Intelligence/Speed/Viciousness/Resolve, symbols M2M) are modeled. CardOwnerHistory records each ownership acquisition; Player.getKnownCards() returns every card ever owned, getCollection() filters to cards whose latest owner is the player.

### Game Mechanics

Turn rules, lane stats, special actions, bot turns, and win detection. Lives in MMM/models.py (BattleParticipant methods) and MMM/views.py (special actions, bot turn, game result).

- [x] Challenged players join as computerControlled BattleParticipants with an auto-built random deck (createRobot). _run_bot_turn() in views.py runs when the human ends their turn: each bot draws when its hand is empty (special + shuffle on empty deck), plays its first hand card face-up, then calls resetTurn().
- [x] When a draw empties the deck, specialActions() runs and then shuffleBoard() returns all untrusted revealed board cards plus all hand cards to the deck (CardState.shuffleBack → reset). Trusted cards stay on the board, so decks never run dry and trusted progress is preserved.
- [x] BattleParticipant.getStats() counts the participant's revealed (face-up) cards per lane: intCount/spdCount/visCount/resCount, plus derived tactics (int+spd), power (vis+res), and influence (tactics+power). All turn limits and special actions read these stats.
- [x] specialActions(participant) fires when a participant draws their last deck card; the dominant lane stat wins (ties checked int → spd → vis → res). intSpecial plays random hand cards face-up ("master plan"); spdSpecial rushes a lower-power opponent (firing the opponent's specials) or flees from a slower opponent; visSpecial attacks — without a trustable resolve card the attacker is defeated, otherwise a lower-resolve opponent is defeated and a resolve card is trusted; resSpecial trusts up to resCount random revealed cards. Flee/defeat set flags on BattleParticipant.
- [x] Per-turn counters on BattleParticipant gate actions: draws limited to intCount+1 (shrinks when over-playing speed), face-up flips to spdCount+1 (shrinks when over-playing intelligence), plays to 2+tactics minus cards already drawn/flipped. Exceeding a limit raises an exception that surfaces as an on-board error message. resetTurn() zeroes the counters on end turn.
- [x] _game_result() ends a free-for-all game when at most one participant is neither fled nor defeated; the last active participant wins, everyone fleeing counts as a draw. viewBoard redirects to viewResult once finished; viewResult (battle/viewResult.jinja2) shows winners/losers/draw, the participant list, and a Play again link back to the player page.

### Hologram Row

Show hologram cards in a dedicated row above the lane cards so the board layout is clearer and holograms stand out, and add a flip hologram that shows a face-up preview when a lane card is flipped.

### Test Coverage

Automated tests for the battle flow, all passing via `python3 manage.py test`.

- [x] MMM/tests.py BattleFlowTests (4 tests, passing): challenge confirm is idempotent (no duplicate GameCards), drawing never duplicates hand cards, the play-cookie JSON payload parses source lane/ordinal correctly, and end_turn advances roundNumber while the bot plays a card.

### Turn Affordances

Display clear turn affordances for draw, play, and flip actions so the player understands what they can do and why. Use the existing stats calculation and subtract plays already made by user. Grey out the moves the player can't make anymore this turn: no more draw -> grey out deck. No more flip -> grey out cards in lanes. No more plays -> grey out cards in hand and tilt them slightly upwards. Add a blocked mouse pointer on hover of these elements. Hide the ugly text and numbers from sight (but keep them for testing).

- [x] Grey out the deck, hand cards and face-down lane cards when their action budget is exhausted — with `cursor: not-allowed` on hover and rule-teaching tooltips ("Draw limit reached (Intelligence + 1 per turn)") — tilt blocked hand cards slightly upwards, hide the d/p/f counter text (kept in DOM for tests), and make the server-rendered blocked state non-interactive.
- [x] Keep the affordances truthful while the player stages cookie plays/flips client-side: `cardDragDrop.js` tracks staged plays/flips against the `#turnLimits` budgets (same formulas), blocks the hand/lane cards/deck the moment a budget runs out mid-turn, and refuses new drags/flips once blocked.
- [x] Compute remaining draw/play/flip allowances from the existing getStats() turn-limit formulas, expose them to the board template as a hidden #turnLimits data block (the backend→frontend contract for all affordance work), and pin parity with the enforcement checks in drawCard()/playCard().

### Web Flow

Page flow from landing to a finished match: index → player page → create challenge → initialize → game detail/confirm → board → result. URLs in MMM/urls.py, views in MMM/views.py, Jinja2 templates in MMM/jinja2/MMM/.

- [x] boardAction (POST to /game/<id>/board/<player>/action/) first executes pending play cookies via playcards(), then applies action=draw (drawCard; special + shuffle when the deck empties) or action=end_turn (resetTurn, bot turns, roundNumber+1). Rule violations are caught and shown as on-page error messages. The response re-renders the board with loading animations and clears the consumed cookies.
- [x] createGame renders a form (createGame.jinja2): pick an opponent, a deck (or "New" = whole collection), and a trusted starting card. initializeGame (POST) creates the human BattleParticipant, substitutes a fallback opponent when challenging yourself, adds the opponent as a robot challenger, and auto-titles the game "<challenger> vs <opponent>".
- [x] viewGame/viewGameAsPlayer show game details (title, artwork, round, participants) with a confirm button. confirmChallenge calls _ensure_game_initialized: each participant's deck is shuffled into GameCards in deck order and the starting card is drawn, played to its lane, revealed and trusted; roundNumber starts at 1. Idempotent — re-confirming reuses existing GameCards (covered by test), so the confirm link doubles as a resume path.
- [x] index lists all players and the 5 latest cards, plus a ResetGames link (resetGames wipes all game/battle/deck data). viewPlayer shows the player's challenges with lootPile, start time and participants, plus their owned card collection. viewCard shows a single card. base.jinja2 provides favicon and global stylesheets (style.css, cards.css) for every page.
