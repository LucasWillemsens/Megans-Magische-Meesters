class ShortcutHoldAction {
    constructor({duration = 1000, loadingClass = 'shortcut-hold-loading'} = {}) {
        this.duration = duration;
        this.loadingClass = loadingClass;
        this.timer = null;
        this.target = null;
        this.onComplete = null;
        this.completed = false;
        this.submitted = false;
        this.active = false;
        this.indicatorStates = [];
    }

    start(target, onComplete) {
        const targets = Array.isArray(target) ? [target.at(0)] : [target];
        const validTargets = [...new Set(targets)].filter((element) => {
            return element && typeof element.classList?.add === 'function';
        });
        if (
            validTargets.length === 0 ||
            this.active ||
            this.completed ||
            this.submitted
        ) return false;

        this.target = validTargets[0];
        this.onComplete = onComplete;
        this.completed = false;
        this.submitted = false;
        this.active = true;
        this.indicatorStates = validTargets.map((element) => ({
            element,
            hadLoadingClass: element.classList.contains(this.loadingClass),
            previousAriaBusy: element.getAttribute('aria-busy'),
            previousDuration: element.style.getPropertyValue('--shortcut-hold-duration'),
            previousDurationPriority: element.style.getPropertyPriority('--shortcut-hold-duration'),
        }));
        this.indicatorStates.forEach((state) => {
            state.element.classList.add(this.loadingClass);
            state.element.setAttribute('aria-busy', 'true');
            state.element.style.setProperty('--shortcut-hold-duration', `${this.duration}ms`);
        });
        this.timer = window.setTimeout(() => this._complete(), this.duration);
        return true;
    }

    release() {
        if (this.active) {
            this.cancel();
            return true;
        }
        if (this.completed || this.submitted) {
            this._resetState();
            return true;
        }
        return false;
    }

    cancel() {
        if (!this.active && !this.target && this.timer === null) return false;
        this._clearTimer();
        this._clearIndicator();
        this._resetState();
        return true;
    }

    isActive() {
        return this.active;
    }

    isProtected() {
        return this.completed || this.submitted;
    }

    _complete() {
        if (!this.active || this.completed || this.submitted) return;
        this.completed = true;
        this.active = false;
        this._clearTimer();
        this._clearIndicator();
        this.submitted = true;
        const complete = this.onComplete;
        this.onComplete = null;
        if (complete) complete();
    }

    _clearTimer() {
        if (this.timer !== null) {
            window.clearTimeout(this.timer);
            this.timer = null;
        }
    }

    _clearIndicator() {
        this.indicatorStates.forEach((state) => {
            if (!state.hadLoadingClass) state.element.classList.remove(this.loadingClass);
            if (state.previousAriaBusy === null) {
                state.element.removeAttribute('aria-busy');
            } else {
                state.element.setAttribute('aria-busy', state.previousAriaBusy);
            }
            if (state.previousDuration === '') {
                state.element.style.removeProperty('--shortcut-hold-duration');
            } else {
                state.element.style.setProperty(
                    '--shortcut-hold-duration',
                    state.previousDuration,
                    state.previousDurationPriority,
                );
            }
        });
    }

    _resetState() {
        this.target = null;
        this.indicatorStates = [];
        this.onComplete = null;
        this.completed = false;
        this.submitted = false;
        this.active = false;
    }
}

class RegionNavigator {
    constructor(system) {
        this.system = system;
    }

    regionFor(element) {
        if (!element || typeof element.closest !== 'function') return null;
        if (
            element.closest(
                '.playerScreen .deckHand .hand-scroll ul.hand li.cardContainer, ' +
                '.playerScreen .deckHand ul.hand li.cardContainer'
            )
        ) return 'hand';
        if (element.closest('.playerScreen .lanes .cardContainer')) return 'field';
        if (element.closest('.playerScreen .end-turn')) return 'end-turn';
        if (element.closest('.playerScreen .deckHand .active-deck button.draw')) return 'draw';
        return null;
    }

    firstFieldCard() {
        const cards = Array.from(
            document.querySelectorAll('.playerScreen .lanes .cardContainer[tabindex="0"]')
        );
        if (cards.length === 0) return null;
        cards.sort((a, b) => {
            const ra = a.getBoundingClientRect();
            const rb = b.getBoundingClientRect();
            if (ra.top !== rb.top) return ra.top - rb.top;
            return ra.left - rb.left;
        });
        return cards[0];
    }

    handCardAt(slot) {
        const cards = this.system.orderableKeyboardCards();
        if (cards.length === 0) return null;
        const clamped = Math.max(1, Math.min(slot, cards.length));
        return cards[clamped - 1] || null;
    }

    endTurnButton() {
        return this.system._findEndTurnControl()?.button || null;
    }

    drawButton() {
        return this.system._findDrawControl()?.button || null;
    }
}

class KeyboardSelectionControl {
    constructor({
        parent,
        isPlayableKeyboardCard,
        isStagedGhost,
        isOrderableKeyboardCard,
        isGhostFlipCandidate,
        handCardForId,
        stagedLaneForGhost,
        handCards,
        hasPlayerBoard,
        remainingAllowances,
        keyboardTransitionActive,
        noZeroOrdinal,
    }) {
        this.parent = parent;
        this.system = parent;
        this.navigator = new RegionNavigator(parent);
        this._predicates = {
            isPlayableKeyboardCard,
            isStagedGhost,
            isOrderableKeyboardCard,
            isGhostFlipCandidate,
            handCardForId,
            stagedLaneForGhost,
            handCards,
            hasPlayerBoard,
            remainingAllowances,
            keyboardTransitionActive,
            noZeroOrdinal,
        };
        this.state = this._emptyKeyboardSelection();
        this._focusArrow = null;
        const raw = Number.parseInt(
            document.getElementById('turnLimits')?.dataset.focusedHandCard ?? '',
            10,
        );
        this.persistedHandSlot = Number.isInteger(raw) && raw >= 1 ? raw : 1;
    }

    _emptyKeyboardSelection() {
        return {
            selectedCard: null,
            cardId: null,
            sourceLane: null,
            sourceOrdinal: null,
            laneValue: null,
            currentLane: null,
            hologram: null,
            rotation: null,
            digitBuffer: "",
            ghostFlip: false,
            lanePreviewActive: false,
            mouseSelecting: false,
            hoveredLaneValue: null,
        };
    }

    _isPlayableKeyboardCard_Legacy(card) {
        return this._predicates.isPlayableKeyboardCard(card);
    }

    _isStagedGhost_Legacy(card) {
        return this._predicates.isStagedGhost(card);
    }

    _isOrderableKeyboardCard_Legacy(card) {
        return this._predicates.isOrderableKeyboardCard(card);
    }

    _isGhostFlipCandidate_Legacy(card) {
        return this._predicates.isGhostFlipCandidate(card);
    }

    _stagedLaneForGhost_Legacy(card) {
        return this._predicates.stagedLaneForGhost(card);
    }

    _handCardForId_Legacy(cardId) {
        return this._predicates.handCardForId(cardId);
    }

    _noZeroOrdinal(buffer) {
        return this._predicates.noZeroOrdinal(buffer);
    }

    playableKeyboardCards() {
        const { hasPlayerBoard, keyboardTransitionActive, remainingAllowances, handCards } = this._predicates;
        if (
            !hasPlayerBoard() ||
            keyboardTransitionActive() ||
            remainingAllowances().plays <= 0
        ) return [];
        return handCards().filter(card => this._isPlayableKeyboardCard_Legacy(card));
    }

    orderableKeyboardCards() {
        const { hasPlayerBoard, keyboardTransitionActive, handCards } = this._predicates;
        if (!hasPlayerBoard() || keyboardTransitionActive()) return [];
        return handCards().filter(card => this._isOrderableKeyboardCard_Legacy(card));
    }

    flipKeyboardFocusedCard(event) {
        if (this._predicates.keyboardTransitionActive()) return;
        const card = this._keyboardFlipTarget(event);
        if (!card || event.repeat) return;
        const laneValue = this.parent._laneValueForCard(card);
        if (
            laneValue == null ||
            this._predicates.remainingAllowances().flips <= 0 ||
            card.classList.contains('blocked') ||
            card.closest('.blocked') ||
            card.classList.contains('ghost')
        ) return;
        event.preventDefault();
        this.parent.onFaceDownCardClick(event, laneValue);
    }

    _keyboardFlipTarget(event) {
        for (const candidate of [event.target, document.activeElement]) {
            if (!candidate || typeof candidate.closest !== 'function') continue;
            const card = candidate.closest(
                '.playerBoard ul.cardRow li.cardContainer.faceDown, ' +
                '.hologram.keyboard-staged .cardContainer.faceDown'
            );
            if (card) return card;
        }
        return null;
    }

    _keyboardHologramRow(laneValue) {
        const zone = this.parent.dropZones.get(laneValue)?.element;
        return zone?.closest('li.lane')?.querySelector('.hologramRow') || null;
    }

    _selectGhostFlipCard(card, digitBuffer) {
        const laneValue = this._stagedLaneForGhost_Legacy(card);
        const cardIdInput = this.parent._cardIdInput(card);
        if (!laneValue || !cardIdInput?.value) return false;

        this.clearKeyboardSelection();
        const input = this.parent.playerBoard?.closest('.playerScreen')
            ?.querySelector('form.cardActionForm input[name="focused_hand_card"]');
        if (input) input.value = digitBuffer;
        card.classList.add('keyboard-selected');
        card.dataset.keyboardSelected = 'true';
        card.setAttribute('aria-selected', 'true');
        if (typeof card.focus === 'function') card.focus({ preventScroll: true });
        this.state = {
            selectedCard: card,
            cardId: cardIdInput.value,
            sourceLane: card.dataset.sourceLane || '0',
            sourceOrdinal: card.dataset.sourceOrdinal || '0',
            laneValue,
            currentLane: laneValue,
            hologram: null,
            rotation: null,
            digitBuffer,
            ghostFlip: true,
            lanePreviewActive: false,
        };
        const parsed = Number.parseInt(digitBuffer, 10);
        this.persistedHandSlot = Number.isInteger(parsed) && parsed >= 1 ? parsed : this.persistedHandSlot;
        return true;
    }

