class loadingAnimationsSystem {
    constructor() {
        this._timeoutIds = [];
        this._fastForwarded = false;
        this._animating = false;
        this._lastAnimatedRound = null;
        this.init();
    }

    _setTimeout(fn, delay) {
        const id = setTimeout(() => {
            if (!this._fastForwarded) fn();
            this._timeoutIds = this._timeoutIds.filter(tid => tid !== id);
        }, delay);
        this._timeoutIds.push(id);
        return id;
    }

    _clearAllTimeouts() {
        this._timeoutIds.forEach(id => clearTimeout(id));
        this._timeoutIds = [];
    }

    fastForward(nextUrl, boardPath) {
        if (this._fastForwarded) return;
        this._fastForwarded = true;
        this._animating = false;
        this._clearAllTimeouts();
        document.body.classList.remove('animating');
        document.querySelectorAll('.timeline-banner, .enemyTurnMarker').forEach(el => el.remove());
        window.location.href = nextUrl || (boardPath ? boardPath() : '/');
    }

    _lockInteraction() {
        this._animating = true;
        document.body.classList.add('animating');
    }

    _unlockInteraction() {
        this._animating = false;
        document.body.classList.remove('animating');
    }

    init() {
        this.Animate();
    }

    Animate(classSelector = 'loading', delay = 1200) {
        const animationsElements = Array.from(document.getElementsByClassName(classSelector));
        const phaseEl = document.getElementById('turnPhase');
        const phase = phaseEl?.dataset.phase ?? '';
        const round = parseInt(phaseEl?.dataset.round ?? '0', 10);
        const nextUrl = document.getElementById('boardNext')?.dataset.nextUrl ?? '';
        const moveDuration = Math.max(0.2, Math.min(1.2, delay / 1000));
        const perElementWindow = delay / 2;
        const markerWindow = delay / 3;
        const maxWindow = delay * 5;

        // Check for timeline steps (special draw sequence)
        const timelineElement = document.getElementById('timelineSteps');
        const timeline = timelineElement ? JSON.parse(timelineElement.textContent) : null;

        const boardPath = () => {
            const path = window.location.pathname;
            let shortPath = path.substring(0, path.lastIndexOf('action'));
            if (!shortPath ) {
                shortPath = path;
            }
            return shortPath;
        };

        const reloadToBoard = () => {
            this._unlockInteraction();
            window.location.href = nextUrl || boardPath();
        };

        const animateElement = (element) => {
            element.classList.add('animating');
            const lane  = element.getAttribute('data-source-lane');
            const ordinal = element.getAttribute('data-source-ordinal');
            if (lane != null && ordinal != null && lane != "" && ordinal != ""){
                const duplicate = duplicateCard(element, parseInt(lane), parseInt(ordinal));
                if (duplicate) {
                    duplicate.style.setProperty('--move-duration', `${moveDuration}s`);
                    let revealed = false;
                    const revealElement = () => {
                        if (revealed) {
                            return;
                        }
                        revealed = true;
                        duplicate.remove();
                        element.classList.remove('loading');
                    };
                    duplicate.addEventListener('transitionend', revealElement, { once: true });
                    this._setTimeout(revealElement, moveDuration * 1000 + 100);
                    requestAnimationFrame(() => {
                        duplicate.classList.add('to-original');
                    });
                    return;
                }
            }
            element.classList.remove('loading');
        };

        const playerElements = animationsElements.filter((element) => element.closest('.enemyBoard') == null);
        const enemyElements = animationsElements.filter((element) => element.closest('.enemyBoard') != null);

        // Prevent re-entering the same round's enemy phase (Bug 2 fix)
        if (phase === 'enemy' && this._lastAnimatedRound === round) {
            this._unlockInteraction();
            this._clearAllTimeouts();
            document.querySelectorAll('.enemyTurnMarker').forEach(el => el.remove());
            reloadToBoard();
            return;
        }
        if (phase === 'enemy' || phase === 'playerMoves') {
            this._lastAnimatedRound = round;
        }

        if (phase === 'player') {
            this._lockInteraction();
            turnMarker(delay, 'Your turn', () => this.fastForward(nextUrl, boardPath), this);
            this._setTimeout(() => {
                animationsElements.forEach((element) => element.classList.remove('loading'));
                this._unlockInteraction();
            }, delay + 300);
            const deckHand = document.querySelector('.playerScreen .deckHand');
            if (deckHand) {
                deckHand.scrollIntoView({ behavior: 'smooth', block: 'end' });
            }
            return;
        }

        if (phase === 'playerMoves') {
            this._lockInteraction();
            playerElements.forEach(animateElement);
            const playerWindow = playerElements.length * perElementWindow;
            const playerFinished = playerElements.length > 0 ? moveDuration * 1000 : 0;
            if (timeline && timeline.length > 0) {
                this._setTimeout(() => {
                    if (!this._fastForwarded) {
                        this.playTimeline(timeline, delay, nextUrl, boardPath);
                    }
                }, Math.max(playerWindow, playerFinished) + 200);
            } else {
                const reloadWindow = Math.max(
                    Math.min(Math.max(playerWindow, delay / 2), maxWindow),
                    playerFinished,
                );
                this._setTimeout(reloadToBoard, reloadWindow);
            }
            return;
        }

        if (phase === 'enemy') {
            this._lockInteraction();
            focusEnemySide();
            playerElements.forEach(animateElement);
            let cursor = playerElements.length * perElementWindow;
            let lastFinish = cursor;
            const enemyBoards = Array.from(document.querySelectorAll('.enemyBoard'));
            if (enemyBoards.length > 0) {
                cursor += 300;
            }
            enemyBoards.forEach((board) => {
                const boardElements = enemyElements.filter((element) => element.closest('.enemyBoard') === board);
                const name = (board.querySelector('h2')?.textContent || 'Enemy').trim();
                const movesWindow = boardElements.length > 0
                    ? Math.max(boardElements.length * perElementWindow, moveDuration * 1000)
                    : 0;
                const boardWindow = markerWindow + Math.max(movesWindow, delay / 2);
                this._setTimeout(() => {
                    turnMarker(boardWindow - 300, `${name}'s turn`, () => this.fastForward(nextUrl, boardPath), this);
                }, cursor);
                if (boardElements.length > 0) {
                    this._setTimeout(() => {
                        boardElements.forEach(animateElement);
                    }, cursor + markerWindow);
                    lastFinish = Math.max(lastFinish, cursor + markerWindow + moveDuration * 1000);
                }
                cursor += boardWindow;
            });
            const reloadWindow = Math.max(Math.min(cursor, maxWindow), lastFinish);
            if (timeline && timeline.length > 0) {
                this._setTimeout(() => {
                    if (!this._fastForwarded) {
                        this.playTimeline(timeline, delay, nextUrl, boardPath);
                    }
                }, reloadWindow + 200);
            } else {
                this._setTimeout(reloadToBoard, reloadWindow);
            }
            return;
        }

        if (animationsElements.length > 0) {
            this._lockInteraction();
            playerElements.forEach(animateElement);
            const playerWindow = playerElements.length * perElementWindow;
            const enemyWindow = enemyElements.length * perElementWindow;
            const enemyMarkerWindow = enemyElements.length > 0 ? markerWindow : 0;
            const enemyStart = playerWindow + enemyMarkerWindow;
            const enemyFinished = enemyElements.length > 0 ? enemyStart + moveDuration * 1000 : 0;
            const reloadWindow = Math.max(Math.min(enemyStart + enemyWindow, maxWindow), enemyFinished);

            if (enemyElements.length > 0) {
                this._setTimeout(() => {
                    turnMarker(reloadWindow - playerWindow - 300, 'Enemy turn', () => this.fastForward(nextUrl, boardPath), this);
                }, playerWindow);
                this._setTimeout(() => {
                    enemyElements.forEach(animateElement);
                }, enemyStart);
            }

            this._setTimeout(reloadToBoard, reloadWindow);
        } else if (nextUrl && nextUrl !== boardPath()) {
            this._setTimeout(() => {
                window.location.href = nextUrl;
            }, delay / 2);
        } else {
            console.log(`No elements found with '${classSelector}' class.`);
        }
    }

