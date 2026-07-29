/**
 * Card Drag and Drop System
 * Handles dragging cards to drop zones in each lane
 */
class CardDragDropSystem {
    constructor() {
        this.draggedCard = null;
        this.dropZones = new Map();
        this.turnAllowances = { int: 0, spd: 0, tactics: 0, drawn: 0, played: 0, flipped: 0 };
        this.staged = { plays: 0, flips: 0 };
        this.tooltips = { draw: "", play: "", flip: "" };
        this.init();
    }

    init() {
        const limitsEl = document.getElementById('turnLimits');
        if (limitsEl) {
            const d = limitsEl.dataset;
            this.turnAllowances = {
                int: parseInt(d.intCount),
                spd: parseInt(d.spdCount),
                tactics: parseInt(d.tactics),
                drawn: parseInt(d.drawn),
                played: parseInt(d.played),
                flipped: parseInt(d.flipped),
            };
            this.tooltips = {
                draw: d.drawBlockedTitle,
                play: d.playBlockedTitle,
                flip: d.flipBlockedTitle,
            };
        }
        this.createDropZones();
        this.setupCardDragListeners();
        this.setupDropZoneListeners();
        this.setupFaceDownCardClickListeners();
        this.applyTurnAffordances();
    }

    remainingAllowances() {
        const { int, spd, tactics, drawn, played, flipped } = this.turnAllowances;
        const { plays: stagedPlays, flips: stagedFlips } = this.staged;
        const effectivePlayed = played + stagedPlays;
        const effectiveFlipped = flipped + stagedFlips;
        return {
            draws: Math.max(0, int + 1 + Math.min(0, spd + 1 - effectiveFlipped - effectivePlayed) - drawn),
            flips: Math.max(0, spd + 1 + Math.min(0, int + 1 - drawn - effectivePlayed) - effectiveFlipped),
            plays: Math.max(0, 2 + tactics - drawn - effectiveFlipped - effectivePlayed),
        };
    }