    _confirmGhostFlipSelection(event = null) {
        const selection = this.state;
        const card = selection.selectedCard;
        if (!selection.ghostFlip || !this._isGhostFlipCandidate_Legacy(card)) {
            this.clearKeyboardSelection();
            return false;
        }
        if (!this.parent._ghostFlipInteractionAllowed(event)) return false;

        const cardId = selection.cardId;
        const laneValue = selection.laneValue;
        this.parent.createupdateCookie(cardId, laneValue, true, selection.sourceLane, selection.sourceOrdinal);

        const stagedCard = document.querySelector(
            `.hologram[data-staged-for-card-id="${CSS.escape(cardId)}"] .cardContainer`
        );
        if (stagedCard) {
            stagedCard.classList.remove('faceDown');
            const cardFace = stagedCard.querySelector(':scope > .card');
            if (cardFace) cardFace.classList.remove('back');
            stagedCard.removeAttribute('tabindex');
            stagedCard.dataset.stagedFlipped = 'true';
        }
        card.dataset.stagedFlipped = 'true';
        card.classList.add('ghost-flipped');
        this.parent.staged.flips++;
        this.parent.applyTurnAffordances();
        this.clearKeyboardSelection();
        return true;
    }

    selectKeyboardCard(card, digitBuffer = this.state.digitBuffer) {
        const { hasPlayerBoard, keyboardTransitionActive, remainingAllowances } = this._predicates;
        if (!hasPlayerBoard()) return false;
        if (keyboardTransitionActive()) {
            this.clearKeyboardSelection();
            return false;
        }
        if (this._isGhostFlipCandidate_Legacy(card)) {
            return this._selectGhostFlipCard(card, digitBuffer);
        }
        if (remainingAllowances().plays <= 0) {
            this.clearKeyboardSelection();
            return false;
        }
        if (!this._isPlayableKeyboardCard_Legacy(card)) return false;
        const laneValue = this.parent._cardLaneValue(card);
        const holoRow = laneValue ? this._keyboardHologramRow(laneValue) : null;
        if (!laneValue || !holoRow) return false;

        const hologram = this.parent._buildPlayHologram(card, laneValue, true);
        if (!hologram) return false;

        this.clearKeyboardSelection();
        const input = this.parent.playerBoard?.closest('.playerScreen')
            ?.querySelector('form.cardActionForm input[name="focused_hand_card"]');
        if (input) input.value = digitBuffer;
        holoRow.appendChild(hologram);
        card.classList.add('keyboard-selected');
        card.dataset.keyboardSelected = 'true';
        card.setAttribute('aria-selected', 'true');
        if (typeof card.focus === 'function') card.focus({ preventScroll: true });
        const cardIdInput = this.parent._cardIdInput(card);
        this.state = {
            selectedCard: card,
            cardId: cardIdInput.value,
            sourceLane: card.dataset.sourceLane || '0',
            sourceOrdinal: card.dataset.sourceOrdinal || '0',
            laneValue,
            currentLane: laneValue,
            hologram,
            rotation: hologram.style.getPropertyValue('--card-rotation'),
            digitBuffer,
            lanePreviewActive: true,
        };
        const parsed = Number.parseInt(digitBuffer, 10);
        this.persistedHandSlot = Number.isInteger(parsed) && parsed >= 1 ? parsed : this.persistedHandSlot;
        return true;
    }

    moveKeyboardSelection(laneValue) {
        const selection = this.state;
        const parsedLane = Number.parseInt(laneValue, 10);
        if (
            !selection.selectedCard ||
            !Number.isInteger(parsedLane) ||
            parsedLane < 1 ||
            parsedLane > 4 ||
            !this.parent.dropZones.has(parsedLane)
        ) return false;
        if (
            this._predicates.keyboardTransitionActive() ||
            this._predicates.remainingAllowances().plays <= 0 ||
            !this._isPlayableKeyboardCard_Legacy(selection.selectedCard)
        ) {
            this.clearKeyboardSelection();
            return false;
        }

        const holoRow = this._keyboardHologramRow(parsedLane);
        const hologram = this.parent._buildPlayHologram(
            selection.selectedCard,
            parsedLane,
            true,
            selection.rotation,
        );
        if (!holoRow || !hologram) return false;

        if (selection.hologram?.parentNode) selection.hologram.remove();
        holoRow.appendChild(hologram);
        selection.hologram = hologram;
        selection.laneValue = parsedLane;
        selection.currentLane = parsedLane;
        return true;
    }

    confirmKeyboardSelection(laneValue = null) {
        if (!this.state.selectedCard) return false;
        if (
            this._predicates.keyboardTransitionActive() ||
            this._predicates.remainingAllowances().plays <= 0 ||
            !this._isPlayableKeyboardCard_Legacy(this.state.selectedCard)
        ) {
            this.clearKeyboardSelection();
            return false;
        }

        const requestedLane = laneValue == null
            ? this.state.currentLane
            : Number.parseInt(laneValue, 10);
        if (!Number.isInteger(requestedLane) || requestedLane < 1 || requestedLane > 4) {
            return false;
        }
        if (requestedLane !== this.state.currentLane && !this.moveKeyboardSelection(requestedLane)) {
            return false;
        }

        const selection = this.state;
        const card = selection.selectedCard;
        if (
            !card ||
            !selection.hologram ||
            !selection.hologram.parentNode ||
            !this._isPlayableKeyboardCard_Legacy(card) ||
            this._predicates.keyboardTransitionActive() ||
            this._predicates.remainingAllowances().plays <= 0
        ) {
            this.clearKeyboardSelection();
            return false;
        }

        selection.hologram.remove();
        const hologram = this.parent._buildPlayHologram(card, requestedLane, false, selection.rotation);
        this._keyboardHologramRow(requestedLane).appendChild(hologram);
        hologram.classList.add('keyboard-staged');
        hologram.dataset.keyboardStaged = 'true';

        const staged = this.parent._stagePlay(card, requestedLane, hologram, true, selection);
        hologram.dataset.stagedForCardId = selection.cardId;
        if (staged) this._mirrorStagedFocus(card, hologram);

        const faceDownCard = hologram.querySelector('.cardContainer.faceDown');
        if (staged && faceDownCard && this._predicates.remainingAllowances().flips > 0) {
            faceDownCard.setAttribute('tabindex', '0');
        }
        return staged;
    }

    clearKeyboardSelection({removePreview = true} = {}) {
        const selection = this.state;
        const card = selection.selectedCard;
        if (card) {
            card.classList.remove('keyboard-selected');
            delete card.dataset.keyboardSelected;
            if (card.getAttribute('aria-selected') === 'true') {
                card.removeAttribute('aria-selected');
            }
            const activeElement = document.activeElement;
            if (activeElement && (activeElement === card || card.contains(activeElement))) {
                activeElement.blur();
            }
        }
        if (this._focusArrow) {
            this._focusArrow.arrow.remove();
            this._focusArrow = null;
        }
        if (removePreview && selection.hologram?.parentNode) selection.hologram.remove();
        this.state = this._emptyKeyboardSelection();
    }

    cancelKeyboardSelection() {
        this.clearKeyboardSelection();
    }

    resetLaneSelection() {
        const selection = this.state;
        const card = selection.selectedCard;
        if (selection.hologram?.parentNode) selection.hologram.remove();
        if (this._focusArrow) {
            this._focusArrow.arrow.remove();
            this._focusArrow = null;
        }
        this.state = {
            selectedCard: card,
            cardId: selection.cardId,
            sourceLane: selection.sourceLane,
            sourceOrdinal: selection.sourceOrdinal,
            laneValue: null,
            currentLane: null,
            hologram: null,
            rotation: selection.rotation,
            digitBuffer: selection.digitBuffer,
            ghostFlip: false,
            lanePreviewActive: false,
        };
        if (card && typeof card.focus === 'function') {
            card.focus({ preventScroll: true });
        }
    }

    navigate(direction, fromElement) {
        const region = this.navigator.regionFor(fromElement);
        if (region === null) return false;

        let target = null;
        let isHandCard = false;
        if (region === 'hand' && direction === 'ArrowUp') {
            target = this.navigator.firstFieldCard();
        } else if (region === 'hand' && direction === 'ArrowDown') {
            target = this.navigator.endTurnButton();
        } else if (region === 'field' && direction === 'ArrowUp') {
            target = this.navigator.endTurnButton();
        } else if (region === 'field' && direction === 'ArrowDown') {
            target = this.navigator.handCardAt(this.persistedHandSlot);
            isHandCard = true;
        } else if (region === 'end-turn' && direction === 'ArrowUp') {
            target = this.navigator.handCardAt(this.persistedHandSlot);
            isHandCard = true;
        } else if (region === 'end-turn' && direction === 'ArrowDown') {
            target = this.navigator.drawButton();
        } else if (region === 'draw' && direction === 'ArrowUp') {
            target = this.navigator.endTurnButton();
        } else if (region === 'draw' && direction === 'ArrowDown') {
            target = this.navigator.handCardAt(this.persistedHandSlot);
            isHandCard = true;
        }
        if (!target) return false;

        if (isHandCard) {
            const success = this.system.selectKeyboardCard(target, String(this.persistedHandSlot));
            if (success) {
                const parsed = Number.parseInt(this.state.digitBuffer, 10);
                this.persistedHandSlot = Number.isInteger(parsed) && parsed >= 1 ? parsed : this.persistedHandSlot;
            }
            return success;
        }
        target.focus({ preventScroll: true });
        return typeof target.focus === 'function';
    }