    playTimeline(timeline, delay, nextUrl, boardPath) {
        if (!timeline || timeline.length === 0) {
            this._unlockInteraction();
            window.location.href = nextUrl || (boardPath ? boardPath() : '/');
            return;
        }

        const totalBudget = delay * 5;
        const stepBudget = totalBudget / Math.max(timeline.length, 1);
        let cursor = 0;

        timeline.forEach((step, index) => {
            const stepDuration = this._computeStepDuration(step, stepBudget);
            this._setTimeout(() => {
                if (!this._fastForwarded) {
                    this._playStep(step, stepDuration, delay);
                }
            }, cursor);
            cursor += stepDuration;
        });

        this._setTimeout(() => {
            this._unlockInteraction();
            if (!this._fastForwarded) {
                window.location.href = nextUrl || (boardPath ? boardPath() : '/');
            }
        }, cursor + 500);
    }

    _computeStepDuration(step, budget) {
        switch (step.kind) {
            case 'special-trigger':
                return Math.max(2000, budget * 1.5);
            case 'card-effect':
                return Math.max(800, budget);
            case 'participant-effect':
                return Math.max(1500, budget * 1.2);
            case 'shuffle-back': {
                const cardCount = (step.affectedCards || []).length;
                if (cardCount === 0) return 200;
                if (cardCount <= 3) return 1500;
                if (cardCount <= 8) return 2000;
                return 2500;
            }
            default:
                return budget;
        }
    }

