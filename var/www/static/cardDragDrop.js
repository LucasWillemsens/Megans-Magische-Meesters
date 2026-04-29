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
        // Get all lanes from both enemy and player boards
        const allLanes = document.querySelectorAll('.lane');

        allLanes.forEach((lane, index) => {
            // Create a drop zone container for each lane
            const dropZone = document.createElement('div');
            dropZone.className = 'drop-zone';
            dropZone.id = `drop-zone-${index}`;
            dropZone.dataset.laneIndex = index;
            dropZone.textContent = '📍 Drop card here';
            dropZone.style.cssText = `
                min-height: 40px;
                border: 2px dashed #999;
                border-radius: 8px;
                padding: 10px;
                text-align: center;
                background-color: #f5f5f5;
                cursor: pointer;
                transition: all 0.3s ease;
                font-size: 12px;
                color: #666;
                margin-top: 8px;
            `;

            // Insert drop zone at the end of each lane
            lane.appendChild(dropZone);

            // Store reference to drop zone
            this.dropZones.set(index, {
                element: dropZone,
                lane: lane,
                laneElement: lane
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
        this.draggedCard.style.opacity = '0.6';
        this.draggedCard.classList.add('dragging');

        // Set drag image and data
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/html', this.draggedCard.innerHTML);

        console.log('Drag started:', this.draggedCard);

        // Highlight all drop zones
        this.highlightAllDropZones(true);
    }

    /**
     * Handle card drag end
     */
    onCardDragEnd(e) {
        this.draggedCard.style.opacity = '1';
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
        zone.style.borderColor = '#4CAF50';
        zone.style.backgroundColor = '#e8f5e9';

        return false;
    }

    /**
     * Handle drag leave from a drop zone
     */
    onDropZoneDragLeave(e) {
        const zone = e.currentTarget;
        zone.classList.remove('drop-zone-active');
        zone.style.borderColor = '#999';
        zone.style.backgroundColor = '#f5f5f5';

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
        zone.style.borderColor = '#999';
        zone.style.backgroundColor = '#f5f5f5';

        if (this.draggedCard) {
            const cardTitle = this.draggedCard.textContent;
            console.log(`Card dropped: "${cardTitle}" in zone`, zone.id);

            // Visual feedback
            zone.textContent = `✓ Dropped: ${cardTitle}`;
            zone.style.backgroundColor = '#c8e6c9';
            zone.style.borderColor = '#4CAF50';

            // Reset the zone text after 2 seconds
            setTimeout(() => {
                zone.textContent = '📍 Drop card here';
                zone.style.backgroundColor = '#f5f5f5';
                zone.style.borderColor = '#999';
            }, 2000);

            // Here you can add logic to send the drop action to your server
            this.handleCardDrop(this.draggedCard, zone);
        }

        return false;
    }

    /**
     * Handle the card drop action (send to server or handle locally)
     */
    handleCardDrop(card, zone) {
        // Extract card information from the card element
        const cardId = this.extractCardId(card);
        const laneIndex = zone.dataset.laneIndex;

        console.log(`Processing drop - Card ID: ${cardId}, Lane: ${laneIndex}`);

        // You can emit a custom event for other parts of your application to handle
        const dropEvent = new CustomEvent('cardDropped', {
            detail: {
                cardId: cardId,
                card: card,
                zone: zone,
                laneIndex: laneIndex,
                timestamp: new Date().toISOString()
            }
        });

        document.dispatchEvent(dropEvent);

        // Optional: send to server via AJAX
        // this.sendDropToServer(cardId, laneIndex);
    }

    /**
     * Extract card ID from card element (adjust based on your HTML structure)
     */
    extractCardId(card) {
        // Try to find card ID from various possible sources
        const form = card.querySelector('form');
        if (form) {
            const cardIdInput = form.querySelector('input[name="card_id"]');
            if (cardIdInput) {
                return cardIdInput.value;
            }
        }

        // Fallback: use card's ID attribute or index
        return card.id || card.dataset.cardId || 'unknown';
    }

    /**
     * Highlight or remove highlight from all drop zones
     */
    highlightAllDropZones(highlight) {
        this.dropZones.forEach((zoneData) => {
            const zone = zoneData.element;
            if (highlight) {
                zone.style.borderColor = '#2196F3';
                zone.style.backgroundColor = '#e3f2fd';
            } else {
                zone.classList.remove('drop-zone-active');
                zone.style.borderColor = '#999';
                zone.style.backgroundColor = '#f5f5f5';
            }
        });
    }

    /**
     * Send drop action to server (optional)
     */
    sendDropToServer(cardId, laneIndex) {
        // Get CSRF token if available
        const csrfToken = document.querySelector('[name="csrfmiddlewaretoken"]');
        const token = csrfToken ? csrfToken.value : '';

        const data = {
            action: 'drop_card',
            card_id: cardId,
            lane: laneIndex
        };

        // Uncomment and adjust the fetch call based on your server endpoint
        /*
        fetch('/your-drop-endpoint/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': token
            },
            body: JSON.stringify(data)
        })
        .then(response => response.json())
        .then(data => {
            console.log('Drop processed:', data);
        })
        .catch(error => {
            console.error('Error sending drop:', error);
        });
        */
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

// Listen for custom cardDropped events (example usage)
document.addEventListener('cardDropped', (e) => {
    const { cardId, laneIndex } = e.detail;
    console.log(`Card ${cardId} was dropped on lane ${laneIndex}`);
    // Add your custom handling here
});