    _mirrorStagedFocus(card, hologram) {
        const ghostCard = hologram.querySelector('.cardContainer');
        if (!ghostCard) return;
        card.addEventListener('focusin', () => ghostCard.classList.add('keyboard-selected'));
        card.addEventListener('focusout', () => ghostCard.classList.remove('keyboard-selected'));
    }

    onFocusIn(card) {
        if (!card) return;
        const target = this.parent._focusArrowTarget(card);
        if (!target) return;
        if (
            this._focusArrow &&
            this._focusArrow.source === card &&
            this._focusArrow.target === target
        ) return;
        if (this._focusArrow) {
            this._focusArrow.arrow.remove();
            this._focusArrow = null;
        }
        this._focusArrow = {
            source: card,
            target,
            arrow: this.parent._createFocusArrow(card, target),
        };
    }

    onFocusOut(card) {
        if (!this._focusArrow) return;
        if (this._focusArrow.source !== card) return;
        this._focusArrow.arrow.remove();
        this._focusArrow = null;
    }
}

class CardDragDropSystem {
    constructor() {
        this.draggedCard = null;
        this.dropZones = new Map();
        this.playerBoard = null;
        this.createdDropZones = [];
        this.turnAllowances = { int: 0, spd: 0, tactics: 0, drawn: 0, played: 0, flipped: 0 };
        this.staged = { plays: 0, flips: 0 };
        this.tooltips = { draw: "", play: "", flip: "" };
        this.keyboardListenersBound = false;
        this.keyboardObserver = null;
        this.lastDragEndedAt = 0;
        this.endTurnHold = new ShortcutHoldAction();
        this.drawHold = new ShortcutHoldAction();
        this.init();
    }

    init() {
        const playerBoard = document.querySelector('.playerBoard');
        if (!playerBoard) {
            this.playerBoard = null;
            return;
        }
        this.playerBoard = playerBoard;

        const limitsEl = document.getElementById('turnLimits');
        if (limitsEl) {
            const d = limitsEl.dataset;
            this.turnAllowances = {
                int: this._parseAllowance(d.intCount),
                spd: this._parseAllowance(d.spdCount),
                tactics: this._parseAllowance(d.tactics),
                drawn: this._parseAllowance(d.drawn),
                played: this._parseAllowance(d.played),
                flipped: this._parseAllowance(d.flipped),
            };
            this.tooltips = {
                draw: d.drawBlockedTitle,
                play: d.playBlockedTitle,
                flip: d.flipBlockedTitle,
            };
        }
        this.createDropZones();
        this.setupCardDragListeners();
        this.setupDropZoneListeners();
        this.setupFaceDownCardClickListeners();
        this.setupKeyboardSelection();

        const handCardForId = (cardId) => this.playerHandCards().find(card => {
            const input = this._cardIdInput(card);
            return input && String(input.value) === String(cardId);
        }) || null;

        const isPlayableKeyboardCard = (card) => {
            if (!card || !card.matches('li.cardContainer')) return false;
            if (!this.playerHandCards().includes(card)) return false;
            if (card.closest('.enemyBoard, .enemyDeckHand, .enemyHand')) return false;
            if (card.classList.contains('blocked') || card.closest('.blocked')) return false;
            if (card.classList.contains('ghost') || card.closest('.ghost')) return false;
            if (card.classList.contains('staged') || card.dataset.staged === 'true') return false;
            if (card.classList.contains('loading') || card.closest('.loading')) return false;
            if (card.getAttribute('draggable') !== 'true') return false;
            if (card.matches('[aria-disabled="true"], :disabled') || card.querySelector(':disabled')) return false;
            const cardIdInput = this._cardIdInput(card);
            return Boolean(cardIdInput?.value);
        };

        const isStagedGhost = (card) => {
            if (!card || !card.matches('li.cardContainer')) return false;
            if (!this.playerHandCards().includes(card)) return false;
            if (card.closest('.enemyBoard, .enemyDeckHand, .enemyHand')) return false;
            if (card.classList.contains('blocked') || card.closest('.blocked')) return false;
            if (!card.classList.contains('ghost')) return false;
            if (card.classList.contains('loading') || card.closest('.loading')) return false;
            const cardIdInput = this._cardIdInput(card);
            return Boolean(cardIdInput?.value);
        };

        const isOrderableKeyboardCard = (card) => {
            if (!card || !card.matches('li.cardContainer')) return false;
            if (isPlayableKeyboardCard(card)) return true;
            return isStagedGhost(card);
        };

        const stagedLaneForGhost = (card) => {
            const stored = Number.parseInt(card.dataset.stagedLane, 10);
            if (stored >= 1 && stored <= 4) return stored;
            return null;
        };

        const isGhostFlipCandidate = (card) => {
            if (!card || !card.matches('li.cardContainer')) return false;
            if (!this.playerHandCards().includes(card)) return false;
            if (card.closest('.enemyBoard, .enemyDeckHand, .enemyHand')) return false;
            if (card.classList.contains('blocked') || card.closest('.blocked')) return false;
            if (!card.classList.contains('ghost')) return false;
            if (card.dataset.stagedFlipped === 'true') return false;
            if (card.classList.contains('loading') || card.closest('.loading')) return false;
            if (this.remainingAllowances().flips <= 0) return false;
            if (!stagedLaneForGhost(card)) return false;
            const cardIdInput = this._cardIdInput(card);
            return Boolean(cardIdInput?.value);
        };

        const handCards = () => this.playerHandCards();
        const hasPlayerBoard = () => this._hasPlayerBoard();
        const remainingAllowances = () => this.remainingAllowances();
        const keyboardTransitionActive = () => this._keyboardTransitionActive();

        const noZeroOrdinal = (buffer) => {
            if (!/^[1-9]+$/.test(buffer)) return null;
            let ordinal = 0;
            for (const character of buffer) {
                ordinal = ordinal * 9 + Number.parseInt(character, 10);
                if (!Number.isSafeInteger(ordinal)) return Number.POSITIVE_INFINITY;
            }
            return ordinal;
        };

        this._keyboardSelectionControl = new KeyboardSelectionControl({
            parent: this,
            isPlayableKeyboardCard,
            isStagedGhost,
            isOrderableKeyboardCard,
            isGhostFlipCandidate,
            handCardForId,
            stagedLaneForGhost,
            handCards,
            hasPlayerBoard,
            remainingAllowances,
            keyboardTransitionActive,
            noZeroOrdinal,
        });
        this.applyTurnAffordances();
    }

    _parseAllowance(value) {
        const parsed = Number.parseInt(value, 10);
        return Number.isFinite(parsed) ? parsed : 0;
    }

    remainingAllowances() {
        const { int, spd, tactics, drawn, played, flipped } = this.turnAllowances;
        const { plays: stagedPlays, flips: stagedFlips } = this.staged;
        const effectivePlayed = played + stagedPlays;
        const effectiveFlipped = flipped + stagedFlips;
        return {
            draws: Math.max(0, int + 1 + Math.min(0, spd + 1 - effectiveFlipped - effectivePlayed) - drawn),
            flips: Math.max(0, spd + 1 + Math.min(0, int + 1 - drawn - effectivePlayed) - effectiveFlipped),
            plays: Math.max(0, 2 + tactics - drawn - effectiveFlipped - effectivePlayed),
        };
    }

    get keyboardSelection() {
        return this._keyboardSelectionControl?.state ?? null;
    }

    get control() {
        return this._keyboardSelectionControl;
    }

    playerHandCards() {
        const fanCards = Array.from(document.querySelectorAll(
            '.playerScreen .deckHand .hand-scroll ul.hand li.cardContainer'
        )).filter(card => card.closest('.enemyBoard, .enemyDeckHand, .enemyHand') == null);
        if (fanCards.length > 0) return fanCards;

        return Array.from(document.querySelectorAll(
            '.playerScreen .deckHand ul.hand li.cardContainer'
        )).filter(card => card.closest('.enemyBoard, .enemyDeckHand, .enemyHand') == null);
    }

    playableKeyboardCards() {
        return this._keyboardSelectionControl.playableKeyboardCards();
    }

    applyTurnAffordances() {
        const remaining = this.remainingAllowances();

        if (remaining.plays <= 0) {
            this.clearKeyboardSelection();
            // Staged ghosts stay interactive: they represent cards that were
            // already played and can still be selected to flip face up.
            this.playerHandCards().filter(card =>
                !card.classList.contains('blocked') && !card.classList.contains('ghost')
            ).forEach(card => {
                card.classList.add('blocked');
                card.setAttribute('draggable', 'false');
                card.title = this.tooltips.play;
                card.removeAttribute('tabindex');
            });
        } else {
            this.playerHandCards().forEach(card => {
                if (!card.hasAttribute('tabindex') && this._isPlayableKeyboardCard(card)) {
                    card.setAttribute('tabindex', '0');
                }
            });
        }

        if (remaining.flips <= 0) {
            document.querySelectorAll(
                '.playerBoard .cardContainer.faceDown:not(.blocked), ' +
                '.hologram .cardContainer.faceDown:not(.blocked)'
            ).forEach(card => {
                card.classList.add('blocked');
                card.title = this.tooltips.flip;
            });
        }

        if (remaining.draws <= 0) {
            const deck = document.querySelector('.playerScreen .deckHand .active-deck');
            if (deck) {
                deck.classList.add('blocked');
            }
            const drawBtn = deck?.querySelector('button.draw');
            if (drawBtn) {
                drawBtn.disabled = true;
                drawBtn.title = this.tooltips.draw;
                drawBtn.setAttribute('tabindex', '-1');
            }
        }
    }