    _playStep(step, duration, delay) {
        switch (step.kind) {
            case 'special-trigger':
                this._playTriggerStep(step, duration);
                break;
            case 'card-effect':
                this._playCardEffectStep(step, duration, delay);
                break;
            case 'participant-effect':
                this._playParticipantEffectStep(step, duration);
                break;
            case 'shuffle-back':
                this._playShuffleBack(step, duration);
                break;
        }
    }

    _playTriggerStep(step, duration) {
        if (step.banner) {
            showBanner(step.banner, duration, 'special', () => this.fastForward(
                document.getElementById('boardNext')?.dataset.nextUrl ?? '',
                () => {
                    const path = window.location.pathname;
                    let shortPath = path.substring(0, path.lastIndexOf('action'));
                    return shortPath || path;
                }
            ), this);
        }
        if (step.lane != null) {
            this._highlightLane(step.participantId, step.lane, duration, true);
        }
    }

    _playCardEffectStep(step, duration, delay) {
        const cards = step.affectedCards || [];
        if (cards.length === 0) return;

        const staggerTotal = Math.min(duration * 0.8, duration - 200);
        const perCardStagger = Math.max(50, staggerTotal / Math.max(cards.length, 1));
        const cardDuration = Math.min(600, Math.max(200, staggerTotal / 2));

        if (step.lane != null) {
            this._highlightLane(step.participantId, step.lane, duration, false);
        }

        cards.forEach((card, index) => {
            this._setTimeout(() => {
                this._animateCardEffect(card, cardDuration, delay);
            }, index * perCardStagger);
        });
    }

