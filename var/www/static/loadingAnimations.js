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
        if (animationsElements.length > 0) {
            // console.log(`Found ${animationsElements.length} elements with '${classSelector}' class.`);
            const moveDuration = Math.max(0.2, Math.min(1.2, delay / 1000));
            const animateElement = (element) => {
                element.classList.add('animating');
                // console.log(`animating element:`, element);
                const lane  = element.getAttribute('data-source-lane');
                const ordinal = element.getAttribute('data-source-ordinal');
                if (lane != null && ordinal != null && lane != "" && ordinal != ""){
                    const duplicate = duplicateCard(element, parseInt(lane), parseInt(ordinal));
                    if (duplicate) {
                        duplicate.style.setProperty('--move-duration', `${moveDuration}s`);
                        requestAnimationFrame(() => {
                            if (lane == 0){    
                                duplicate.classList.add('to-original');
                            }
                        });
                    }
                    element.setAttribute("hidden","true");
                }
            };

            // player actions always play before enemy actions
            const playerElements = animationsElements.filter((element) => element.closest('.enemyBoard') == null);
            const enemyElements = animationsElements.filter((element) => element.closest('.enemyBoard') != null);
            playerElements.forEach(animateElement);

            // the viewing window scales with every loading element, player and
            // enemy alike, but stays readable: long enough for every enemy
            // animation to finish before the reload fires, never endless
            const perElementWindow = delay / 2;
            const playerWindow = playerElements.length * perElementWindow;
            const enemyWindow = enemyElements.length * perElementWindow;
            // the floating enemy turn marker gets a beat to land before the
            // enemy cards move
            const markerWindow = enemyElements.length > 0 ? delay / 3 : 0;
            const enemyStart = playerWindow + markerWindow;
            const enemyFinished = enemyElements.length > 0 ? enemyStart + moveDuration * 1000 : 0;
            const maxWindow = delay * 5;
            const reloadWindow = Math.max(Math.min(enemyStart + enemyWindow, maxWindow), enemyFinished);

            if (enemyElements.length > 0) {
                // mark the start of the enemy turn so the player can follow
                // what happened, then play the enemy animations
                setTimeout(() => {
                    enemyTurnMarker(reloadWindow - playerWindow - 300);
                }, playerWindow);
                setTimeout(() => {
                    enemyElements.forEach(animateElement);
                }, enemyStart);
            }

            setTimeout(() => {
                // console.log('Reloading window after animations');
                const path = window.location.pathname;
                // console.log('Current path:', path);
                let shortPath = path.substring(0, path.lastIndexOf('action'));
                if (!shortPath ) {
                    shortPath = path;
                }
                window.location.href = shortPath;
            }, reloadWindow);
        } else {
            console.log(`No elements found with '${classSelector}' class.`);
        }
    }
}

// floating text that marks the start of the enemy turn, shown before the
// enemy action animations so the player can follow what happened
function enemyTurnMarker(holdMs = 1200, text = 'Enemy turn') {
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

// //adds a duplicate card in the lane or hand, based on the source lane integer
function duplicateCard(element, lane, ordinal) 
{
    let laneElement  = null;
    const duplicate = element.cloneNode(true);
    duplicate.classList.add('duplicate');
    const enemyBoard = element.closest('.enemyBoard');
    if (enemyBoard) {
        // enemy cards animate from their source position inside their own board
        const enemyLaneNames = {1: 'Intelligence', 2: 'Speed', 3: 'Visciousness', 4: 'Resolve'};
        if (enemyLaneNames[lane]) {
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