    createDropZones() {
        const allLanes = this.playerBoard?.querySelectorAll(':scope > ul.lanes > li.lane') || [];
        allLanes.forEach((lane, index) => {
            const dropZone = document.createElement('div');
            dropZone.className = 'drop-zone';
            dropZone.id = `drop-zone-${index+1}`;
            lane.appendChild(dropZone);
            this.createdDropZones.push(dropZone);
            this.dropZones.set(index+1, {
                element: dropZone
            });
        });
    }

    setupCardDragListeners() {
        const draggableCards = this.playerHandCards().filter(
            (card) => card.getAttribute('draggable') === 'true'
        );
        draggableCards.forEach((card, index) => {
            card.addEventListener('dragstart', this.onCardDragStart.bind(this));
            card.addEventListener('dragend', this.onCardDragEnd.bind(this));
        });
    }

    setupFaceDownCardClickListeners() {
        if (!this.playerBoard) return;
        const faceDownCards = Array.from(
            this.playerBoard
            .querySelectorAll(':not(.hologram) .cardContainer.faceDown:not(.blocked)')
        ).filter((card) => card.closest('.enemyDeckHand') == null);

        faceDownCards.forEach((card) => {
            const laneValue = this._laneValueForCard(card);
            card.addEventListener('click', (e) => this.onFaceDownCardClick(e, laneValue), {once : true});
        });
    }

    _laneValueForCard(card) {
        const laneElementClass = card.closest('li.lane').classList[1];
        if (laneElementClass === 'Intelligence') return 1;
        if (laneElementClass === 'Speed') return 2;
        if (laneElementClass === 'Visciousness') return 3;
        if (laneElementClass === 'Resolve') return 4;
        console.warn('Unknown lane type for face-down card:', laneElementClass);
        return null;
    }

    setupDropZoneListeners() {
        this.dropZones.forEach((zoneData, index) => {
            const zone = zoneData.element;

            zone.addEventListener('dragover', this.onDropZoneDragOver.bind(this));
            zone.addEventListener('dragleave', this.onDropZoneDragLeave.bind(this));
            zone.addEventListener('drop', this.onDropZoneDrop.bind(this));
            zone.addEventListener('click', this.onDropZoneClick.bind(this));
            zone.addEventListener('mouseenter', (event) => this.onDropZoneMouseEnter(event, index + 1));
            zone.addEventListener('mouseleave', (event) => this.onDropZoneMouseLeave(event, index + 1));
        });
    }

    onDropZoneMouseEnter(event, laneValue) {
        const state = this._keyboardSelectionControl?.state;
        if (!state?.mouseSelecting) return;
        if (!this._isPlayableKeyboardCard(state.selectedCard)) return;
        if (this.remainingAllowances().plays <= 0) return;
        state.hoveredLaneValue = laneValue;
        if (state.hologram?.parentNode) state.hologram.remove();
        const dropZone = this.dropZones.get(laneValue)?.element;
        const holoRow = dropZone?.closest('li.lane')?.querySelector('.hologramRow');
        if (!holoRow) return;
        const hologram = this._buildPlayHologram(state.selectedCard, laneValue, true, state.rotation);
        if (!hologram) return;
        holoRow.appendChild(hologram);
        state.hologram = hologram;
        state.laneValue = laneValue;
        state.currentLane = laneValue;
        state.lanePreviewActive = true;
        this._refreshFocusArrowFromMouse();
    }

    onDropZoneMouseLeave(event, laneValue) {
        const state = this._keyboardSelectionControl?.state;
        if (!state?.mouseSelecting) return;
        if (state.hoveredLaneValue !== laneValue) return;
        state.hoveredLaneValue = null;
        if (state.hologram?.parentNode) state.hologram.remove();
        state.hologram = null;
        state.laneValue = null;
        state.currentLane = null;
        state.lanePreviewActive = false;
        this._refreshFocusArrowFromMouse();
    }

    setupKeyboardSelection() {
        if (this.keyboardListenersBound || !this._hasPlayerBoard()) return;

        this.keyboardKeydownHandler = (event) => this.onKeyboardKeyDown(event);
        this.keyboardKeyupHandler = (event) => this.onKeyboardKeyUp(event);
        this.keyboardClickHandler = (event) => this.onHandCardClick(event);
        this.keyboardVisibilityHandler = () => {
            if (document.hidden || document.visibilityState === 'hidden') {
                this.clearKeyboardSelection();
                this.cancelShortcutHolds();
            }
        };
        this.keyboardBlurHandler = () => this.cancelShortcutHolds();
        this.keyboardPageHideHandler = () => {
            this.clearKeyboardSelection();
            this.cancelShortcutHolds();
        };
        this.keyboardMutationHandler = () => {
            if (!this._hasPlayerBoard()) {
                this.destroy();
                return;
            }
            if (this.endTurnHold.isActive() && !this._endTurnActionAllowed()) {
                this.endTurnHold.cancel();
            }
            if (this.drawHold.isActive() && !this._drawActionAllowed()) {
                this.drawHold.cancel();
            }
            const selection = this.keyboardSelection;
            if (
                (selection.selectedCard || selection.digitBuffer) &&
                (
                    this._keyboardTransitionActive() ||
                    (
                        selection.selectedCard &&
                        !this._isPlayableKeyboardCard(selection.selectedCard) &&
                        !this._isGhostFlipCandidate(selection.selectedCard)
                    )
                )
            ) {
                this.clearKeyboardSelection();
            }
        };

        document.addEventListener('keydown', this.keyboardKeydownHandler, true);
        document.addEventListener('keyup', this.keyboardKeyupHandler, true);
        document.addEventListener('click', this.keyboardClickHandler);
        document.addEventListener('visibilitychange', this.keyboardVisibilityHandler);
        window.addEventListener('blur', this.keyboardBlurHandler);
        window.addEventListener('pagehide', this.keyboardPageHideHandler);
        if (typeof MutationObserver !== 'undefined' && document.body) {
            this.keyboardObserver = new MutationObserver(this.keyboardMutationHandler);
            this.keyboardObserver.observe(document.body, {
                attributes: true,
                attributeFilter: [
                    'class',
                    'data-phase',
                    'data-loading',
                    'data-timeline-active',
                    'disabled',
                    'aria-disabled',
                    'data-drawn',
                    'data-int-count',
                    'data-spd-count',
                    'data-tactics',
                    'data-played',
                    'data-flipped',
                    'data-draws-left',
                    'data-plays-left',
                    'data-flips-left',
                ],
                childList: true,
                subtree: true,
            });
        }
        const playerScreen = document.querySelector('.playerScreen');
        if (playerScreen) {
            this.focusDelegateHandler = (event) => {
                const card = event.target.closest('.cardContainer');
                if (!card || !playerScreen.contains(card)) return;
                if (card.closest('.playerScreen ul.cardRow[title="trustedCards"]')) return;
                if (event.type === 'focusin') {
                    this._keyboardSelectionControl.onFocusIn(card);
                } else {
                    this._keyboardSelectionControl.onFocusOut(card);
                }
            };
            playerScreen.addEventListener('focusin', this.focusDelegateHandler, true);
            playerScreen.addEventListener('focusout', this.focusDelegateHandler, true);
        }
        this.keyboardListenersBound = true;
    }

    _hasPlayerBoard() {
        return Boolean(
            this.playerBoard &&
            document.documentElement &&
            document.documentElement.contains(this.playerBoard)
        );
    }

    cancelShortcutHolds() {
        this.endTurnHold.cancel();
        this.drawHold.cancel();
    }

    _isTextControlTarget(target) {
        if (!target || typeof target.closest !== 'function') return false;
        const control = target.closest('input, textarea, select, [contenteditable]');
        if (!control) return false;
        if (control.matches('input, textarea, select')) return true;
        return control.getAttribute('contenteditable') !== 'false';
    }

    _keyboardTransitionActive() {
        const phase = document.getElementById('turnPhase')?.dataset.phase || '';
        if (document.querySelector('#turnPhase[data-phase="enemy"]')) return true;
        if (phase === 'enemy' || phase === 'playerMoves' || phase === 'loading' || phase === 'timeline') {
            return true;
        }
        if (document.getElementById('timelineSteps')) return true;
        if (document.querySelector('.loading, [data-loading="true"]')) {
            return true;
        }
        if (document.querySelector('.timeline-banner, .enemyTurnMarker, .timeline-active, [data-timeline-active="true"]')) {
            return true;
        }
        return false;
    }

    _keyboardInteractionAllowed(event = null) {
        if (!this._hasPlayerBoard()) return false;
        const activeElement = document.activeElement;
        if (
            this._isTextControlTarget(event?.target) ||
            this._isTextControlTarget(activeElement)
        ) return false;
        if (
            this._isDisabledControlTarget(event?.target) ||
            this._isDisabledControlTarget(activeElement)
        ) return false;
        if (event && (event.ctrlKey || event.altKey || event.metaKey || event.shiftKey)) return false;
        if (this._keyboardTransitionActive()) {
            this.clearKeyboardSelection();
            return false;
        }
        return true;
    }

    _keyboardActionAllowed(event) {
        if (!this._keyboardInteractionAllowed(event)) return false;
        if (this.remainingAllowances().plays <= 0) {
            this.clearKeyboardSelection();
            return false;
        }
        return true;
    }

