/**
 * Card Drag and Drop System
 * Handles dragging cards to drop zones in each lane
 */
class CardDragDropSystem {
    constructor() {
        this.draggedCard = null;
        this.dropZones = new Map();
        this.init();
    }

    init() {
        this.createDropZones();
        this.setupCardDragListeners();
        this.setupDropZoneListeners();
        this.setupFaceDownCardClickListeners();
    }

    createDropZones() {
        const allLanes = document.querySelectorAll('li.playerBoard ul.lanes li.lane');
        allLanes.forEach((lane, index) => {
            const dropZone = document.createElement('div');
            dropZone.className = 'drop-zone';
            dropZone.id = `drop-zone-${index+1}`;
            lane.appendChild(dropZone);
            this.dropZones.set(index+1, {
                element: dropZone
            });
        });
    }

    setupCardDragListeners() {
        // the enemy deck/hand (.enemyDeckHand) is display-only: never bind
        // drag behaviour to its card containers
        const draggableCards = Array.from(
            document.querySelectorAll('.cardContainer[draggable="true"]')
        ).filter((card) => card.closest('.enemyDeckHand') == null);
        draggableCards.forEach((card, index) => {
            card.addEventListener('dragstart', this.onCardDragStart.bind(this));
            card.addEventListener('dragend', this.onCardDragEnd.bind(this));
        });
    }

    setupFaceDownCardClickListeners() {
        const faceDownCards = Array.from(
            document.querySelector('.playerBoard')
            .querySelectorAll(':not(.hologram) .cardContainer.faceDown')
            // the enemy deck/hand (.enemyDeckHand) is display-only: its
            // face-down cards never get click handlers
        ).filter((card) => card.closest('.enemyDeckHand') == null);

        faceDownCards.forEach((card, index) => {
            let laneValue = null;
            const laneElementClass = card.closest('li.lane').classList[1];
            if (laneElementClass === 'Intelligence') {
                laneValue = 1;
            }else if (laneElementClass === 'Speed') {
                laneValue = 2;
            } else if (laneElementClass === 'Visciousness') {
                laneValue = 3;
            } else if (laneElementClass === 'Resolve') {
                laneValue = 4;
            } else {
                console.warn('Unknown lane type for face-down card:', laneElementClass);
            }
            card.addEventListener('click', (e) => this.onFaceDownCardClick(e, laneValue), {once : true});
        });

        // console.log(`Setup click listeners for ${faceDownCards.length} cards`);
    }

    setupDropZoneListeners() {
        this.dropZones.forEach((zoneData, index) => {
            const zone = zoneData.element;

            zone.addEventListener('dragover', this.onDropZoneDragOver.bind(this));
            zone.addEventListener('dragleave', this.onDropZoneDragLeave.bind(this));
            zone.addEventListener('drop', this.onDropZoneDrop.bind(this));
        });
    }

    onCardDragStart(e) {
        this.draggedCard = e.currentTarget;
        this.draggedCard.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setDragImage(this.draggedCard,180, 150);
        this.highlightAllDropZones(true);
    }

    onCardDragEnd(e) {
        this.draggedCard.classList.remove('dragging');
        this.highlightAllDropZones(false);
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

    onDropZoneDrop(e) {
        e.preventDefault();
        e.stopPropagation();
        const zone = e.currentTarget;
        zone.classList.remove('drop-zone-active');

        if (this.draggedCard) {
            const cardTitle = this.draggedCard.textContent;
            const hologram = document.createElement('div');
            
            const copycard = this.draggedCard.cloneNode(true);
            copycard.classList.remove('dragging');
            copycard.classList.add('faceDown');
            copycard.removeAttribute('draggable');
            copycard.children[0].classList.add('back');
            const button = copycard.querySelector('button');
            button.setAttribute('inert', 'true');
            
            hologram.appendChild(copycard);
            hologram.querySelector('.cardContainer.faceDown').addEventListener('click', (e) => this.onFaceDownCardClick(e, zone.id.split('-')[2]), {once : true});
            hologram.classList.add('hologram');
            zone.appendChild(hologram);

            const sourceLane = this.draggedCard.dataset.sourceLane ?? '0';
            const sourceOrdinal = this.draggedCard.dataset.sourceOrdinal ?? '0';
            this.createupdateCookie(
                this.draggedCard.querySelectorAll('input[name="card_id"]')[0].value,
                zone.id.split('-')[2],
                false,
                sourceLane,
                sourceOrdinal,
            );
            this.draggedCard.remove();
        }
        return false;
    }

    onFaceDownCardClick(e, laneValue) {
        const card = e.currentTarget ?? e.target.closest('.cardContainer');
        const cardId = card.querySelectorAll('input[name="card_id"]')[0].value;
        const sourceLane = card.dataset.sourceLane ?? '0';
        const sourceOrdinal = card.dataset.sourceOrdinal ?? '0';
        // console.log('Face-down card clicked:', card, `cardId: ${cardId}, laneValue: ${laneValue}`);
        this.createupdateCookie(`${cardId}`, `${laneValue}`, true, sourceLane, sourceOrdinal);
        card.classList.remove('faceDown');
        card.children[0].classList.remove('back');
    }

    createupdateCookie(cardId, laneValue, flipFaceUp=false, sourceLane=null, sourceOrdinal=null) {
        const path = window.location.pathname;
        // console.log('Current path:', path);
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
        this.dropZones.clear();
        this.init();
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.cardDragDrop = new CardDragDropSystem();
    // console.log('Card Drag and Drop System initialized');
});