    applyTurnAffordances() {
        const remaining = this.remainingAllowances();

        if (remaining.plays <= 0) {
            document.querySelectorAll('ul.hand li.cardContainer:not(.blocked)').forEach(card => {
                card.classList.add('blocked');
                card.setAttribute('draggable', 'false');
                card.title = this.tooltips.play;
            });
        }

        if (remaining.flips <= 0) {
            document.querySelectorAll(
                '.playerBoard .cardContainer.faceDown:not(.blocked), ' +
                '.hologram .cardContainer.faceDown:not(.blocked)'
            ).forEach(card => {
                card.classList.add('blocked');
                card.title = this.tooltips.flip;
            });
        }

        if (remaining.draws <= 0) {
            const deck = document.querySelector('.deckHand > ul.deck');
            if (deck) deck.classList.add('blocked');
            const drawBtn = document.querySelector('.deckHand button.draw');
            if (drawBtn) {
                drawBtn.disabled = true;
                drawBtn.title = this.tooltips.draw;
            }
        }
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
            .querySelectorAll(':not(.hologram) .cardContainer.faceDown:not(.blocked)')
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
        if (this.remainingAllowances().plays <= 0) {
            e.preventDefault();
            return;
        }
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
            const laneElement = zone.closest('li.lane');
            const holoRow = laneElement.querySelector('.hologramRow');
            const laneValue = parseInt(zone.id.split('-')[2]);

            const hologram = document.createElement('div');
            const copycard = this.draggedCard.cloneNode(true);
            copycard.classList.remove('dragging');
            copycard.classList.add('faceDown');
            copycard.removeAttribute('draggable');
            copycard.children[0].classList.add('back');
            const button = copycard.querySelector('button');
            if (button) button.setAttribute('inert', 'true');

            hologram.appendChild(copycard);
            hologram.querySelector('.cardContainer.faceDown').addEventListener('click', (e) => this.onFaceDownCardClick(e, laneValue), {once : true});
            hologram.classList.add('hologram');
            holoRow.appendChild(hologram);

            const sourceLane = this.draggedCard.dataset.sourceLane ?? '0';
            const sourceOrdinal = this.draggedCard.dataset.sourceOrdinal ?? '0';
            this.createupdateCookie(
                this.draggedCard.querySelectorAll('input[name="card_id"]')[0].value,
                laneValue,
                false,
                sourceLane,
                sourceOrdinal,
            );

            // Keep hand card as ghost instead of removing it
            this.draggedCard.classList.add('ghost');
            this.draggedCard.setAttribute('draggable', 'false');

            // Hover arrow between ghost and hologram
            this._addHoverArrow(this.draggedCard, hologram);

            this.staged.plays++;
            this.applyTurnAffordances();
        }
        return false;
    }

    _addHoverArrow(sourceEl, targetEl) {
        let arrow = null;
        let hideTimeout = null;

        const showArrow = () => {
            if (hideTimeout) {
                clearTimeout(hideTimeout);
                hideTimeout = null;
            }
            if (!arrow || !arrow.parentNode) {
                arrow = this._createCurvedArrow(sourceEl, targetEl);
                document.body.appendChild(arrow);
            }
            sourceEl.classList.add('hover');
            targetEl.classList.add('hover');
        };

        const hideArrow = () => {
            if (hideTimeout) return;
            hideTimeout = setTimeout(() => {
                if (arrow && arrow.parentNode) {
                    arrow.remove();
                }
                arrow = null;
                sourceEl.classList.remove('hover');
                targetEl.classList.remove('hover');
                hideTimeout = null;
            }, 100);
        };

        sourceEl.addEventListener('mouseenter', showArrow);
        sourceEl.addEventListener('mouseleave', hideArrow);
        targetEl.addEventListener('mouseenter', showArrow);
        targetEl.addEventListener('mouseleave', hideArrow);
    }

    _createCurvedArrow(sourceEl, targetEl) {
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.classList.add('hologram-arrow');
        svg.style.position = 'fixed';
        svg.style.pointerEvents = 'none';
        svg.style.zIndex = '1000';
        svg.style.overflow = 'visible';
        svg.style.top = '0'; //adjust
        svg.style.left = '0';//adjust
        svg.style.width = '100%';
        svg.style.height = '100%';

        const sourceRect = sourceEl.getBoundingClientRect();
        const targetRect = targetEl.getBoundingClientRect();

        const x1 = sourceRect.left + sourceRect.width / 2;
        const y1 = sourceRect.top + sourceRect.height / 2;
        const x2 = targetRect.left + targetRect.width / 2; // Adjust
        const y2 = targetRect.top + targetRect.height / 2; // Adjust

        const dx = x2 - x1;
        const dy = y2 - y1;
        const cx1 = x1 + dx * 0.25;
        const cy1 = y1 + dy * 0.1 - Math.abs(dx) * 0.3;
        const cx2 = x1 + dx * 0.75;
        const cy2 = y1 + dy * 0.9 - Math.abs(dx) * 0.3;

        const d = `M ${x1} ${y1} C ${cx1} ${cy1}, ${cx2} ${cy2}, ${x2} ${y2}`;

        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', d);
        path.setAttribute('stroke', '#ffcc00');
        path.setAttribute('stroke-width', '3');
        path.setAttribute('fill', 'none');
        path.setAttribute('stroke-dasharray', '6,4');

        svg.appendChild(path);

        // Arrowhead
        const angle = Math.atan2(dy, dx);
        const arrowSize = 20;
        const ax = x2 - arrowSize * 0.5 * Math.cos(angle);
        const ay = y2 - arrowSize * 0.5 * Math.sin(angle);

        const marker = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
        marker.setAttribute('points',
            `${ax},${ay} ${ax - arrowSize * Math.cos(angle - 0.4)},${ay - arrowSize * Math.sin(angle - 0.4)} ${ax - arrowSize * Math.cos(angle + 0.4)},${ay - arrowSize * Math.sin(angle + 0.4)}`
        );
        marker.setAttribute('fill', '#ffcc00');
        svg.appendChild(marker);

        return svg;
    }

    onFaceDownCardClick(e, laneValue) {
        if (this.remainingAllowances().flips <= 0) return;
        const card = e.currentTarget ?? e.target.closest('.cardContainer');
        const cardId = card.querySelectorAll('input[name="card_id"]')[0].value;
        const sourceLane = card.dataset.sourceLane ?? '0';
        const sourceOrdinal = card.dataset.sourceOrdinal ?? '0';
        this.createupdateCookie(`${cardId}`, `${laneValue}`, true, sourceLane, sourceOrdinal);
        card.classList.remove('faceDown');
        // Properly find the card div — for lane cards children[0] is <input>, not the card div
        const cardDiv = card.querySelector(':scope > .card');
        if (cardDiv) cardDiv.classList.remove('back');

        // If this is a lane card (not a hologram), add ghost and create flip hologram
        if (!card.closest('.hologram')) {
            const laneElement = card.closest('li.lane');
            const holoRow = laneElement.querySelector('.hologramRow');

            // Make the flipped lane card ghostly
            card.classList.add('ghost');

            // Create face-up hologram clone
            const flipHologram = document.createElement('div');
            const holoClone = card.cloneNode(true);
            holoClone.classList.remove('ghost');
            holoClone.classList.add('faceUp');
            // Remove form/button from the clone (display only)
            const form = holoClone.querySelector('form');
            if (form) form.remove();
            const buttons = holoClone.querySelectorAll('button');
            buttons.forEach(btn => btn.remove());

            // Ensure the clone's card div does NOT have the 'back' class
            const cloneCardDiv = holoClone.querySelector(':scope > .card');
            if (cloneCardDiv) cloneCardDiv.classList.remove('back');

            flipHologram.classList.add('hologram');
            flipHologram.appendChild(holoClone);
            holoRow.appendChild(flipHologram);

            // One-shot click-to-flip on the hologram (same pattern as play hologram)
            const holoCard = flipHologram.querySelector('.cardContainer');
            if (holoCard) {
                holoCard.addEventListener('click', (ev) => this.onFaceDownCardClick(ev, laneValue), { once: true });
            }

            // Hover arrow between lane card and hologram
            this._addHoverArrow(card, flipHologram);
        }

        this.staged.flips++;
        this.applyTurnAffordances();
    }

    createupdateCookie(cardId, laneValue, flipFaceUp=false, sourceLane=null, sourceOrdinal=null) {
        const path = window.location.pathname;
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
});