    _ghostFlipInteractionAllowed(event = null) {
        if (!this._keyboardInteractionAllowed(event)) return false;
        if (this.remainingAllowances().flips <= 0) {
            this.clearKeyboardSelection();
            return false;
        }
        return true;
    }

    _ghostFlipSelectionActive() {
        return Boolean(
            this.keyboardSelection.selectedCard && this.keyboardSelection.ghostFlip
        );
    }

    _keyboardCancellationAllowed(event) {
        if (!this._keyboardInteractionAllowed(event)) return false;
        if (this.remainingAllowances().plays <= 0 && !this._ghostFlipSelectionActive()) {
            this.clearKeyboardSelection();
            return false;
        }
        return true;
    }

    _cancelKeyboardSelectionFromEvent(event) {
        if (!this._keyboardCancellationAllowed(event)) return false;
        event.preventDefault();
        this.cancelKeyboardSelection();
        return true;
    }

    _isDisabledControlTarget(target) {
        if (!target || typeof target.closest !== 'function') return false;
        const control = target.closest(
            'button, input, textarea, select, [aria-disabled="true"], .blocked'
        );
        if (!control) return false;
        return Boolean(
            control.disabled ||
            control.matches(':disabled, [aria-disabled="true"], .blocked')
        );
    }

    _cardIdInput(card) {
        return Array.from(card.querySelectorAll('input[name="card_id"]'))
            .find(input => input.type === 'hidden' || input.hidden) || null;
    }

    _cardLaneValue(card) {
        const laneInput = card.querySelector('input[name="lane"]');
        const hiddenLane = Number.parseInt(laneInput?.value, 10);
        if (hiddenLane >= 1 && hiddenLane <= 4) return hiddenLane;

        const dataLane = Number.parseInt(card.dataset.cardLane || card.dataset.lane, 10);
        if (dataLane >= 1 && dataLane <= 4) return dataLane;

        const cardType = card.querySelector('.cardType')?.textContent.trim().toLowerCase();
        const numericType = Number.parseInt(cardType, 10);
        if (numericType >= 0 && numericType <= 3) return numericType + 1;
        const laneNames = {
            intelligence: 1,
            speed: 2,
            viciousness: 3,
            visciousness: 3,
            resolve: 4,
        };
        return laneNames[cardType] || null;
    }

    _isPlayableKeyboardCard(card) {
        return this._keyboardSelectionControl._isPlayableKeyboardCard_Legacy(card);
    }

    _isStagedGhost(card) {
        return this._keyboardSelectionControl._isStagedGhost_Legacy(card);
    }

    orderableKeyboardCards() {
        return this._keyboardSelectionControl.orderableKeyboardCards();
    }

    _isOrderableKeyboardCard(card) {
        return this._keyboardSelectionControl._isOrderableKeyboardCard_Legacy(card);
    }

    _isGhostFlipCandidate(card) {
        return this._keyboardSelectionControl._isGhostFlipCandidate_Legacy(card);
    }

    _stagedLaneForGhost(card) {
        return this._keyboardSelectionControl._stagedLaneForGhost_Legacy(card);
    }

    _handCardForId(cardId) {
        return this._keyboardSelectionControl._handCardForId_Legacy(cardId);
    }

    _isEndTurnKey(event) {
        return typeof event.key === 'string' && event.key.toLowerCase() === 'e';
    }

    _isDrawKey(event) {
        return typeof event.key === 'string' && event.key.toLowerCase() === 'd';
    }

    _findEndTurnControl() {
        const markedControl = document.querySelector('.playerScreen .end-turn');
        if (!markedControl) return null;

        const button = markedControl.matches('button')
            ? markedControl
            : markedControl.querySelector('button[type="submit"], button');
        const form = markedControl.matches('form')
            ? markedControl
            : button?.form || markedControl.closest('form');
        if (!form || (!button && typeof form.requestSubmit !== 'function')) return null;

        return {
            target: markedControl,
            button,
            form,
        };
    }

    _isPlayerActionPhase() {
        const phase = document.getElementById('turnPhase')?.dataset.phase || '';
        return phase === '' || phase === 'player';
    }

    _isBlockedOrDisabled(control) {
        if (!control) return false;
        return Boolean(
            control.disabled ||
            control.matches?.(':disabled, [aria-disabled="true"], .blocked') ||
            control.closest?.('.blocked')
        );
    }

    _shortcutActionAllowed(event = null) {
        if (!this._hasPlayerBoard()) return false;
        if (document.hidden || document.visibilityState === 'hidden') return false;
        if (!this._isPlayerActionPhase() || this._keyboardTransitionActive()) return false;

        const activeElement = document.activeElement;
        if (
            this._isTextControlTarget(event?.target) ||
            this._isTextControlTarget(activeElement) ||
            this._isDisabledControlTarget(event?.target) ||
            this._isDisabledControlTarget(activeElement)
        ) return false;
        if (event && (event.ctrlKey || event.altKey || event.metaKey || event.shiftKey)) {
            return false;
        }

        return true;
    }

    _endTurnActionAllowed(event = null, control = this._findEndTurnControl()) {
        if (!control || !this._shortcutActionAllowed(event)) return false;

        return ![control.target, control.button, control.form].some((element) => {
            return this._isBlockedOrDisabled(element);
        });
    }

    _findDrawControl() {
        const deck = document.querySelector('.playerScreen .deckHand .active-deck');
        if (!deck || deck.querySelector('.emptyDeck')) return null;

        const button = deck.querySelector('button.draw');
        const form = button?.form || button?.closest('form');
        if (!button || !form) return null;

        return {
            deck,
            button,
            form,
        };
    }

    _drawActionAllowed(event = null, control = this._findDrawControl()) {
        if (!control || !this._shortcutActionAllowed(event)) return false;
        if (this.remainingAllowances().draws <= 0) return false;

        return ![control.deck, control.button, control.form].some((element) => {
            return this._isBlockedOrDisabled(element);
        });
    }

    onEndTurnKeyDown(event) {
        if (
            event.repeat ||
            this.endTurnHold.isActive() ||
            this.endTurnHold.isProtected() ||
            this.drawHold.isActive() ||
            this.drawHold.isProtected()
        ) return;

        const control = this._findEndTurnControl();
        if (!this._endTurnActionAllowed(event, control)) return;
        if (this.endTurnHold.start(control.target, () => this._submitHeldEndTurn())) {
            event.preventDefault();
        }
    }

    onKeyboardKeyUp(event) {
        if (this._isEndTurnKey(event)) {
            if (this.endTurnHold.release()) event.preventDefault();
            return;
        }
        if (this._isDrawKey(event) && this.drawHold.release()) event.preventDefault();
    }

    _submitHeldEndTurn() {
        const control = this._findEndTurnControl();
        if (!this._endTurnActionAllowed(null, control)) return;
        if (control.button && typeof control.button.click === 'function') {
            control.button.click();
            return;
        }
        if (typeof control.form.requestSubmit === 'function') {
            control.form.requestSubmit();
        }
    }

    onDrawKeyDown(event) {
        if (
            event.repeat ||
            this.drawHold.isActive() ||
            this.drawHold.isProtected() ||
            this.endTurnHold.isActive() ||
            this.endTurnHold.isProtected()
        ) return;

        let control = this._findDrawControl();
        if (!this._drawActionAllowed(event, control)) return;
        if (this.drawHold.start([control.deck, control.button], () => this._submitHeldDraw())) {
            event.preventDefault();
        }
    }

    _submitHeldDraw() {
        const control = this._findDrawControl();
        if (!this._drawActionAllowed(null, control)) return;
        if (control.button && typeof control.button.click === 'function') {
            control.button.click();
            return;
        }
        if (typeof control.form.requestSubmit === 'function') {
            control.form.requestSubmit(control.button);
        }
    }