    _animateCardEffect(cardInfo, cardDuration, delay) {
        const selector = `[data-card-id="${cardInfo.cardId}"]`;
        const element = document.querySelector(selector);
        if (!element) return;

        if (cardInfo.trust && cardInfo.sourceLane === cardInfo.destinationLane) {
            element.classList.add('trust-glow');
            this._setTimeout(() => {
                element.classList.remove('trust-glow');
            }, cardDuration + 500);
            return;
        }

        const sourceLane = cardInfo.sourceLane;
        const sourceOrdinal = cardInfo.sourceOrdinal;
        const duplicate = duplicateCard(element, sourceLane, sourceOrdinal);
        if (duplicate) {
            const moveDuration = Math.min(1.0, cardDuration / 1000);
            duplicate.style.setProperty('--move-duration', `${moveDuration}s`);
            if (cardInfo.flipFaceUp) {
                duplicate.classList.add('flipFaceUp');
            }
            let revealed = false;
            const onReveal = () => {
                if (revealed) return;
                revealed = true;
                duplicate.remove();
                element.classList.remove('loading');
                if (cardInfo.trust) {
                    element.classList.add('trust-glow');
                    this._setTimeout(() => element.classList.remove('trust-glow'), 1500);
                }
            };
            duplicate.addEventListener('transitionend', onReveal, { once: true });
            this._setTimeout(onReveal, moveDuration * 1000 + 100);
            requestAnimationFrame(() => {
                duplicate.classList.add('to-original');
            });
        }
    }

    _playParticipantEffectStep(step, duration) {
        if (step.banner) {
            const variant = step.defeatedParticipantId ? 'defeat' : 'flee';
            showBanner(step.banner, duration, variant, () => this.fastForward(
                document.getElementById('boardNext')?.dataset.nextUrl ?? '',
                () => {
                    const path = window.location.pathname;
                    let shortPath = path.substring(0, path.lastIndexOf('action'));
                    return shortPath || path;
                }
            ), this);
        }
        if (step.defeatedParticipantId) {
            this._dimBoard(step.defeatedParticipantId);
        }
        if (step.fledParticipantId) {
            this._dimBoard(step.fledParticipantId);
        }
    }

    _playShuffleBack(step, duration) {
        const cards = step.affectedCards || [];
        if (cards.length === 0) {
            this._wiggleDeck(step.participantId);
            return;
        }

        const staggerTotal = Math.min(duration * 0.8, duration - 500);
        const perCardStagger = Math.max(50, staggerTotal / Math.max(cards.length, 1));
        const cardDuration = Math.min(800, Math.max(200, staggerTotal / 2));
        let completedCount = 0;

        cards.forEach((card, index) => {
            this._setTimeout(() => {
                this._flyCardToDeck(card, step.participantId, cardDuration, () => {
                    completedCount++;
                    if (completedCount >= cards.length) {
                        this._wiggleDeck(step.participantId);
                    }
                });
            }, index * perCardStagger);
        });
    }

    _makeCardClone() {
        const li = document.createElement('li');
        li.className = 'cardContainer faceDown';
        const div = document.createElement('div');
        div.className = 'card back smallCard';
        li.appendChild(div);
        return li;
    }

    _positionCloneAtSource(cardInfo, participantId) {
        const board = this._boardForParticipant(participantId);
        if (!board) return null;

        const isPlayer = board.classList.contains('playerBoard');
        const lane = cardInfo.sourceLane;
        const ordinal = cardInfo.sourceOrdinal || 0;

        let sourceContainer = null;
        const laneNames = {1: 'Intelligence', 2: 'Speed', 3: 'Visciousness', 4: 'Resolve'};

        if (lane === 0) {
            sourceContainer = isPlayer
                ? document.querySelector('.playerScreen .deckHand .hand')
                : board.querySelector('.enemyDeckHand .hand');
        } else if (lane > 0 && lane <= 4) {
            const laneEl = board.querySelector(`.lane.${laneNames[lane]}`);
            if (laneEl) {
                sourceContainer = findCardRowForOrdinal(laneEl, ordinal, 5);
            }
        }

        if (!sourceContainer) return null;

        const clone = this._makeCardClone();
        clone.classList.add('duplicate', 'shuffle-flying');
        const insertIndex = Math.min(Math.max(0, ordinal - 1), sourceContainer.children.length);
        const beforeEl = sourceContainer.children[insertIndex] ?? null;
        if (beforeEl) {
            sourceContainer.insertBefore(clone, beforeEl);
        } else {
            sourceContainer.appendChild(clone);
        }

        const sourceRect = clone.getBoundingClientRect();
        return {element: clone, sourceRect};
    }

