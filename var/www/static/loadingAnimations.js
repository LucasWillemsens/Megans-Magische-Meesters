class loadingAnimationsSystem {
    constructor() {
        this.init();
    }

    init() {
        this.Animate();
    }

    Animate(classSelector = 'loading', delay = 1200) {
        const animationsElements = Array.from(document.getElementsByClassName(classSelector));
        const phase = document.getElementById('turnPhase')?.dataset.phase ?? '';
        const nextUrl = document.getElementById('boardNext')?.dataset.nextUrl ?? '';
        const moveDuration = Math.max(0.2, Math.min(1.2, delay / 1000));
        const perElementWindow = delay / 2;
        const markerWindow = delay / 3;
        const maxWindow = delay * 5;

        // Check for timeline steps (special draw sequence)
        const timelineElement = document.getElementById('timelineSteps');
        const timeline = timelineElement ? JSON.parse(timelineElement.textContent) : null;

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
                    setTimeout(revealElement, moveDuration * 1000 + 100);
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

        const boardPath = () => {
            const path = window.location.pathname;
            let shortPath = path.substring(0, path.lastIndexOf('action'));
            if (!shortPath ) {
                shortPath = path;
            }
            return shortPath;
        };

        const reloadToBoard = () => {
            window.location.href = nextUrl || boardPath();
        };

        if (phase === 'player') {
            turnMarker(delay, 'Your turn');
            animationsElements.forEach((element) => element.classList.remove('loading'));
            const deckHand = document.querySelector('.playerScreen .deckHand');
            if (deckHand) {
                deckHand.scrollIntoView({ behavior: 'smooth', block: 'end' });
            }
            return;
        }

        if (phase === 'playerMoves') {
            playerElements.forEach(animateElement);
            const playerWindow = playerElements.length * perElementWindow;
            const playerFinished = playerElements.length > 0 ? moveDuration * 1000 : 0;
            if (timeline && timeline.length > 0) {
                // Play timeline after draw animations finish
                setTimeout(() => {
                    this.playTimeline(timeline, delay, nextUrl, boardPath);
                }, Math.max(playerWindow, playerFinished) + 200);
            } else {
                const reloadWindow = Math.max(
                    Math.min(Math.max(playerWindow, delay / 2), maxWindow),
                    playerFinished,
                );
                setTimeout(reloadToBoard, reloadWindow);
            }
            return;
        }

        if (phase === 'enemy') {
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
                setTimeout(() => {
                    turnMarker(boardWindow - 300, `${name}'s turn`);
                }, cursor);
                if (boardElements.length > 0) {
                    setTimeout(() => {
                        boardElements.forEach(animateElement);
                    }, cursor + markerWindow);
                    lastFinish = Math.max(lastFinish, cursor + markerWindow + moveDuration * 1000);
                }
                cursor += boardWindow;
            });
            const reloadWindow = Math.max(Math.min(cursor, maxWindow), lastFinish);
            if (timeline && timeline.length > 0) {
                // Play timeline after enemy animations finish
                setTimeout(() => {
                    this.playTimeline(timeline, delay, nextUrl, boardPath);
                }, reloadWindow + 200);
            } else {
                setTimeout(reloadToBoard, reloadWindow);
            }
            return;
        }

        if (animationsElements.length > 0) {
            playerElements.forEach(animateElement);
            const playerWindow = playerElements.length * perElementWindow;
            const enemyWindow = enemyElements.length * perElementWindow;
            const enemyMarkerWindow = enemyElements.length > 0 ? markerWindow : 0;
            const enemyStart = playerWindow + enemyMarkerWindow;
            const enemyFinished = enemyElements.length > 0 ? enemyStart + moveDuration * 1000 : 0;
            const reloadWindow = Math.max(Math.min(enemyStart + enemyWindow, maxWindow), enemyFinished);

            if (enemyElements.length > 0) {
                setTimeout(() => {
                    turnMarker(reloadWindow - playerWindow - 300);
                }, playerWindow);
                setTimeout(() => {
                    enemyElements.forEach(animateElement);
                }, enemyStart);
            }

            setTimeout(reloadToBoard, reloadWindow);
        } else if (nextUrl && nextUrl !== boardPath()) {
            setTimeout(() => {
                window.location.href = nextUrl;
            }, delay / 2);
        } else {
            console.log(`No elements found with '${classSelector}' class.`);
        }
    }

    /**
     * Play a timeline of steps sequentially.
     * Each step waits for the previous step's animations to finish.
     */
    playTimeline(timeline, delay, nextUrl, boardPath) {
        if (!timeline || timeline.length === 0) {
            window.location.href = nextUrl || (boardPath ? boardPath() : '/');
            return;
        }

        // Fixed total budget for the whole sequence
        const totalBudget = delay * 5; // ~6 seconds
        const stepBudget = totalBudget / Math.max(timeline.length, 1);
        let cursor = 0;

        timeline.forEach((step, index) => {
            const stepDuration = this._computeStepDuration(step, stepBudget);
            setTimeout(() => {
                this._playStep(step, stepDuration, delay);
            }, cursor);
            cursor += stepDuration;
        });

        // After all steps complete, reload to nextUrl
        setTimeout(() => {
            window.location.href = nextUrl || (boardPath ? boardPath() : '/');
        }, cursor + 500);
    }

    _computeStepDuration(step, budget) {
        switch (step.kind) {
            case 'special-trigger':
                return Math.max(2000, budget * 1.5); // Banner needs time to read
            case 'card-effect':
                return Math.max(800, budget);
            case 'participant-effect':
                return Math.max(1500, budget * 1.2);
            case 'shuffle-back': {
                const cardCount = (step.affectedCards || []).length;
                if (cardCount === 0) return 200;
                if (cardCount <= 3) return 1500;
                if (cardCount <= 8) return 2000;
                return 2500; // Compress per-card stagger for large counts
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
        // Show banner
        if (step.banner) {
            showBanner(step.banner, duration, 'special');
        }
        // Highlight the lane of the winning stat
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

        // Highlight destination lane
        if (step.lane != null) {
            this._highlightLane(step.participantId, step.lane, duration, false);
        }

        cards.forEach((card, index) => {
            setTimeout(() => {
                this._animateCardEffect(card, cardDuration, delay);
            }, index * perCardStagger);
        });
    }

    _animateCardEffect(cardInfo, cardDuration, delay) {
        // Find the card element by data-card-id
        const selector = `[data-card-id="${cardInfo.cardId}"]`;
        const element = document.querySelector(selector);
        if (!element) return;

        // Determine if this is a trust-only effect (no flight, just glow)
        if (cardInfo.trust && cardInfo.sourceLane === cardInfo.destinationLane) {
            // Card stays in place, just add trust glow
            element.classList.add('trust-glow');
            setTimeout(() => {
                element.classList.remove('trust-glow');
            }, cardDuration + 500);
            return;
        }

        // Use duplicateCard for flight animations
        const sourceLane = cardInfo.sourceLane;
        const sourceOrdinal = cardInfo.sourceOrdinal;
        // Create duplicate flying from source to the element's current position
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
                    setTimeout(() => element.classList.remove('trust-glow'), 1500);
                }
            };
            duplicate.addEventListener('transitionend', onReveal, { once: true });
            setTimeout(onReveal, moveDuration * 1000 + 100);
            requestAnimationFrame(() => {
                duplicate.classList.add('to-original');
            });
        }
    }

    _playParticipantEffectStep(step, duration) {
        // Show outcome banner
        if (step.banner) {
            const variant = step.defeatedParticipantId ? 'defeat' : 'flee';
            showBanner(step.banner, duration, variant);
        }
        // Dim the affected board
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
            // No cards to shuffle — just a brief deck wiggle
            this._wiggleDeck(step.participantId);
            return;
        }

        const staggerTotal = Math.min(duration * 0.8, duration - 500); // leave 500ms for wiggle
        const perCardStagger = Math.max(50, staggerTotal / Math.max(cards.length, 1));
        const cardDuration = Math.min(800, Math.max(200, staggerTotal / 2));
        let completedCount = 0;

        cards.forEach((card, index) => {
            setTimeout(() => {
                this._flyCardToDeck(card, step.participantId, cardDuration, () => {
                    completedCount++;
                    // Wiggle the deck after all cards arrive
                    if (completedCount >= cards.length) {
                        this._wiggleDeck(step.participantId);
                    }
                });
            }, index * perCardStagger);
        });
    }

    /**
     * Create a face-down card element for animation purposes.
     */
    _makeCardClone() {
        const li = document.createElement('li');
        li.className = 'cardContainer faceDown';
        const div = document.createElement('div');
        div.className = 'card back smallCard';
        li.appendChild(div);
        return li;
    }

    /**
     * Insert a temporary card element at the source lane/hand position
     * (determined by cardInfo.sourceLane / cardInfo.sourceOrdinal) and return it.
     * The clone is NOT inserted into the DOM; this function only builds it.
     * Returns {element, sourceRect} where sourceRect is the bounding box of
     * the source position, or null if the source container can't be found.
     */
    _positionCloneAtSource(cardInfo, participantId) {
        const board = this._boardForParticipant(participantId);
        if (!board) return null;

        const isPlayer = board.classList.contains('playerBoard');
        const lane = cardInfo.sourceLane;
        const ordinal = cardInfo.sourceOrdinal || 0;

        // Find the source container (hand or lane cardRow)
        let sourceContainer = null;
        const laneNames = {1: 'Intelligence', 2: 'Speed', 3: 'Visciousness', 4: 'Resolve'};

        if (lane === 0) {
            // Hand
            sourceContainer = isPlayer
                ? document.querySelector('.playerScreen .deckHand .hand')
                : board.querySelector('.enemyDeckHand .hand');
        } else if (lane > 0 && lane <= 4) {
            // A lane — find the correct cardRow by ordinal
            const laneEl = board.querySelector(`.lane.${laneNames[lane]}`);
            if (laneEl) {
                sourceContainer = findCardRowForOrdinal(laneEl, ordinal, 5);
            }
        }

        if (!sourceContainer) return null;

        // Create a card clone and add it at the ordinal position in the container
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

        // Position a clone at the SOURCE location (lane or hand before shuffleBoard)
        const placed = this._positionCloneAtSource(cardInfo, participantId);
        if (!placed) {
            if (onComplete) onComplete();
            return;
        }

        const duplicate = placed.element;
        const elRect = placed.sourceRect;
        const deckRect = deck.getBoundingClientRect();

        // Immediately re-position as fixed so it doesn't affect layout during flight
        duplicate.style.position = 'fixed';
        duplicate.style.left = `${elRect.left}px`;
        duplicate.style.top = `${elRect.top}px`;
        duplicate.style.width = `${elRect.width}px`;
        duplicate.style.height = `${elRect.height}px`;
        duplicate.style.transition = `all ${duration}ms cubic-bezier(.2, .8, .2, 1)`;
        duplicate.style.pointerEvents = 'none';
        duplicate.style.zIndex = 1000;
        document.body.appendChild(duplicate);

        // Animate to deck center at normal size, fading out
        requestAnimationFrame(() => {
            duplicate.style.left = `${deckRect.left + deckRect.width / 2 - elRect.width / 2}px`;
            duplicate.style.top = `${deckRect.top + deckRect.height / 2 - elRect.height / 2}px`;
            duplicate.style.transform = 'scale(0.8)';
            duplicate.style.opacity = '0.3';
        });

        setTimeout(() => {
            duplicate.remove();
            if (onComplete) onComplete();
        }, duration + 50);
    }

    /**
     * Find the board element (player or enemy) for a given participantId.
     * Returns the .playerBoard or .enemyBoard element, or null.
     */
    _boardForParticipant(participantId) {
        // Try player board first
        const playerBoard = document.querySelector('.playerBoard');
        if (playerBoard && playerBoard.dataset.participantId == participantId) {
            return playerBoard;
        }
        // Search enemy boards
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
        setTimeout(() => {
            deck.classList.remove('deck-shuffle');
        }, 600);
    }

    _highlightLane(participantId, laneNumber, duration, isTrigger) {
        const laneNames = {1: 'Intelligence', 2: 'Speed', 3: 'Visciousness', 4: 'Resolve'};
        const name = laneNames[laneNumber];
        if (!name) return;

        // Find the board for this participant
        const board = this._boardForParticipant(participantId);
        if (!board) return;

        const lane = board.querySelector(`.lane.${name}`);
        if (!lane) return;
        lane.classList.add('lane-highlight');

        // Also highlight revealed cards in this lane
        const revealedCards = lane.querySelectorAll('.cardContainer:not(.faceDown)');
        revealedCards.forEach(c => c.classList.add('card-highlight'));

        setTimeout(() => {
            lane.classList.remove('lane-highlight');
            revealedCards.forEach(c => c.classList.remove('card-highlight'));
        }, duration);
    }

    _dimBoard(participantId) {
        // Dim the board of the given participant
        const board = this._boardForParticipant(participantId);
        if (board) {
            board.classList.add('board-dimmed');
        }
    }
}

