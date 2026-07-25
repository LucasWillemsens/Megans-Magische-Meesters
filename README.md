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

Capture the current project state and prioritize the next development steps.

### Prototype target

Define the prototype target for the project: a reliable 1v1 demo with clear visuals, a readable match flow, and a polished battle experience.

### Top priority: Battle page polish

Polish the battle page to make the game feel responsive, readable, and exciting.

- [ ] Show enemy player turn indicators to improve multiplayer-like flow and make it obvious when the opponent is acting.
- [ ] Show hologram cards in a dedicated row above the lane cards so the board layout is clearer and holograms stand out.
- [ ] Create a smooth draw-card animation that visually communicates when a card is drawn from the deck into play.
- [ ] Render multiple cards in a lane with a consistent stacked visual style that matches how hologram cards are shown.
- [ ] Highlight the affected lanes when special moves execute so players can instantly see the result of the action.
- [ ] Animate special draw sequences, detect the last drawn card, play special move animations in order, and show a shuffle-back effect.
- [ ] Display clear turn affordances for draw, play, and flip actions so the player understands what they can do and why.
- [ ] Add an undo button and a fallback board reload path that recovers the player state if the game is driven by cookie data.

### Pre-battle and deck flow

Build the pre-battle experience, including deck ordering, challenge management, active games, and deck metadata.

- [ ] Show active games in the UI instead of only pending challenges, making it easier to discover and resume live play.
- [ ] Support canceling a pending challenge cleanly in the UI.
- [ ] Allow the player to set a custom deck order before battle begins.

### Deck page

Create a deck page that lets players manage decks with ordering, artwork, metadata, and creation support.

- [ ] Show card artwork previews on the deck page to make each deck easier to scan and personalize.
- [ ] Support creating new decks from the deck page to let players experiment with multiple strategies.
- [ ] Add drag-and-drop deck ordering to make reordering cards intuitive and efficient.
- [ ] Allow deck name and description editing so players can label their decks clearly.

### Game page metadata

Improve game page metadata so each match feels like a distinct playable entry.

- [ ] Ensure bot rematches shuffle the board and use a fresh deck automatically.
- [ ] Add artwork, name, and description support to the game page to make matches easier to identify.
- [ ] Make the "Play again" action create a new challenge instead of reusing the old one.

- [ ] Move completed games and challenges into a dedicated history page for better post-game navigation.
- [ ] Add roaming challenge flow so players can send and accept challenges while traveling, including trusted card and deck order adjustments.

### Tests and reliability

Add tests and reliability work to make the prototype stable before sharing.

- [ ] Add tests for active game discovery so live sessions are shown accurately in the UI.
- [ ] Test challenge send, cancel, accept, and resolution paths to ensure reliable match setup.
- [ ] Prevent duplicate confirms and accidental double submit behavior in challenge and game flows.
- [ ] Build and verify the full match loop so a game can be played from start to finish without breaking.

### Multiplayer and account model

Clarify multiplayer and account behavior to support both asynchronous battle flow and secure identity.

- [ ] Prevent cookies from consuming state incorrectly when the opponent is not active.
- [ ] Consider encrypting frontend account keys before sending them to the server to protect account operations.
- [ ] Implement login through secure account links or email key tokens for account-based play.
- [ ] Clarify turn order, allow asynchronous play, and define reset behavior when a player is not active.
- [ ] Define win and loot rules, including split loot, card returns, lootpile drafting, and passing behavior.

### Low priority

### Customization and card systems

Develop customization systems that grow the game beyond simple battles, including symbol-driven behavior, links, upgrades, and future card-soul mechanics.

- [ ] Consider AI-assisted image generation and approval workflows for creating unique card upgrades.
- [ ] Make card links followable via middle-click to support quick navigation and preservation of the current board.
- [ ] Remember recent symbol history instead of only the last symbol to support richer upgrade and action mechanics.
- [ ] Explore card-soul and trial mechanics as a future expansion path for manifesting cards and symbols.
- [ ] Design how symbols modify special actions and gate upgrades, so cards evolve meaningfully over time.
- [ ] Define upgrade requirements based on symbol history, card art, or card name to make special upgrades feel earned.

### Sound design

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
- [ ] Add load, refresh, sync, and lane flip animations for smoother state updates and board transitions.