    _flyCardToDeck(cardInfo, participantId, duration, onComplete) {
        const board = this._boardForParticipant(participantId);
        if (!board) {
            if (onComplete) onComplete();
            return;
        }

        const isPlayer = board.classList.contains('playerBoard');
        const deck = isPlayer
            ? document.querySelector('.playerScreen .deckHand .deck')
            : board.querySelector('.enemyDeckHand .deck');
        if (!deck) {
            if (onComplete) onComplete();
            return;
        }

        const placed = this._positionCloneAtSource(cardInfo, participantId);
        if (!placed) {
            if (onComplete) onComplete();
            return;
        }

        const duplicate = placed.element;
        const elRect = placed.sourceRect;
        const deckRect = deck.getBoundingClientRect();

        duplicate.style.position = 'fixed';
        duplicate.style.left = `${elRect.left}px`;
        duplicate.style.top = `${elRect.top}px`;
        duplicate.style.width = `${elRect.width}px`;
        duplicate.style.height = `${elRect.height}px`;
        duplicate.style.transition = `all ${duration}ms cubic-bezier(.2, .8, .2, 1)`;
        duplicate.style.pointerEvents = 'none';
        duplicate.style.zIndex = 1000;
        document.body.appendChild(duplicate);

        requestAnimationFrame(() => {
            duplicate.style.left = `${deckRect.left + deckRect.width / 2 - elRect.width / 2}px`;
            duplicate.style.top = `${deckRect.top + deckRect.height / 2 - elRect.height / 2}px`;
            duplicate.style.transform = 'scale(0.8)';
            duplicate.style.opacity = '0.3';
        });

        this._setTimeout(() => {
            duplicate.remove();
            if (onComplete) onComplete();
        }, duration + 50);
    }

    _boardForParticipant(participantId) {
        const playerBoard = document.querySelector('.playerBoard');
        if (playerBoard && playerBoard.dataset.participantId == participantId) {
            return playerBoard;
        }
        const boards = document.querySelectorAll('.enemyBoard');
        for (const board of boards) {
            if (board.dataset.participantId == participantId) {
                return board;
            }
        }
        return null;
    }

    _wiggleDeck(participantId) {
        const board = this._boardForParticipant(participantId);
        if (!board) return;
        const isPlayer = board.classList.contains('playerBoard');
        const deck = isPlayer
            ? document.querySelector('.playerScreen .deckHand .deck')
            : board.querySelector('.enemyDeckHand .deck');
        if (!deck) return;
        deck.classList.add('deck-shuffle');
        this._setTimeout(() => {
            deck.classList.remove('deck-shuffle');
        }, 600);
    }

    _highlightLane(participantId, laneNumber, duration, isTrigger) {
        const laneNames = {1: 'Intelligence', 2: 'Speed', 3: 'Visciousness', 4: 'Resolve'};
        const name = laneNames[laneNumber];
        if (!name) return;

        const board = this._boardForParticipant(participantId);
        if (!board) return;

        const lane = board.querySelector(`.lane.${name}`);
        if (!lane) return;
        lane.classList.add('lane-highlight');

        const revealedCards = lane.querySelectorAll('.cardContainer:not(.faceDown)');
        revealedCards.forEach(c => c.classList.add('card-highlight'));

        this._setTimeout(() => {
            lane.classList.remove('lane-highlight');
            revealedCards.forEach(c => c.classList.remove('card-highlight'));
        }, duration);
    }

    _dimBoard(participantId) {
        const board = this._boardForParticipant(participantId);
        if (board) {
            board.classList.add('board-dimmed');
        }
    }
}

/**
 * Show a banner overlay with fast-forward button.
 */
