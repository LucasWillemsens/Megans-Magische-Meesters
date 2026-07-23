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

## 🗺 Roadmap (updated from OneNote progress and plans)

### Current state snapshot

- [x] Core Django data model exists (`Player`, `Card`, `Deck`, `BattleHistory`, `Game`, `GameCard`, `CardState`)
- [x] Basic web flow exists: index -> player -> create challenge -> game -> board
- [x] Battle board and challenge flow skeleton exists
- [ ] End-to-end playable match loop is not complete yet
- [ ] Challenge lifecycle, roaming challenges, and active-game discovery are not complete yet
- [ ] Visual polish, animations, sound effects and account flow are not implemented
- [ ] Automated tests are not in place yet

### Prototype target

Ship a reliable 1v1 demo (human vs bot) that can be played from start to finish with clear visuals, a readable match flow, and a polished battle experience.

### Top priority: Battle page polish

- [ ] Implement draw-card animation
- [ ] Show hologram cards in a dedicated row above lane cards
- [ ] Stack multiple cards in a lane consistently, matching hologram visuals
- [ ] Animate special draw sequence and shuffle-back effects
- [ ] Highlight lanes when special moves execute
- [ ] Show turn affordances for draw / play / flip actions
- [ ] Add undo support and fallback board reload for cookie-driven games
- [ ] Add enemy-player turn indicators for multiplayer-like flow

### Pre-battle and deck flow

- [ ] Allow custom deck order before battle
- [ ] Support canceling a challenge
- [ ] Add roaming challenge flow: send challenge, accept challenge, adjust trusted card and deck order
- [ ] Show active games in the UI, not only pending challenges
- [ ] Build a deck page with:
  - [ ] drag-and-drop ordering
  - [ ] card artwork previews
  - [ ] editable deck name and description
  - [ ] create-new-deck support
- [ ] Improve game page metadata:
  - [ ] artwork, name, description
  - [ ] "Play again" creates a new challenge
  - [ ] bot rematch immediately shuffles the board with a fresh deck
- [ ] Move completed games and challenges into a history page

### Customization and card systems

- [ ] Design symbol behavior for special actions and upgrade gating
- [ ] Remember recent symbol history instead of only the last symbol
- [ ] Support card links that open with middle-click
- [ ] Explore card-soul / trial mechanics for future expansion
- [ ] Define upgrade requirements by symbol history, card art, or card name
- [ ] Consider AI-assisted image generation and approval workflows for card upgrades

### Multiplayer and account model

- [ ] Clarify battle turn order and async/skip rules for non-active turns
- [ ] Avoid consuming cookie state incorrectly when the opponent is not active
- [ ] Define win and loot rules: split loot, return cards, draft from a lootpile, allow passing
- [ ] Implement login via secure account links or email key tokens
- [ ] Consider encrypted frontend account keys for create/update operations

### Sound design

- [ ] Record and integrate sound effects for card draws, plays, challenges, holograms, wins and losses
- [ ] Add ambient interaction sounds: paper shuffle, writing, clicks, sparkles, rolls
- [ ] Balance audio levels and playback triggers

### Later actions

- [ ] Offer rematch when games are even and all cards are on the board
- [ ] Finish win rules and show the lootpile on the results screen
- [ ] Implement pursuit/flee rules for chase sequences in multiplayer battles
- [ ] Improve drag-and-drop and click interactions across hand, lanes and board
- [ ] Add load/refresh/sync and lane flip animations
- [ ] Sync enemy and bot card actions through cookie/state updates

### Structured goal breakdown

- A branching directory of roadmap stages and individual goal descriptions is available in `roadmap/`.

