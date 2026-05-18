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

    /**
     * Initialize the drag and drop system
     */
    init() {
        this.createDropZones();
        this.setupCardDragListeners();
        this.setupDropZoneListeners();
    }

    /**
     * Create drop zones for each lane
     */
    createDropZones() {
        // Get all lanes from player board
        const allLanes = document.querySelectorAll('li.playerBoard ul.lanes li.lane');

        allLanes.forEach((lane, index) => {
            // Create a drop zone container for each lane
            const dropZone = document.createElement('div');
            dropZone.className = 'drop-zone';
            dropZone.id = `drop-zone-${index}`;

            // Insert drop zone at the end of each lane
            lane.appendChild(dropZone);

            // Store reference to drop zone, must be done or garbage collected
            this.dropZones.set(index, {
                element: dropZone
            });
        });

        console.log(`Created ${this.dropZones.size} drop zones`);
    }

    /**
     * Setup drag event listeners for all draggable cards
     */
    setupCardDragListeners() {
        const draggableCards = document.querySelectorAll('.card[draggable="true"]');

        draggableCards.forEach((card, index) => {
            card.addEventListener('dragstart', this.onCardDragStart.bind(this));
            card.addEventListener('dragend', this.onCardDragEnd.bind(this));
        });

        console.log(`Setup drag listeners for ${draggableCards.length} cards`);
    }

    /**
     * Setup event listeners for drop zones
     */
    setupDropZoneListeners() {
        this.dropZones.forEach((zoneData, index) => {
            const zone = zoneData.element;

            zone.addEventListener('dragover', this.onDropZoneDragOver.bind(this));
            zone.addEventListener('dragleave', this.onDropZoneDragLeave.bind(this));
            zone.addEventListener('drop', this.onDropZoneDrop.bind(this));
        });
    }

    /**
     * Handle card drag start
     */
    onCardDragStart(e) {
        this.draggedCard = e.currentTarget;
        this.draggedCard.classList.add('dragging');

        // Set drag image and data
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setDragImage(this.draggedCard, 0, 0);
        // e.dataTransfer.setData('text/html', this.draggedCard.innerHTML);

        console.log('Drag started:', this.draggedCard);

        // Highlight all drop zones
        this.highlightAllDropZones(true);
    }

    /**
     * Handle card drag end
     */
    onCardDragEnd(e) {
        this.draggedCard.classList.remove('dragging');

        // Remove drop zone highlights
        this.highlightAllDropZones(false);

        console.log('Drag ended');
    }

    /**
     * Handle drag over a drop zone
     */
    onDropZoneDragOver(e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';

        const zone = e.currentTarget;
        zone.classList.add('drop-zone-active');

        return false;
    }

    /**
     * Handle drag leave from a drop zone
     */
    onDropZoneDragLeave(e) {
        const zone = e.currentTarget;
        zone.classList.remove('drop-zone-active');
        return false;
    }

    /**
     * Handle drop on a drop zone
     */
    onDropZoneDrop(e) {
        e.preventDefault();
        e.stopPropagation();

        const zone = e.currentTarget;

        zone.classList.remove('drop-zone-active');

        if (this.draggedCard) {
            const cardTitle = this.draggedCard.textContent;
            console.log(`Card dropped: "${cardTitle}" in zone`, zone.id);

            // TODO use local storage and hologram of card and remove this ugly Visual feedback
            zone.textContent = `✓ Dropped: ${cardTitle}`;
            zone.classList.add('drop-zone-landed');
            
            // Reset the zone text after 2 seconds
            setTimeout(() => {
                zone.textContent = ``;
                zone.classList.remove('drop-zone-landed');
            }, 2000);

            // Here you can add logic to send the drop action to your server
            this.handleCardDrop(this.draggedCard, zone);
        }

        return false;
    }

    /**
     * Handle the card drop action (send to server or handle locally)
     */
    handleCardDrop(cardId, zone) {
        // Extract card information from the card element
        // const cardId = this.extractCardId(card);
        const lane = zone.dataset.lane;

        console.log(`Processing drop - Card ID: ${cardId}, Lane: ${lane}`);

        // You can emit a custom event for other parts of your application to handle
        const dropEvent = new CustomEvent('cardDropped', {
            detail: {
                cardId: cardId,
                // card: card,
                zone: zone,
                // laneIndex: laneIndex,
                // timestamp: new Date().toISOString()
            }
        });

        document.dispatchEvent(dropEvent);

        // Optional: send to server via AJAX
        //draw and end turn should sync with server. Other actions are handled locally and could be undone.
        // this.sendDropToServer(cardId, laneIndex);
    }

    // extractCardId(card) {
    //     const form = card.querySelector('form.cardActionForm');
    //     if (form) {
    //         const cardIdInput = form.querySelector('input[name="card_id"]');
    //         if (cardIdInput) {
    //             return cardIdInput.value;
    //         }
    //     }
    //     return 'unknown';
    // }

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

    /**
     * Refresh the drag and drop system (call after dynamic updates)
     */
    refresh() {
        // Clear existing listeners
        this.dropZones.clear();

        // Reinitialize
        this.init();
    }
}

// Initialize the system when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.cardDragDrop = new CardDragDropSystem();
    console.log('Card Drag and Drop System initialized');
});

// // Listen for custom cardDropped events (example usage)
// document.addEventListener('cardDropped', (e) => {
//     const { cardId, zone } = e.detail;
//     console.log(`Card ${cardId} was dropped on lane ${zone.id}`);
//     // Add your custom handling here


// });
