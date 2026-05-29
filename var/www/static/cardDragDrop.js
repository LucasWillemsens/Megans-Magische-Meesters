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
        const draggableCards = document.querySelectorAll('.cardContainer[draggable="true"]');
        draggableCards.forEach((card, index) => {
            card.addEventListener('dragstart', this.onCardDragStart.bind(this));
            card.addEventListener('dragend', this.onCardDragEnd.bind(this));
        });
    }

    //TODO
    setupFaceDownCardClickListeners() {
        const facedownCards = document.querySelector('.playerBoard')
        .querySelectorAll(':not(.hologram) .cardContainer.facedown');

        facedownCards.forEach((card, index) => {
            //todo grab lane value from card location
            card.addEventListener('click', (e) => this.onFaceDownCardClick(e, card.dataset.laneValue), {once : true});
        });

        console.log(`Setup click listeners for ${facedownCards.length} cards`);
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
            copycard.classList.add('facedown');
            copycard.removeAttribute('draggable');
            copycard.children[0].classList.add('back');
            const button = copycard.querySelector('button');
            button.setAttribute('inert', 'true');
            
            hologram.appendChild(copycard);
            hologram.querySelector('.cardContainer.facedown').addEventListener('click', (e) => this.onFaceDownCardClick(e, zone.id.split('-')[2]), {once : true});
            hologram.classList.add('hologram');
            zone.appendChild(hologram);

            this.createupdateCookie(this.draggedCard.querySelectorAll('input[name="card_id"]')[0].value, zone.id.split('-')[2]);
            this.draggedCard.remove();
        }
        return false;
    }

    onFaceDownCardClick(e, laneValue) {
        const card = e.target;
        console.log('Face-down card clicked:',card);
        const cardId = card.querySelectorAll('input[name="card_id"]')[0].value;
        this.createupdateCookie(`${cardId}`, `${laneValue}`, true);
        card.classList.remove('facedown');
        card.children[0].classList.remove('back');
    }

    createupdateCookie(cardId, laneValue,flipFaceUp=false) {
        if (flipFaceUp) {
            document.cookie=`${cardId}=${laneValue}f`;
        } else {
            document.cookie=`${cardId}=${laneValue}`;
        }
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
