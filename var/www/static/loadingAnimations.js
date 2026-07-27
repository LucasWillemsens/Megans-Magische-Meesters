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
        const moveDuration = Math.max(0.2, Math.min(1.2, delay / 1000));
        const perElementWindow = delay / 2;
        const markerWindow = delay / 3;
        const maxWindow = delay * 5;

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

        const reloadToBoard = () => {
            const path = window.location.pathname;
            let shortPath = path.substring(0, path.lastIndexOf('action'));
            if (!shortPath ) {
                shortPath = path;
            }
            window.location.href = shortPath;
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
            const reloadWindow = Math.max(
                Math.min(Math.max(playerWindow, delay / 2), maxWindow),
                playerFinished,
            );
            setTimeout(reloadToBoard, reloadWindow);
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
            setTimeout(reloadToBoard, reloadWindow);
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
        } else {
            console.log(`No elements found with '${classSelector}' class.`);
        }
    }
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

function duplicateCard(element, lane, ordinal)
{
    let laneElement  = null;
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
