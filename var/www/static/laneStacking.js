/**
 * LaneCardStacking — Multi-row overflow for lane cards and holograms.
 * 
 * Measures available lane width on load/resize, calculates how many
 * overlapping cards fit per row, and splits excess cards into
 * additional rows below. Rows created by splitting carry the
 * `overflow-row` marker class so they can be collapsed and re-split
 * without ever touching other row groups (e.g. trustedCards).
 */
class LaneCardStacking {
    static OVERFLOW_ROW_CLASS = 'overflow-row';
    static MAX_CARDS_PER_ROW = 15;

    constructor() {
        this.debounceTimer = null;
        this.overlapOffset = 1.4; // em per card overlap (from CSS nth-child)
        this.init();
    }

    init() {
        this.reflowAll();
        window.addEventListener('resize', () => {
            clearTimeout(this.debounceTimer);
            this.debounceTimer = setTimeout(() => this.reflowAll(), 300);
        });
    }

    /**
     * Reflow all player lanes — recalculate row splitting.
     */
    reflowAll() {
        const lanes = document.querySelectorAll('.playerBoard .lane');
        lanes.forEach(lane => this.reflowLane(lane));
    }

    /**
     * Reflow a single lane: split cards/holograms into multiple rows.
     */
    reflowLane(lane) {
        // Process .cardRow elements (lane cards + trusted cards)
        const cardRows = lane.querySelectorAll(':scope > ul.cardRow');
        cardRows.forEach(row => this.reflowRowGroup(lane, row));

        // Process .hologramRow elements
        const holoRows = lane.querySelectorAll(':scope > ul.hologramRow');
        holoRows.forEach(row => this.reflowRowGroup(lane, row));
    }

    /**
     * Reflow a single row group — collapse previous overflow rows,
     * then split again if the children no longer fit the lane width.
     * @param {Element} lane - The lane container
     * @param {Element} row - The source row element (ul.cardRow or ul.hologramRow)
     */
    reflowRowGroup(lane, row) {
        if (!row.isConnected || !lane.isConnected) return;
        this.ensureSingleRow(row);

        const children = Array.from(row.children);
        if (children.length === 0) return;

        const laneWidth = lane.clientWidth;
        if (laneWidth <= 0) return;

        // Calculate how many cards fit per row.
        // The first card starts at left: 0, each subsequent card at overlapOffset em.
        const emSize = parseFloat(getComputedStyle(lane).fontSize) || 16;
        const overlapPx = this.overlapOffset * emSize;
        const firstCardWidth = children[0].offsetWidth || 100;

        // Total width used: overlapPx * (count - 1) + cardWidth
        const cardsPerRow = Math.min(
            LaneCardStacking.MAX_CARDS_PER_ROW,
            Math.max(1, Math.floor((laneWidth - firstCardWidth) / overlapPx) + 1)
        );
        row.dataset.cardsPerRow = String(cardsPerRow);

        if (children.length > cardsPerRow) {
            this.splitIntoRows(row, children, cardsPerRow);
        }
    }

    /**
     * Move children of every following overflow row (created by
     * splitting) back into this row and remove those rows. Only
     * marker-classed siblings of the same element type are consumed,
     * so the trustedCards row and other row groups stay separate.
     */
    ensureSingleRow(row) {
        if (!row.isConnected) return;
        let sibling = row.nextElementSibling;
        while (sibling) {
            const isOverflow = sibling.tagName === row.tagName
                && sibling.classList.contains(LaneCardStacking.OVERFLOW_ROW_CLASS);
            if (!isOverflow) break;
            const next = sibling.nextElementSibling;
            while (sibling.firstChild) {
                row.appendChild(sibling.firstChild);
            }
            sibling.remove();
            sibling = next;
        }
    }

    /**
     * Split children of a row into multiple rows.
     */
    splitIntoRows(sourceRow, children, cardsPerRow) {
        const parent = sourceRow.parentNode;
        if (!parent) return;

        const rows = [sourceRow];
        for (let i = cardsPerRow; i < children.length; i += cardsPerRow) {
            const newRow = document.createElement('ul');
            newRow.className = [sourceRow.className, LaneCardStacking.OVERFLOW_ROW_CLASS]
                .filter(Boolean)
                .join(' ');
            newRow.title = sourceRow.title;
            rows.push(newRow);
        }

        // Distribute children across rows
        children.forEach((child, index) => {
            const rowIndex = Math.min(Math.floor(index / cardsPerRow), rows.length - 1);
            rows[rowIndex].appendChild(child);
        });

        // Insert additional rows after the source row, before whatever follows it
        const refNode = sourceRow.nextElementSibling;
        for (let i = 1; i < rows.length; i++) {
            parent.insertBefore(rows[i], refNode);
        }
    }
}

// Initialize on DOMContentLoaded
document.addEventListener('DOMContentLoaded', () => {
    window.laneCardStacking = new LaneCardStacking();
});