function showBanner(text, holdMs = 2000, variant = 'special', onFastForward, loaderInstance) {
    const banner = document.createElement('div');
    banner.className = `timeline-banner banner-${variant}`;
    Object.assign(banner.style, {
        position: 'fixed',
        top: '30%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        padding: '0.75em 2em 2.5em 2em',
        fontSize: '1.5rem',
        fontWeight: 'bold',
        color: '#fff',
        borderRadius: '0.5em',
        border: '3px solid',
        boxShadow: '0 0 1.5em rgba(0, 0, 0, 0.7)',
        zIndex: 1000,
        opacity: '0',
        transition: 'opacity 0.3s ease-in-out',
        textAlign: 'center',
        maxWidth: '80%',
    });

    // Banner text
    const textSpan = document.createElement('span');
    textSpan.textContent = text;
    banner.appendChild(textSpan);

    // Fast-forward button
    const ffBtn = document.createElement('button');
    ffBtn.textContent = '⏩ Fast Forward';
    Object.assign(ffBtn.style, {
        position: 'absolute',
        bottom: '0.3em',
        right: '0.5em',
        fontSize: '0.65rem',
        padding: '0.15em 0.5em',
        border: '1px solid rgba(255,255,255,0.5)',
        borderRadius: '0.3em',
        background: 'rgba(255,255,255,0.15)',
        color: '#fff',
        cursor: 'pointer',
        pointerEvents: 'auto',
        zIndex: 10001,
    });
    ffBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        if (loaderInstance && onFastForward) {
            onFastForward();
        }
    });
    banner.appendChild(ffBtn);

    // Variant styling
    if (variant === 'special') {
        banner.style.borderColor = 'gold';
        banner.style.background = 'linear-gradient(135deg, #2a1a00, #4a3000)';
    } else if (variant === 'defeat') {
        banner.style.borderColor = '#ff4444';
        banner.style.background = 'linear-gradient(135deg, #2a0000, #4a0000)';
    } else if (variant === 'flee') {
        banner.style.borderColor = '#888';
        banner.style.background = 'linear-gradient(135deg, #1a1a2a, #2a2a3a)';
    }

    document.body.appendChild(banner);
    requestAnimationFrame(() => {
        banner.style.opacity = '1';
    });
    const tid = setTimeout(() => {
        banner.style.opacity = '0';
        setTimeout(() => banner.remove(), 300);
    }, Math.max(holdMs, 0));
    return banner;
}

function turnMarker(holdMs = 1200, text = 'Enemy turn', onFastForward, loaderInstance) {
    const marker = document.createElement('div');
    marker.className = 'enemyTurnMarker';
    Object.assign(marker.style, {
        position: 'fixed',
        top: '35%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        padding: '0.5em 1.5em 2em 1.5em',
        fontSize: '2rem',
        fontWeight: 'bold',
        color: '#fff',
        background: 'rgba(20, 20, 30, 0.8)',
        border: '2px solid rgba(255, 255, 255, 0.6)',
        borderRadius: '0.5em',
        boxShadow: '0 0 1em rgba(0, 0, 0, 0.6)',
        zIndex: 1000,
        opacity: '0',
        transition: 'opacity 0.3s ease-in-out',
        textAlign: 'center',
    });

    // Text
    const textSpan = document.createElement('span');
    textSpan.textContent = text;
    marker.appendChild(textSpan);

    // Fast-forward button
    const ffBtn = document.createElement('button');
    ffBtn.textContent = '⏩ Fast Forward';
    Object.assign(ffBtn.style, {
        position: 'absolute',
        bottom: '0.2em',
        right: '0.4em',
        fontSize: '0.6rem',
        padding: '0.1em 0.4em',
        border: '1px solid rgba(255,255,255,0.4)',
        borderRadius: '0.3em',
        background: 'rgba(255,255,255,0.12)',
        color: '#fff',
        cursor: 'pointer',
        pointerEvents: 'auto',
        zIndex: 10001,
    });
    ffBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        if (loaderInstance && onFastForward) {
            onFastForward();
        }
    });
    marker.appendChild(ffBtn);

    document.body.appendChild(marker);
    requestAnimationFrame(() => {
        marker.style.opacity = '1';
    });
    setTimeout(() => {
        marker.style.opacity = '0';
        setTimeout(() => marker.remove(), 300);
    }, Math.max(holdMs, 0));
    return marker;
}

