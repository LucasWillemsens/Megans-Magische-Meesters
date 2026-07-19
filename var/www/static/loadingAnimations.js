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
            for (let i = 0; i < animationsElements.length; i++) {
                const element = animationsElements[i];
                element.classList.add('animating');
                // console.log(`animating element ${i + 1}:`, element);
                const lane  = element.getAttribute('data-source-lane');
                const ordinal = element.getAttribute('data-source-ordinal');
                if (lane != null && ordinal != null && lane != "" && ordinal != ""){
                    const duplicate = duplicateCard(element, parseInt(lane), parseInt(ordinal));
                    if (duplicate) {
                        const moveDuration = Math.max(0.2, Math.min(1.2, delay / 1000));
                        duplicate.style.setProperty('--move-duration', `${moveDuration}s`);
                        // duplicate.style.setProperty('--move-delay', `${moveDuration*i}s`);//TODO?
                        requestAnimationFrame(() => {
                            if (lane == 0){    
                                duplicate.classList.add('to-original');
                            }
                        });
                    }
                    element.setAttribute("hidden","true");
                }
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
            }, (animationsElements.length)*delay/2);
        } else {
            console.log(`No elements found with '${classSelector}' class.`);
        }
    }
}

// //adds a duplicate card in the lane or hand, based on the source lane integer
function duplicateCard(element, lane, ordinal) 
{
    let laneElement  = null;
    const duplicate = element.cloneNode(true);
    duplicate.classList.add('duplicate');
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