    onKeyboardKeyDown(event) {
        if (event.defaultPrevented) return;
        if (event.key === '`') {
            const target = event.target || document.activeElement;
            if (this._isTextControlTarget(target) || this._isTextControlTarget(document.activeElement)) {
                event.preventDefault();
                return;
            }
            event.preventDefault();
            const playerCounter = document.querySelector('.playerScreen .deckHand > p');
            if (playerCounter) playerCounter.classList.toggle('debug-overlay-visible');
            document.querySelectorAll('.playerScreen .enemyDeckHand > p').forEach(element => {
                element.classList.toggle('debug-overlay-visible');
            });
            document.querySelectorAll('.playerScreen .lanes .lane > p').forEach(element => {
                element.classList.toggle('debug-overlay-visible');
            });
            const debugOverlay = document.getElementById('debugOverlay');
            if (debugOverlay) {
                const shouldShow = !debugOverlay.classList.contains('debug-overlay-visible');
                debugOverlay.classList.toggle('debug-overlay-visible');
                debugOverlay.hidden = !shouldShow;
            }
            return;
        }
        if (this._isEndTurnKey(event)) {
            this.onEndTurnKeyDown(event);
            return;
        }
        if (this._isDrawKey(event)) {
            this.onDrawKeyDown(event);
            return;
        }
        const key = event.key;
        if (
            this.keyboardSelection.selectedCard &&
            !this._isPlayableKeyboardCard(this.keyboardSelection.selectedCard) &&
            !this._isGhostFlipCandidate(this.keyboardSelection.selectedCard)
        ) {
            this.clearKeyboardSelection();
        }
        const activeSelection = this.keyboardSelection.selectedCard || this.keyboardSelection.digitBuffer;

        if (key === '0' || key === 'Backspace') {
            if (!activeSelection) return;
            this._cancelKeyboardSelectionFromEvent(event);
            return;
        }

        if (key === 'Escape') {
            if (!activeSelection) return;
            if (this.keyboardSelection.lanePreviewActive) {
                if (!this._keyboardInteractionAllowed(event)) return;
                event.preventDefault();
                this._keyboardSelectionControl.resetLaneSelection();
                return;
            }
            this._cancelKeyboardSelectionFromEvent(event);
            return;
        }

        if (!activeSelection && (key === 'Enter' || key === ' ')) {
            this.flipKeyboardFocusedCard(event);
            return;
        }

        if (
            this.keyboardSelection.selectedCard &&
            (key === 'Enter' || key === ' ' || key === 'Space' || key === 'Spacebar')
        ) {
            if (event.repeat) return;
            if (this.keyboardSelection.ghostFlip) {
                if (this._keyboardSelectionControl._confirmGhostFlipSelection(event)) event.preventDefault();
                return;
            }
            const selection = this.keyboardSelection;
            if (
                selection.selectedCard &&
                selection.selectedCard.dataset.stagedFlipped === 'true'
            ) {
                this.clearKeyboardSelection();
                return;
            }
            if (!this._keyboardActionAllowed(event)) return;
            if (this.confirmKeyboardSelection()) event.preventDefault();
            return;
        }

        if (
            (key === 'ArrowUp' || key === 'ArrowDown' || key === 'ArrowLeft' || key === 'ArrowRight') &&
            !this.keyboardSelection.selectedCard &&
            !this.keyboardSelection.ghostFlip
        ) {
            if (!this._keyboardInteractionAllowed(event)) return;
            if (this.control.navigate(key, document.activeElement)) event.preventDefault();
            return;
        }

        const laneStep = {
            ArrowLeft: -1,
            ArrowUp: -1,
            ArrowRight: 1,
            ArrowDown: 1,
        }[key];
        if (
            this.keyboardSelection.selectedCard &&
            !this.keyboardSelection.ghostFlip &&
            this.keyboardSelection.lanePreviewActive &&
            laneStep
        ) {
            if (!this._keyboardActionAllowed(event)) return;
            const currentLane = this.keyboardSelection.currentLane;
            const nextLane = ((currentLane - 1 + laneStep + 4) % 4) + 1;
            if (this.moveKeyboardSelection(nextLane)) event.preventDefault();
            return;
        }

        if (
            this.keyboardSelection.selectedCard &&
            !this.keyboardSelection.ghostFlip &&
            !this.keyboardSelection.lanePreviewActive &&
            (key === 'ArrowLeft' || key === 'ArrowRight')
        ) {
            if (!this._keyboardActionAllowed(event)) return;
            const eligibleCards = this.playableKeyboardCards();
            if (eligibleCards.length === 0) return;
            const currentIndex = eligibleCards.indexOf(this.keyboardSelection.selectedCard);
            const direction = key === 'ArrowRight' ? 1 : -1;
            const fallbackIndex = direction > 0 ? 0 : eligibleCards.length - 1;
            const nextIndex = currentIndex === -1
                ? fallbackIndex
                : (((currentIndex + direction) % eligibleCards.length) + eligibleCards.length) % eligibleCards.length;
            const nextCard = eligibleCards[nextIndex];
            this._keyboardSelectionControl.clearKeyboardSelection({ removePreview: false });
            this._keyboardSelectionControl.selectKeyboardCard(nextCard, String(nextIndex + 1));
            event.preventDefault();
            return;
        }

        // Held +/- repeats intentionally cycle through the fan, unlike other keys.
        const stepDirection =
            (key === '+' || key === '=' || event.code === 'NumpadAdd') ? 1 :
            ((key === '-' || key === '_' || event.code === 'NumpadSubtract') ? -1 : 0);
        if (stepDirection !== 0) {
            if (this.keyboardSelection.ghostFlip) return;
            if (!this._keyboardActionAllowed(event)) return;
            const eligibleCards = this.playableKeyboardCards();
            let stepped = false;
            if (!activeSelection) {
                if (stepDirection > 0 && eligibleCards.length > 0) {
                    stepped = this.selectKeyboardCard(eligibleCards[0], '1');
                }
            } else if (eligibleCards.length >= 2) {
                const currentIndex = eligibleCards.indexOf(this.keyboardSelection.selectedCard);
                const nextIndex =
                    (((currentIndex + stepDirection) % eligibleCards.length) +
                        eligibleCards.length) % eligibleCards.length;
                stepped = this.selectKeyboardCard(eligibleCards[nextIndex], String(nextIndex + 1));
            }
            if (stepped) event.preventDefault();
            return;
        }

        if (event.repeat || !/^[1-9]$/.test(key)) return;

        const orderableCards = this.orderableKeyboardCards();
        if (orderableCards.length === 0) return;

        event.preventDefault();
        const digitBuffer = `${this.keyboardSelection.digitBuffer}${key}`;
        this.keyboardSelection.digitBuffer = digitBuffer;
        const ordinal = this._keyboardSelectionControl._noZeroOrdinal(digitBuffer);
        if (ordinal) {
            if (ordinal <= orderableCards.length) {
                this.selectOrderedCard(orderableCards[ordinal - 1], digitBuffer, event);
                return;
            }
        }
        const lastDigitBuffer = digitBuffer.slice(-1);
        const lastDigitOrdinal = this._keyboardSelectionControl._noZeroOrdinal(lastDigitBuffer);
        if (lastDigitOrdinal && lastDigitOrdinal <= orderableCards.length) {
            this.selectOrderedCard(orderableCards[lastDigitOrdinal - 1], lastDigitBuffer, event);
            return;
        }
        this.clearKeyboardSelection();
    }

    
    selectOrderedCard(card, digitBuffer, event) {
        if (this._isPlayableKeyboardCard(card)) {
            if (!this._keyboardActionAllowed(event)) return;
            this.selectKeyboardCard(card, digitBuffer);
            return;
        }
        if (this._isGhostFlipCandidate(card)) {
            if (!this._ghostFlipInteractionAllowed(event)) return;
            this.selectKeyboardCard(card, digitBuffer);
            return;
        }
        if (card.dataset.stagedFlipped === 'true' && card.classList.contains('ghost')) {
            if (typeof card.focus === 'function') card.focus({ preventScroll: true });
            this.clearKeyboardSelection();
        }
    }

    flipKeyboardFocusedCard(event) {
        return this._keyboardSelectionControl.flipKeyboardFocusedCard(event);
    }

    selectKeyboardCard(card, digitBuffer) {
        return this._keyboardSelectionControl.selectKeyboardCard(card, digitBuffer);
    }

    moveKeyboardSelection(laneValue) {
        return this._keyboardSelectionControl.moveKeyboardSelection(laneValue);
    }

    confirmKeyboardSelection(laneValue = null) {
        return this._keyboardSelectionControl.confirmKeyboardSelection(laneValue);
    }

    clearKeyboardSelection(opts) {
        this._teardownMouseSelectionListeners();
        const marker = document.getElementById('mousePreviewCursor');
        if (marker) marker.remove();
        return this._keyboardSelectionControl.clearKeyboardSelection(opts);
    }

    cancelKeyboardSelection() {
        return this._keyboardSelectionControl.cancelKeyboardSelection();
    }

    onHandCardClick(event) {
        const target = event.target;
        const card = typeof target.closest === 'function'
            ? target.closest('.playerScreen .deckHand .hand-scroll ul.hand li.cardContainer')
            : null;
        if (!card) return;
        if (event.button !== 0) return;
        if (this._isTextControlTarget(target)) return;
        if (this._keyboardTransitionActive()) return;
        if (Date.now() - this.lastDragEndedAt < 100) return;

        const orderable = this.orderableKeyboardCards();
        const index = orderable.indexOf(card);
        if (index === -1) return;
        if (this.playableKeyboardCards().includes(card)) {
            if (!this._keyboardActionAllowed(event)) return;
            this.selectHandCardByMouse(card, String(index + 1));
            return;
        }
        if (!card.classList.contains('ghost')) {
            if (!this._ghostFlipInteractionAllowed(event)) return;
            this.selectKeyboardCard(card, String(index + 1));
            return;
        }
        if (card.dataset.stagedFlipped === 'true') {
            if (typeof card.focus === 'function') card.focus({ preventScroll: true });
            this.clearKeyboardSelection();
            return;
        }
        if (!this._ghostFlipInteractionAllowed(event)) return;
        this.selectKeyboardCard(card, String(index + 1));
    }

    selectHandCardByMouse(card, digitBuffer = this.keyboardSelection?.digitBuffer ?? '') {
        if (!this._hasPlayerBoard() || this._keyboardTransitionActive()) {
            this.clearKeyboardSelection();
            return false;
        }
        if (this.remainingAllowances().plays <= 0) {
            this.clearKeyboardSelection();
            return false;
        }
        if (!this._isPlayableKeyboardCard(card)) return false;
        const laneValue = this._cardLaneValue(card);
        if (!laneValue) return false;
        const cardIdInput = this._cardIdInput(card);
        if (!cardIdInput?.value) return false;

        this._keyboardSelectionControl.clearKeyboardSelection();
        const input = this.playerBoard?.closest('.playerScreen')
            ?.querySelector('form.cardActionForm input[name="focused_hand_card"]');
        if (input) input.value = digitBuffer;
        card.classList.add('keyboard-selected');
        card.dataset.keyboardSelected = 'true';
        card.setAttribute('aria-selected', 'true');
        if (typeof card.focus === 'function') card.focus({ preventScroll: true });
        this._keyboardSelectionControl.state = {
            selectedCard: card,
            cardId: cardIdInput.value,
            sourceLane: card.dataset.sourceLane || '0',
            sourceOrdinal: card.dataset.sourceOrdinal || '0',
            laneValue,
            currentLane: laneValue,
            hologram: null,
            rotation: null,
            digitBuffer,
            ghostFlip: false,
            lanePreviewActive: false,
            mouseSelecting: true,
            hoveredLaneValue: null,
        };
        const parsed = Number.parseInt(digitBuffer, 10);
        this._keyboardSelectionControl.persistedHandSlot = Number.isInteger(parsed) && parsed >= 1
            ? parsed
            : this._keyboardSelectionControl.persistedHandSlot;
        this._updateMousePreviewCursor(event);
        this._refreshFocusArrowFromMouse();
        this._installMouseSelectionListeners();
        return true;
    }

