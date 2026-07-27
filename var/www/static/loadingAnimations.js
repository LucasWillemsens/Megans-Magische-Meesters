class loadingAnimationsSystem {
    constructor() {
        // this.draggedCard = null;
        // this.dropZones = new Map();
        this.init();
    }

    init() {
        // console.log('Initializing Loading Animations System');
        this.Animate();
    }

    Animate(classSelector = 'loading', delay = 1200) {
        const animationsElements = Array.from(document.getElementsByClassName(classSelector));
        // cross-render turn sequence, rendered by the server (see viewBoard):
        // "playerMoves" (end_turn POST: own moves, then always reload),
        // "enemy" (a floating marker per opponent + their moves, then reload),
        // "player" (own turn starts again: marker only, no reload)
        const phase = document.getElementById('turnPhase')?.dataset.phase ?? '';
        const moveDuration = Math.max(0.2, Math.min(1.2, delay / 1000));
        const perElementWindow = delay / 2;
        const markerWindow = delay / 3;
        const maxWindow = delay * 5;

        const animateElement = (element) => {
            element.classList.add('animating');
            // console.log(`animating element:`, element);
            const lane  = element.getAttribute('data-source-lane');
            const ordinal = element.getAttribute('data-source-ordinal');
            if (lane != null && ordinal != null && lane != "" && ordinal != ""){
                const duplicate = duplicateCard(element, parseInt(lane), parseInt(ordinal));
                if (duplicate) {
                    duplicate.style.setProperty('--move-duration', `${moveDuration}s`);
                    // the original is hidden from page load by the .loading CSS
                    // rule (also during any marker beat before this flight);
                    // once the duplicate lands, the original takes over its
                    // final position and the duplicate is removed again
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
                        if (lane <= 0){
                            duplicate.classList.add('to-original');
                        }
                    });
                    return;
                }
            }
            // nothing to fly in (no source position): never leave the card
            // stuck invisible behind the .loading CSS rule
            element.classList.remove('loading');
        };

        // player actions always play before enemy actions
        const playerElements = animationsElements.filter((element) => element.closest('.enemyBoard') == null);
        const enemyElements = animationsElements.filter((element) => element.closest('.enemyBoard') != null);

        const reloadToBoard = () => {
            // console.log('Reloading window after animations');
            const path = window.location.pathname;
            // console.log('Current path:', path);
            let shortPath = path.substring(0, path.lastIndexOf('action'));
            if (!shortPath ) {
                shortPath = path;
            }
            window.location.href = shortPath;
        };

        if (phase === 'player') {
            // the player's own turn starts again: always show the marker, even
            // when the player has no moves waiting, and hand the focus back to
            // the player's deck and hand at the bottom of the page
            turnMarker(delay, 'Your turn');
            // this render plays no animations and never reloads, so no card
            // may stay hidden behind the .loading CSS rule here
            animationsElements.forEach((element) => element.classList.remove('loading'));
            const deckHand = document.querySelector('.playerScreen .deckHand');
            if (deckHand) {
                deckHand.scrollIntoView({ behavior: 'smooth', block: 'end' });
            }
            return;
        }

        if (phase === 'playerMoves') {
            // the player's own moves after 'end turn'; reload afterwards even
            // with zero moves so the enemy phase always follows
            playerElements.forEach(animateElement);
            const playerWindow = playerElements.length * perElementWindow;
            const playerFinished = playerElements.length > 0 ? moveDuration * 1000 : 0;
            const reloadWindow = Math.max(
                Math.min(Math.max(playerWindow, delay / 2), maxWindow),
                playerFinished,
            );
            setTimeout(reloadToBoard, reloadWindow);
            return;
        }

        if (phase === 'enemy') {
            // the enemy turn: focus slides up to the enemy boards and the
            // player's deck/hand is de-emphasized while the opponents act
            focusEnemySide();
            playerElements.forEach(animateElement);
            let cursor = playerElements.length * perElementWindow;
            let lastFinish = cursor;
            const enemyBoards = Array.from(document.querySelectorAll('.enemyBoard'));
            if (enemyBoards.length > 0) {
                // give the upward scroll a beat to land before the first marker
                cursor += 300;
            }
            enemyBoards.forEach((board) => {
                // every opponent gets a floating marker with their name, even
                // an opponent without any actions this turn
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
            // stay readable: never endless, but never reload mid-animation
            const reloadWindow = Math.max(Math.min(cursor, maxWindow), lastFinish);
            setTimeout(reloadToBoard, reloadWindow);
            return;
        }

        if (animationsElements.length > 0) {
            // console.log(`Found ${animationsElements.length} elements with '${classSelector}' class.`);
            playerElements.forEach(animateElement);

            // the viewing window scales with every loading element, player and
            // enemy alike, but stays readable: long enough for every enemy
            // animation to finish before the reload fires, never endless
            const playerWindow = playerElements.length * perElementWindow;
            const enemyWindow = enemyElements.length * perElementWindow;
            // the floating enemy turn marker gets a beat to land before the
            // enemy cards move
            const enemyMarkerWindow = enemyElements.length > 0 ? markerWindow : 0;
            const enemyStart = playerWindow + enemyMarkerWindow;
            const enemyFinished = enemyElements.length > 0 ? enemyStart + moveDuration * 1000 : 0;
            const reloadWindow = Math.max(Math.min(enemyStart + enemyWindow, maxWindow), enemyFinished);

            if (enemyElements.length > 0) {
                // mark the start of the enemy turn so the player can follow
                // what happened, then play the enemy animations
                setTimeout(() => {
                    turnMarker(reloadWindow - playerWindow - 300);
                }, playerWindow);
                setTimeout(() => {
                    enemyElements.forEach(animateElement);
                }, enemyStart);
            }

            setTimeout(reloadToBoard, reloadWindow);
        } else {
            console.log(`No elements found with '${classSelector}' class.`);
        }
    }
}

