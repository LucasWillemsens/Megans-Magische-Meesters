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

class CardDragDropSystem {
    constructor() {
        this.draggedCard = null;
        this.dropZones = new Map();
        this.playerBoard = null;
        this.createdDropZones = [];
        this.turnAllowances = { int: 0, spd: 0, tactics: 0, drawn: 0, played: 0, flipped: 0 };
        this.staged = { plays: 0, flips: 0 };
        this.tooltips = { draw: "", play: "", flip: "" };
        this.keyboardSelection = this._emptyKeyboardSelection();
        this.keyboardListenersBound = false;
        this.keyboardObserver = null;
        this.lastDragEndedAt = 0;
        this.endTurnHold = new ShortcutHoldAction();
        this.drawHold = new ShortcutHoldAction();
        this.init();
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
        };
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
        if (
            !this._hasPlayerBoard() ||
            this._keyboardTransitionActive() ||
            this.remainingAllowances().plays <= 0
        ) return [];
        return this.playerHandCards().filter(card => this._isPlayableKeyboardCard(card));
    }

    applyTurnAffordances() {
        const remaining = this.remainingAllowances();

        if (remaining.plays <= 0) {
            this.clearKeyboardSelection();
            this.playerHandCards().filter(card => !card.classList.contains('blocked')).forEach(card => {
                card.classList.add('blocked');
                card.setAttribute('draggable', 'false');
                card.title = this.tooltips.play;
                card.removeAttribute('tabindex');
            });
        } else {
            this.playerHandCards().forEach(card => {
                if (!card.hasAttribute('tabindex') && this._isPlayableKeyboardCard(card)) {
                    card.setAttribute('tabindex', '-1');
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
            // The deck stack must stay focus-inert (no tabindex on ul/li);
            // the disabled draw button is the visible indication.
            const deck = document.querySelector('.playerScreen .deckHand .active-deck');
            if (deck) deck.classList.add('blocked');
            const drawBtn = deck?.querySelector('button.draw');
            if (drawBtn) {
                drawBtn.disabled = true;
                drawBtn.title = this.tooltips.draw;
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
        });
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
                    (selection.selectedCard && !this._isPlayableKeyboardCard(selection.selectedCard))
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

    _keyboardActionAllowed(event) {
        if (!this._hasPlayerBoard()) return false;
        const activeElement = document.activeElement;
        if (this._isTextControlTarget(event.target) || this._isTextControlTarget(activeElement)) {
            return false;
        }
        if (this._isDisabledControlTarget(event.target) || this._isDisabledControlTarget(activeElement)) {
            return false;
        }
        if (event.ctrlKey || event.altKey || event.metaKey || event.shiftKey) return false;
        if (this._keyboardTransitionActive()) {
            this.clearKeyboardSelection();
            return false;
        }
        if (this.remainingAllowances().plays <= 0) {
            this.clearKeyboardSelection();
            return false;
        }
        return true;
    }

    _keyboardCancellationAllowed(event) {
        if (!this._hasPlayerBoard()) return false;
        if (this._isTextControlTarget(event.target) || this._isTextControlTarget(document.activeElement)) {
            return false;
        }
        if (this._isDisabledControlTarget(event.target) || this._isDisabledControlTarget(document.activeElement)) {
            return false;
        }
        if (event.ctrlKey || event.altKey || event.metaKey || event.shiftKey) return false;
        if (this._keyboardTransitionActive() || this.remainingAllowances().plays <= 0) {
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
    }

    _noZeroOrdinal(buffer) {
        if (!/^[1-9]+$/.test(buffer)) return null;
        let ordinal = 0;
        for (const character of buffer) {
            ordinal = ordinal * 9 + Number.parseInt(character, 10);
            if (!Number.isSafeInteger(ordinal)) return Number.POSITIVE_INFINITY;
        }
        return ordinal;
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
            !this._isPlayableKeyboardCard(this.keyboardSelection.selectedCard)
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
            if (event.repeat || !this._keyboardActionAllowed(event)) return;
            if (this.confirmKeyboardSelection()) event.preventDefault();
            return;
        }

        const laneStep = {
            ArrowLeft: -1,
            ArrowUp: -1,
            ArrowRight: 1,
            ArrowDown: 1,
        }[key];
        if (this.keyboardSelection.selectedCard && laneStep) {
            if (!this._keyboardActionAllowed(event)) return;
            const currentLane = this.keyboardSelection.currentLane;
            const nextLane = ((currentLane - 1 + laneStep + 4) % 4) + 1;
            if (this.moveKeyboardSelection(nextLane)) event.preventDefault();
            return;
        }

        // Held +/- repeats intentionally cycle through the fan, unlike other keys.
        const stepDirection =
            (key === '+' || key === '=' || event.code === 'NumpadAdd') ? 1 :
            ((key === '-' || key === '_' || event.code === 'NumpadSubtract') ? -1 : 0);
        if (stepDirection !== 0) {
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

        if (event.repeat || !/^[1-9]$/.test(key) || !this._keyboardActionAllowed(event)) return;

        const eligibleCards = this.playableKeyboardCards();
        if (eligibleCards.length === 0) return;

        event.preventDefault();
        const digitBuffer = `${this.keyboardSelection.digitBuffer}${key}`;
        this.keyboardSelection.digitBuffer = digitBuffer;
        const ordinal = this._noZeroOrdinal(digitBuffer);
        if (!ordinal) return;
        if (ordinal <= eligibleCards.length) {
            this.selectKeyboardCard(eligibleCards[ordinal - 1], digitBuffer);
            return;
        }
        const lastDigitBuffer = digitBuffer.slice(-1);
        const lastDigitOrdinal = this._noZeroOrdinal(lastDigitBuffer);
        if (lastDigitOrdinal && lastDigitOrdinal <= eligibleCards.length) {
            this.selectKeyboardCard(eligibleCards[lastDigitOrdinal - 1], lastDigitBuffer);
            return;
        }
        this.clearKeyboardSelection();
    }

    flipKeyboardFocusedCard(event) {
        const card = this._keyboardFlipTarget(event);
        if (!card || event.repeat) return;
        const laneValue = this._laneValueForCard(card);
        if (
            laneValue == null ||
            this.remainingAllowances().flips <= 0 ||
            card.classList.contains('blocked') ||
            card.closest('.blocked') ||
            card.classList.contains('ghost')
        ) return;
        event.preventDefault();
        this.onFaceDownCardClick(event, laneValue);
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
        const zone = this.dropZones.get(laneValue)?.element;
        return zone?.closest('li.lane')?.querySelector('.hologramRow') || null;
    }

    selectKeyboardCard(card, digitBuffer = this.keyboardSelection.digitBuffer) {
        if (!this._hasPlayerBoard()) return false;
        if (this._keyboardTransitionActive() || this.remainingAllowances().plays <= 0) {
            this.clearKeyboardSelection();
            return false;
        }
        if (!this._isPlayableKeyboardCard(card)) return false;
        const laneValue = this._cardLaneValue(card);
        const holoRow = laneValue ? this._keyboardHologramRow(laneValue) : null;
        if (!laneValue || !holoRow) return false;

        const hologram = this._buildPlayHologram(card, laneValue, true);
        if (!hologram) return false;

        this.clearKeyboardSelection();
        holoRow.appendChild(hologram);
        card.classList.add('keyboard-selected');
        card.dataset.keyboardSelected = 'true';
        card.setAttribute('aria-selected', 'true');
        if (typeof card.focus === 'function') card.focus({ preventScroll: true });
        const cardIdInput = this._cardIdInput(card);
        this.keyboardSelection = {
            selectedCard: card,
            cardId: cardIdInput.value,
            sourceLane: card.dataset.sourceLane || '0',
            sourceOrdinal: card.dataset.sourceOrdinal || '0',
            laneValue,
            currentLane: laneValue,
            hologram,
            rotation: hologram.style.getPropertyValue('--card-rotation'),
            digitBuffer,
        };
        return true;
    }

    moveKeyboardSelection(laneValue) {
        const selection = this.keyboardSelection;
        const parsedLane = Number.parseInt(laneValue, 10);
        if (
            !selection.selectedCard ||
            !Number.isInteger(parsedLane) ||
            parsedLane < 1 ||
            parsedLane > 4 ||
            !this.dropZones.has(parsedLane)
        ) return false;
        if (
            this._keyboardTransitionActive() ||
            this.remainingAllowances().plays <= 0 ||
            !this._isPlayableKeyboardCard(selection.selectedCard)
        ) {
            this.clearKeyboardSelection();
            return false;
        }

        const holoRow = this._keyboardHologramRow(parsedLane);
        const hologram = this._buildPlayHologram(
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
        if (!this.keyboardSelection.selectedCard) return false;
        if (
            this._keyboardTransitionActive() ||
            this.remainingAllowances().plays <= 0 ||
            !this._isPlayableKeyboardCard(this.keyboardSelection.selectedCard)
        ) {
            this.clearKeyboardSelection();
            return false;
        }

        const requestedLane = laneValue == null
            ? this.keyboardSelection.currentLane
            : Number.parseInt(laneValue, 10);
        if (!Number.isInteger(requestedLane) || requestedLane < 1 || requestedLane > 4) {
            return false;
        }
        if (requestedLane !== this.keyboardSelection.currentLane && !this.moveKeyboardSelection(requestedLane)) {
            return false;
        }

        const selection = this.keyboardSelection;
        const card = selection.selectedCard;
        if (
            !card ||
            !selection.hologram ||
            !selection.hologram.parentNode ||
            !this._isPlayableKeyboardCard(card) ||
            this._keyboardTransitionActive() ||
            this.remainingAllowances().plays <= 0
        ) {
            this.clearKeyboardSelection();
            return false;
        }

        selection.hologram.remove();
        const hologram = this._buildPlayHologram(card, requestedLane, false, selection.rotation);
        this._keyboardHologramRow(requestedLane).appendChild(hologram);
        hologram.classList.add('keyboard-staged');
        hologram.dataset.keyboardStaged = 'true';

        const staged = this._stagePlay(card, requestedLane, hologram, true, selection);

        const faceDownCard = hologram.querySelector('.cardContainer.faceDown');
        if (staged && faceDownCard && this.remainingAllowances().flips > 0) {
            faceDownCard.setAttribute('tabindex', '0');
        }
        return staged;
    }

    clearKeyboardSelection({removePreview = true} = {}) {
        const selection = this.keyboardSelection;
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
        if (removePreview && selection.hologram?.parentNode) selection.hologram.remove();
        this.keyboardSelection = this._emptyKeyboardSelection();
    }

    cancelKeyboardSelection() {
        this.clearKeyboardSelection();
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
        if (!this._keyboardActionAllowed(event)) return;

        const eligible = this.playableKeyboardCards();
        const index = eligible.indexOf(card);
        if (index === -1) return;
        this.selectKeyboardCard(card, String(index + 1));
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
        if (!laneValue || !this.confirmKeyboardSelection(laneValue)) return;

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
            copycard.querySelectorAll('.back').forEach(cardFace => cardFace.classList.remove('back'));
            this._removePreviewControls(copycard);
        } else {
            copycard.classList.add('faceDown');
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

    onFaceDownCardClick(e, laneValue) {
        if (this.remainingAllowances().flips <= 0) return;
        const card = (e.currentTarget instanceof Element ? e.currentTarget : null)
            ?? e.target.closest('.cardContainer');
        if (!card || card.closest('.keyboard-preview')) return;
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
            if (cloneCardContainer) cloneCardContainer.classList.remove('faceDown');

            flipHologram.classList.add('hologram');
            flipHologram.appendChild(holoClone);
            // Small random rotation for stacking look
            flipHologram.style.setProperty('--card-rotation', `${(Math.random() * 8 - 4).toFixed(1)}deg`);
            holoRow.appendChild(flipHologram);

            // One-shot click-to-flip on the hologram (same pattern as play hologram)
            const holoCard = flipHologram.querySelector('.cardContainer');
            if (holoCard) {
                holoCard.addEventListener('click', (ev) => this.onFaceDownCardClick(ev, laneValue), { once: true });
            }

            // Hover arrow between lane card and hologram
            this._addHoverArrow(card, flipHologram);
        } else {
            // For hologram clicks (play hologram flipping face-up), flip face-up
            card.classList.remove('faceDown');
            const cardDiv = card.querySelector(':scope > .card');
            if (cardDiv) cardDiv.classList.remove('back');
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
        this.keyboardListenersBound = false;
        this.playerBoard = null;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.cardDragDrop = new CardDragDropSystem();
});