    _updateMousePreviewCursor(event = null) {
        const state = this._keyboardSelectionControl?.state;
        if (!state?.mouseSelecting) return;
        let x = state.mouseCursorX;
        let y = state.mouseCursorY;
        if (event) {
            x = event.clientX;
            y = event.clientY;
            state.mouseCursorX = x;
            state.mouseCursorY = y;
        }
        if (x == null || y == null) {
            if (!event) return;
        }
        let marker = document.getElementById('mousePreviewCursor');
        if (!marker) {
            marker = document.createElement('div');
            marker.id = 'mousePreviewCursor';
            marker.className = 'mouse-preview-cursor';
            document.body.appendChild(marker);
        }
        if (x != null && y != null) {
            marker.style.left = `${x}px`;
            marker.style.top = `${y}px`;
        }
    }

    _refreshFocusArrowFromMouse() {
        const state = this._keyboardSelectionControl?.state;
        if (!state?.mouseSelecting || !state.selectedCard) return;
        const card = state.selectedCard;
        const target = this._mouseFocusTarget(card);
        this._keyboardSelectionControl.onFocusOut(card);
        if (!target) return;
        this._keyboardSelectionControl._focusArrow = {
            source: card,
            target,
            arrow: this._createFocusArrow(card, target),
        };
    }

    _mouseFocusTarget(card) {
        if (!card) return null;
        const state = this._keyboardSelectionControl?.state;
        if (!state?.mouseSelecting) return null;
        if (state.hoveredLaneValue && state.hologram) {
            return state.hologram.querySelector('.cardContainer') || state.hologram;
        }
        return document.getElementById('mousePreviewCursor');
    }

    _installMouseSelectionListeners() {
        if (this._mouseSelectionListenersInstalled) return;
        this._mouseMoveHandler = (event) => {
            const state = this._keyboardSelectionControl?.state;
            if (!state?.mouseSelecting) return;
            this._updateMousePreviewCursor(event);
            this._refreshFocusArrowFromMouse();
        };
        document.addEventListener('mousemove', this._mouseMoveHandler);
        this._mouseSelectionListenersInstalled = true;
    }

    _teardownMouseSelectionListeners() {
        if (!this._mouseSelectionListenersInstalled) return;
        document.removeEventListener('mousemove', this._mouseMoveHandler);
        this._mouseSelectionListenersInstalled = false;
        this._mouseMoveHandler = null;
        const marker = document.getElementById('mousePreviewCursor');
        if (marker) marker.remove();
    }

    onCardDragStart(e) {
        this.clearKeyboardSelection();
        if (this.remainingAllowances().plays <= 0) {
            e.preventDefault();
            return;
        }
        this.draggedCard = e.currentTarget;
        this.draggedCard.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setDragImage(this.draggedCard,180, 150);
        this.highlightAllDropZones(true);
    }

    onCardDragEnd(e) {
        this.draggedCard.classList.remove('dragging');
        this.highlightAllDropZones(false);
        this.lastDragEndedAt = Date.now();
    }

    onDropZoneDragOver(e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        const zone = e.currentTarget;
        zone.classList.add('drop-zone-active');
        return false;
    }

    onDropZoneDragLeave(e) {
        const zone = e.currentTarget;
        zone.classList.remove('drop-zone-active');
        return false;
    }

    onDropZoneClick(e) {
        if (!this.keyboardSelection.selectedCard) return;
        if (!this._keyboardActionAllowed(e)) return;

        const zone = e.currentTarget;
        const laneValue = Array.from(this.dropZones.entries()).find(
            ([, zoneData]) => zoneData.element === zone
        )?.[0];
        if (!laneValue) return;
        const state = this._keyboardSelectionControl?.state;
        if (state?.mouseSelecting && state.laneValue !== laneValue) {
            this.onDropZoneMouseEnter(e, laneValue);
        }
        if (!this.confirmKeyboardSelection(laneValue)) return;

        e.preventDefault();
        e.stopPropagation();
    }

    onDropZoneDrop(e) {
        e.preventDefault();
        e.stopPropagation();
        const zone = e.currentTarget;
        zone.classList.remove('drop-zone-active');

        if (this.draggedCard) {
            const laneElement = zone.closest('li.lane');
            const holoRow = laneElement.querySelector('.hologramRow');
            const laneValue = parseInt(zone.id.split('-')[2]);

            const hologram = this._buildPlayHologram(this.draggedCard, laneValue);
            if (!hologram) return false;
            holoRow.appendChild(hologram);

            if (!this._stagePlay(this.draggedCard, laneValue, hologram)) {
                hologram.remove();
            }
        }
        return false;
    }

    _stagePlay(card, laneValue, hologram, preserveKeyboardPreview = false, sourceState = null) {
        const cardIdInput = this._cardIdInput(card);
        if (!cardIdInput?.value || !hologram) return false;

        const cardId = sourceState?.cardId ?? cardIdInput.value;
        const sourceLane = sourceState?.sourceLane ?? card.dataset.sourceLane ?? '0';
        const sourceOrdinal = sourceState?.sourceOrdinal ?? card.dataset.sourceOrdinal ?? '0';
        if (preserveKeyboardPreview) this.clearKeyboardSelection({removePreview: false});
        this.createupdateCookie(cardId, laneValue, false, sourceLane, sourceOrdinal);

        card.classList.add('ghost');
        card.setAttribute('draggable', 'false');
        card.removeAttribute('tabindex');
        card.dataset.stagedLane = String(laneValue);
        hologram.dataset.stagedForCardId = String(cardId);
        this._addHoverArrow(card, hologram);
        this.staged.plays++;
        this.applyTurnAffordances();
        return true;
    }

    _buildPlayHologram(sourceCard, laneValue, keyboardPreview = false, rotation = null) {
        if (!sourceCard) return null;

        const hologram = document.createElement('div');
        const copycard = sourceCard.cloneNode(true);
        copycard.classList.remove('dragging');
        copycard.removeAttribute('draggable');

        if (keyboardPreview) {
            copycard.classList.remove('faceDown', 'ghost', 'loading', 'keyboard-selected');
            copycard.removeAttribute('aria-selected');
            delete copycard.dataset.keyboardSelected;
            copycard.classList.add('faceUp');
            copycard.removeAttribute('tabindex');
            copycard.querySelectorAll('.back').forEach(cardFace => cardFace.classList.remove('back'));
            this._removePreviewControls(copycard);
        } else {
            copycard.classList.add('faceDown');
            copycard.classList.remove('keyboard-selected');
            copycard.removeAttribute('aria-selected');
            delete copycard.dataset.keyboardSelected;
            copycard.removeAttribute('tabindex');
            const cardFace = copycard.querySelector(':scope > .card');
            if (cardFace) cardFace.classList.add('back');
            const button = copycard.querySelector('button');
            if (button) button.setAttribute('inert', 'true');
        }

        hologram.appendChild(copycard);
        hologram.classList.add('hologram');
        if (keyboardPreview) {
            hologram.classList.add('keyboard-preview');
            hologram.dataset.keyboardPreview = 'true';
            const sourceCardId = this._cardIdInput(sourceCard)?.value;
            if (sourceCardId) hologram.dataset.sourceCardId = sourceCardId;
        } else {
            const faceDownCard = hologram.querySelector('.cardContainer.faceDown');
            if (faceDownCard) {
                faceDownCard.addEventListener(
                    'click',
                    (event) => this.onFaceDownCardClick(event, laneValue),
                    { once: true },
                );
            }
        }
        hologram.style.setProperty(
            '--card-rotation',
            rotation ?? `${(Math.random() * 8 - 4).toFixed(1)}deg`,
        );
        return hologram;
    }

    _removePreviewControls(card) {
        card.querySelectorAll('button').forEach(button => {
            const parent = button.parentNode;
            while (button.firstChild) parent.insertBefore(button.firstChild, button);
            button.remove();
        });
        card.querySelectorAll('form').forEach(form => {
            const parent = form.parentNode;
            while (form.firstChild) parent.insertBefore(form.firstChild, form);
            form.remove();
        });
        card.querySelectorAll('input, select, textarea').forEach(control => control.remove());
    }

    _addHoverArrow(sourceEl, targetEl) {
        let arrow = null;
        let hideTimeout = null;

        const showArrow = () => {
            if (hideTimeout) {
                clearTimeout(hideTimeout);
                hideTimeout = null;
            }
            if (!arrow || !arrow.parentNode) {
                arrow = this._createCurvedArrow(sourceEl, targetEl);
                document.body.appendChild(arrow);
            }
            sourceEl.classList.add('hover');
            targetEl.classList.add('hover');
        };

        const hideArrow = () => {
            if (hideTimeout) return;
            hideTimeout = setTimeout(() => {
                if (arrow && arrow.parentNode) {
                    arrow.remove();
                }
                arrow = null;
                sourceEl.classList.remove('hover');
                targetEl.classList.remove('hover');
                hideTimeout = null;
            }, 100);
        };

        sourceEl.addEventListener('mouseenter', showArrow);
        sourceEl.addEventListener('mouseleave', hideArrow);
        targetEl.addEventListener('mouseenter', showArrow);
        targetEl.addEventListener('mouseleave', hideArrow);
    }