// floating text that marks whose turn it is, shown before that side's action
// animations so the player can follow what happened
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

// during the enemy turn the focus slides up to the enemy boards (their deck
// and hand live at the top of the page) and the player's own deck/hand is
// greyed out until the player's turn starts again
function focusEnemySide() {
    const playerScreen = document.querySelector('.playerScreen');
    if (playerScreen) {
        playerScreen.classList.add('enemyTurnFocus');
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

// //adds a duplicate card in the lane or hand, based on the source lane integer
function duplicateCard(element, lane, ordinal)
{
    let laneElement  = null;
    const duplicate = element.cloneNode(true);
    duplicate.classList.add('duplicate');
    const enemyBoard = element.closest('.enemyBoard');
    if (enemyBoard) {
        // enemy cards animate from their source position inside their own
        // board: the deck (negative source lane), the hand (0) or a lane
        const enemyLaneNames = {1: 'Intelligence', 2: 'Speed', 3: 'Visciousness', 4: 'Resolve'};
        if (lane < 0) {
            laneElement = enemyBoard.querySelector('.enemyDeckHand .deck');
        } else if (lane === 0) {
            laneElement = enemyBoard.querySelector('.enemyDeckHand .hand');
        } else if (enemyLaneNames[lane]) {
            laneElement = enemyBoard.querySelector(`.lane.${enemyLaneNames[lane]} .cardRow`);
        }
    } else {
        switch (lane) {
            case 0:
                laneElement = document.querySelector('.playerScreen .deckHand .hand');
                break;
            case 1:
                laneElement = document.querySelector('.playerScreen .playerBoard .lane.Intelligence .cardRow');
                break;
            case 2:
                laneElement = document.querySelector('.playerScreen .playerBoard .lane.Speed .cardRow');
                break;
            case 3:
                laneElement = document.querySelector('.playerScreen .playerBoard .lane.Visciousness .cardRow');
                break;
            case 4:
                laneElement = document.querySelector('.playerScreen .playerBoard .lane.Resolve .cardRow');
                break;
        }
    }
    // console.log("laneElement found: ", laneElement);
    if (laneElement) {
        const insertIndex = Math.min(ordinal - 1, laneElement.children.length);
        const beforeElement = laneElement.children[insertIndex] ?? null;

        if (beforeElement) {
            laneElement.insertBefore(duplicate, beforeElement);
        } else {
            laneElement.appendChild(duplicate);
        }
        // console.log(`Duplicated element(${duplicate}) in lane ${lane} at ordinal ${ordinal}`);
        const originalRect = element.getBoundingClientRect();
        const duplicateRect = duplicate.getBoundingClientRect();
        // console.log(`Original Rect:`, originalRect, `Duplicate Rect:`, duplicateRect);
        if (lane > 0){
            duplicate.classList.add('flipFaceUp');
            // duplicate.style.setProperty('position', 'absolute');
            // duplicate.style.setProperty('top', `${originalRect.top}px`);
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
