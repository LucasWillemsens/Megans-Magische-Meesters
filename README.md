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

## 🗺 Roadmap (updated for fastest impressive prototype)

### Current state snapshot

- [x] Core Django data model exists (`Player`, `Card`, `Deck`, `BattleHistory`, `Game`, `GameCard`, `CardState`)
- [x] Basic web flow exists: index -> player -> create challenge -> game -> board
- [x] Deck shuffle + initial game-card creation is partially implemented
- [ ] End-to-end playable match loop is not complete yet
- [ ] Challenge lifecycle (send/cancel/accept) is not complete yet
- [ ] Automated tests are not in place yet

### Prototype target (what "impressive" means)

Ship a reliable 1v1 demo (human vs bot) that can be played from start to finish in under 3 minutes, with clear visuals and a readable match log.

### Phase 1: Lock a playable vertical slice (1-3 days)

- [ ] Make one stable demo route: `create challenge -> confirm -> board -> winner`
- [ ] Auto-add bot opponent when challenge is confirmed (postpone async invites)
- [ ] Implement turn actions with minimal scope:
  - [ ] Draw one card
  - [ ] Play one card to a lane
  - [ ] End turn
- [ ] Show only allowed information (own hand visible, opponent hand hidden)
- [ ] Add one clear win condition and finish screen

### Phase 2: Make it look and feel like a real game (1-2 days)

- [ ] Upgrade board readability (lane labels, active player, card counts, trusted/revealed states)
- [ ] Add compact action log (draw/play/reveal/win)
- [ ] Improve visual identity for demo impact (title bar, consistent palette, stronger card focus)
- [ ] Add one-click "Play again"

### Phase 3: Reliability before sharing (0.5-1 day)

- [ ] Add tests for `CardState` transitions (draw/play/reveal/trust)
- [ ] Add test for deck initialization (no duplicates, starting card handling)
- [ ] Add one smoke test for challenge -> board flow
- [ ] Prevent duplicate confirms / accidental double-submit

### Explicitly postpone (after prototype demo)

- [ ] Full multiplayer accept/cancel notifications
- [ ] Deck builder and card-creation UI
- [ ] Import/export pipeline
- [ ] Tournament systems and deployment variants

### Feedback loop

- [ ] Run 3 focused playtests (including Annabel)
- [ ] Capture friction points after each session
- [ ] Apply top 3 fixes immediately, defer the rest

---