    _createCurvedArrow(sourceEl, targetEl) {
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.classList.add('hologram-arrow');
        svg.style.position = 'fixed';
        svg.style.pointerEvents = 'none';
        svg.style.zIndex = '1000';
        svg.style.overflow = 'visible';
        svg.style.top = '0'; //adjust
        svg.style.left = '0';//adjust
        svg.style.width = '100%';
        svg.style.height = '100%';

        const sourceRect = sourceEl.getBoundingClientRect();
        const targetRect = targetEl.getBoundingClientRect();

        const x1 = sourceRect.left + sourceRect.width / 2;
        const y1 = sourceRect.top + sourceRect.height / 2;
        const x2 = targetRect.left + targetRect.width / 2; // Adjust
        const y2 = targetRect.top + targetRect.height / 2; // Adjust

        const dx = x2 - x1;
        const dy = y2 - y1;
        const cx1 = x1 + dx * 0.25;
        const cy1 = y1 + dy * 0.1 - Math.abs(dx) * 0.3;
        const cx2 = x1 + dx * 0.75;
        const cy2 = y1 + dy * 0.9 - Math.abs(dx) * 0.3;

        const d = `M ${x1} ${y1} C ${cx1} ${cy1}, ${cx2} ${cy2}, ${x2} ${y2}`;

        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', d);
        path.setAttribute('stroke', '#ffcc00');
        path.setAttribute('stroke-width', '3');
        path.setAttribute('fill', 'none');
        path.setAttribute('stroke-dasharray', '6,4');

        svg.appendChild(path);

        const tangentX = x2 - cx2;
        const tangentY = y2 - cy2;
        const angle = Math.atan2(tangentY, tangentX);
        const arrowSize = 20;
        const ax = x2;
        const ay = Math.max(y2 - arrowSize * 0.35 * Math.sin(angle) - 20, y2);

        const marker = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
        marker.setAttribute('points',
            `${ax},${ay} ${ax - arrowSize * Math.cos(angle - 0.4)},${ay - arrowSize * Math.sin(angle - 0.4)} ${ax - arrowSize * Math.cos(angle + 0.4)},${ay - arrowSize * Math.sin(angle + 0.4)}`
        );
        marker.setAttribute('fill', '#ffcc00');
        svg.appendChild(marker);

        return svg;
    }

    _createFocusArrow(sourceEl, targetEl) {
        const arrow = this._createCurvedArrow(sourceEl, targetEl);
        document.body.appendChild(arrow);
        sourceEl.classList.add('hover');
        targetEl.classList.add('hover');
        return arrow;
    }

    _focusArrowTarget(card) {
        if (!card || typeof card.closest !== 'function') return null;
        if (card.closest('.playerScreen .deckHand')) {
            const cardIdInput = this._cardIdInput(card);
            const cardId = cardIdInput?.value;
            if (!cardId) return null;
            if (this.parent && this.state.mouseSelecting) {
                return this.parent._mouseFocusTarget(card) || document.getElementById('mousePreviewCursor');
            }
            const stagedHologram = document.querySelector(
                `.hologram[data-staged-for-card-id="${CSS.escape(cardId)}"]`
            );
            if (stagedHologram) return stagedHologram.querySelector('.cardContainer') || null;
            const previewHologram = document.querySelector(
                `.hologram.keyboard-preview[data-keyboard-preview="true"][data-source-card-id="${CSS.escape(cardId)}"]`
            );
            return previewHologram?.querySelector('.cardContainer') || null;
        }
        if (
            card.closest('.playerScreen .playerBoard ul.cardRow') &&
            card.dataset.stagedFlipped === 'true'
        ) {
            const lane = card.closest('li.lane');
            const flipHologram = lane?.querySelector(':scope > .hologramRow > .hologram');
            return flipHologram?.querySelector('.cardContainer') || null;
        }
        return null;
    }

    onFaceDownCardClick(e, laneValue) {
        if (this.remainingAllowances().flips <= 0) return;
        const card = (e.currentTarget instanceof Element ? e.currentTarget : null)
            ?? e.target.closest('.cardContainer');
        if (!card || card.closest('.keyboard-preview')) return;
        if (card.dataset.stagedFlipped === 'true') return;
        const cardId = card.querySelectorAll('input[name="card_id"]')[0].value;
        const sourceLane = card.dataset.sourceLane ?? '0';
        const sourceOrdinal = card.dataset.sourceOrdinal ?? '0';
        this.createupdateCookie(`${cardId}`, `${laneValue}`, true, sourceLane, sourceOrdinal);

        // If this is a lane card (not a hologram), keep it face-down and create a face-up hologram
        if (!card.closest('.hologram')) {
            const laneElement = card.closest('li.lane');
            const holoRow = laneElement.querySelector('.hologramRow');

            // Lane card stays face-down — ghostly to indicate it was flipped
            card.classList.add('ghost');
            card.dataset.stagedFlipped = 'true';

            // Create face-up hologram clone
            const flipHologram = document.createElement('div');
            const holoClone = card.cloneNode(true);
            holoClone.classList.remove('ghost');
            holoClone.classList.add('faceUp');
            // Remove form/button from the clone (display only)
            const form = holoClone.querySelector('form');
            if (form) form.remove();
            const buttons = holoClone.querySelectorAll('button');
            buttons.forEach(btn => btn.remove());

            // The lane card is still face-down (back class present), so strip back from clone
            const cloneCardDiv = holoClone.querySelector(':scope > .card');
            if (cloneCardDiv) cloneCardDiv.classList.remove('back');
            const cloneCardContainer = holoClone.querySelector('.cardContainer');
            if (cloneCardContainer) {
                cloneCardContainer.classList.remove('faceDown');
                // Face-up lane cards are never focusable.
                cloneCardContainer.removeAttribute('tabindex');
            }

            flipHologram.classList.add('hologram');
            flipHologram.appendChild(holoClone);
            // Small random rotation for stacking look
            flipHologram.style.setProperty('--card-rotation', `${(Math.random() * 8 - 4).toFixed(1)}deg`);
            holoRow.appendChild(flipHologram);

            // One-shot click-to-flip on the hologram (same pattern as play hologram)
            const holoCard = flipHologram.querySelector('.cardContainer');
            if (holoCard) {
                holoCard.addEventListener('click', (ev) => {
                    if (card.dataset.stagedFlipped === 'true') return;
                    this.onFaceDownCardClick(ev, laneValue);
                }, { once: true });
            }

            // Hover arrow between lane card and hologram
            this._addHoverArrow(card, flipHologram);
        } else {
            // For hologram clicks (play hologram flipping face-up), flip face-up
            card.classList.remove('faceDown');
            const cardDiv = card.querySelector(':scope > .card');
            if (cardDiv) cardDiv.classList.remove('back');
            // Face-up cards are never focusable; the flip is one-shot.
            card.removeAttribute('tabindex');
            card.dataset.stagedFlipped = 'true';
            // The hand ghost mirrors the flip so it can't be flipped twice.
            const handGhost = this._handCardForId(cardId);
            if (handGhost) handGhost.dataset.stagedFlipped = 'true';
        }

        this.staged.flips++;
        this.applyTurnAffordances();
    }

    createupdateCookie(cardId, laneValue, flipFaceUp=false, sourceLane=null, sourceOrdinal=null) {
        const path = window.location.pathname;
        let shortPath = path.substring(0, path.lastIndexOf('action'));
        if (!shortPath ) {
            shortPath = path;
        }
        const payload = {
            laneValue: `${laneValue}`,
            sourceLane: sourceLane ?? 0,
            sourceOrdinal: sourceOrdinal ?? 0,
            flipFaceUp,
        };
        document.cookie=`${cardId}=${encodeURIComponent(JSON.stringify(payload))};path=${shortPath}`;
    }

    highlightAllDropZones(highlight) {
        this.dropZones.forEach((zoneData) => {
            const zone = zoneData.element;
            if (highlight) {
                zone.classList.add('drop-zone-highlight');
            } else {
                zone.classList.remove('drop-zone-highlight');
                zone.classList.remove('drop-zone-active');
            }
        });
    }

    refresh() {
        this.destroy();
        this.init();
    }

    destroy() {
        this.clearKeyboardSelection();
        this.cancelShortcutHolds();
        if (this.keyboardListenersBound) {
            document.removeEventListener('keydown', this.keyboardKeydownHandler, true);
            document.removeEventListener('keyup', this.keyboardKeyupHandler, true);
            document.removeEventListener('click', this.keyboardClickHandler);
            document.removeEventListener('visibilitychange', this.keyboardVisibilityHandler);
            window.removeEventListener('blur', this.keyboardBlurHandler);
            window.removeEventListener('pagehide', this.keyboardPageHideHandler);
        }
        if (this.keyboardObserver) {
            this.keyboardObserver.disconnect();
            this.keyboardObserver = null;
        }
        this.createdDropZones.forEach(dropZone => dropZone.remove());
        this.createdDropZones = [];
        this.dropZones.clear();
        this.draggedCard = null;
        if (this.focusDelegateHandler) {
            const playerScreen = document.querySelector('.playerScreen');
            if (playerScreen) {
                playerScreen.removeEventListener('focusin', this.focusDelegateHandler, true);
                playerScreen.removeEventListener('focusout', this.focusDelegateHandler, true);
            }
            this.focusDelegateHandler = null;
        }
        this.keyboardListenersBound = false;
        this.playerBoard = null;
        this._keyboardSelectionControl = null;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.cardDragDrop = new CardDragDropSystem();
});