function focusEnemySide() {
    const playerScreen = document.querySelector('.playerScreen');
    if (playerScreen) {
        playerScreen.classList.add('enemyTurnFocus');
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function findCardRowForOrdinal(laneElement, ordinal, cardsPerRow) {
    const rows = laneElement.querySelectorAll(':scope > ul.cardRow');
    if (rows.length <= 1) return rows[0] || null;
    const cpr = cardsPerRow || 5;
    const rowIndex = Math.min(Math.max(0, Math.floor((ordinal - 1) / cpr)), rows.length - 1);
    return rows[rowIndex];
}

function duplicateCard(element, lane, ordinal)
{
    let laneElement  = null;
    const cardsPerRow = 5;
    const duplicate = element.cloneNode(true);
    duplicate.classList.add('duplicate');
    const enemyBoard = element.closest('.enemyBoard');
    if (enemyBoard) {
        const enemyLaneNames = {1: 'Intelligence', 2: 'Speed', 3: 'Visciousness', 4: 'Resolve'};
        if (lane < 0) {
            laneElement = enemyBoard.querySelector('.enemyDeckHand .deck');
        } else if (lane === 0) {
            laneElement = enemyBoard.querySelector('.enemyDeckHand .hand');
        } else if (enemyLaneNames[lane]) {
            const enemyLane = enemyBoard.querySelector(`.lane.${enemyLaneNames[lane]}`);
            if (enemyLane) {
                laneElement = findCardRowForOrdinal(enemyLane, ordinal, cardsPerRow);
            }
        }
    } else {
        if (lane < 0) {
            laneElement = document.querySelector('.playerScreen .deckHand .deck');
            duplicate.classList.add('faceDown');
            const innerCard = duplicate.querySelector('.card');
            if (innerCard) {
                innerCard.classList.add('back');
                innerCard.replaceChildren();
            }
        } else switch (lane) {
            case 0:
                laneElement = document.querySelector('.playerScreen .deckHand .hand');
                break;
            case 1:
                laneElement = findCardRowForOrdinal(
                    document.querySelector('.playerScreen .playerBoard .lane.Intelligence'), ordinal, cardsPerRow);
                break;
            case 2:
                laneElement = findCardRowForOrdinal(
                    document.querySelector('.playerScreen .playerBoard .lane.Speed'), ordinal, cardsPerRow);
                break;
            case 3:
                laneElement = findCardRowForOrdinal(
                    document.querySelector('.playerScreen .playerBoard .lane.Visciousness'), ordinal, cardsPerRow);
                break;
            case 4:
                laneElement = findCardRowForOrdinal(
                    document.querySelector('.playerScreen .playerBoard .lane.Resolve'), ordinal, cardsPerRow);
                break;
        }
    }
    if (laneElement) {
        const insertIndex = Math.min(ordinal - 1, laneElement.children.length);
        const beforeElement = laneElement.children[insertIndex] ?? null;

        if (beforeElement) {
            laneElement.insertBefore(duplicate, beforeElement);
        } else {
            laneElement.appendChild(duplicate);
        }
        const originalRect = element.getBoundingClientRect();
        const duplicateRect = duplicate.getBoundingClientRect();
        if (lane > 0){
            duplicate.classList.add('flipFaceUp');
            duplicate.classList.add('faceDown');
            const innerCard = duplicate.querySelector('.card');
            if (innerCard) {
                innerCard.classList.add('back');
                innerCard.replaceChildren();
            }
        } else{
            duplicate.style.setProperty('--move-x', `${originalRect.left - duplicateRect.left}px`);
            duplicate.style.setProperty('--move-y', `${originalRect.top - duplicateRect.top}px`);
        }
        return duplicate;
    }
    return null;
}

document.addEventListener('DOMContentLoaded', () => {
    window.loadingAnimations = new loadingAnimationsSystem();
});