/**
 * Show a banner overlay with the given text and variant styling.
 * Variants: 'special' (gold), 'defeat' (red), 'flee' (grey).
 */
function showBanner(text, holdMs = 2000, variant = 'special') {
    const banner = document.createElement('div');
    banner.className = `timeline-banner banner-${variant}`;
    banner.textContent = text;
    Object.assign(banner.style, {
        position: 'fixed',
        top: '30%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        padding: '0.75em 2em',
        fontSize: '1.5rem',
        fontWeight: 'bold',
        color: '#fff',
        borderRadius: '0.5em',
        border: '3px solid',
        boxShadow: '0 0 1.5em rgba(0, 0, 0, 0.7)',
        zIndex: 1000,
        pointerEvents: 'none',
        opacity: '0',
        transition: 'opacity 0.3s ease-in-out',
        textAlign: 'center',
        maxWidth: '80%',
    });

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
    setTimeout(() => {
        banner.style.opacity = '0';
        setTimeout(() => banner.remove(), 300);
    }, Math.max(holdMs, 0));
    return banner;
}

function turnMarker(holdMs = 1200, text = 'Enemy turn') {
    const marker = document.createElement('div');
    marker.className = 'enemyTurnMarker';
    marker.textContent = text;
    Object.assign(marker.style, {
        position: 'fixed',
        top: '35%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        padding: '0.5em 1.5em',
        fontSize: '2rem',
        fontWeight: 'bold',
        color: '#fff',
        background: 'rgba(20, 20, 30, 0.8)',
        border: '2px solid rgba(255, 255, 255, 0.6)',
        borderRadius: '0.5em',
        boxShadow: '0 0 1em rgba(0, 0, 0, 0.6)',
        zIndex: 1000,
        pointerEvents: 'none',
        opacity: '0',
        transition: 'opacity 0.3s ease-in-out',
    });
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

/**
 * Find the correct .cardRow within a lane for a given ordinal.
 * When a lane has multiple rows (overflow), this calculates which row
 * the ordinal falls into based on cards-per-row.
 */
function findCardRowForOrdinal(laneElement, ordinal, cardsPerRow) {
    const rows = laneElement.querySelectorAll(':scope > ul.cardRow');
    if (rows.length <= 1) return rows[0] || null;
    const cpr = cardsPerRow || 5; // fallback default
    const rowIndex = Math.min(Math.max(0, Math.floor((ordinal - 1) / cpr)), rows.length - 1);
    return rows[rowIndex];
}

function duplicateCard(element, lane, ordinal)
{
    let laneElement  = null;
    const cardsPerRow = 5; // Default, will be recalculated by LaneCardStacking
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
