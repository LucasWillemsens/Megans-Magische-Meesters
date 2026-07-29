/**
 * LaneCardStacking — Multi-row overflow for lane cards and holograms.
 * 
 * Measures available lane width on load/resize, calculates how many
 * overlapping cards fit per row, and splits excess cards into
 * additional rows below.
 */
class LaneCardStacking {
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
     * Reflow a single row group — split if children exceed lane width.
     * @param {Element} lane - The lane container
     * @param {Element} row - The row element (ul.cardRow or ul.hologramRow)
     */
    reflowRowGroup(lane, row) {
        const children = Array.from(row.children);
        if (children.length === 0) return;

        const laneWidth = lane.clientWidth;
        if (laneWidth <= 0) return;

        // Calculate how many cards fit per row
        // The first card starts at left: 0, each subsequent card at overlapOffset em
        // We need to convert em to px for calculation
        const emSize = parseFloat(getComputedStyle(lane).fontSize) || 16;
        const overlapPx = this.overlapOffset * emSize;
        const firstCardWidth = children[0].offsetWidth || 100;

        // Cards per row: 1 (for the first card) + floor((laneWidth - firstCardWidth) / overlapPx)
        // But since cards overlap, the total width used is: overlapPx * (count - 1) + cardWidth
        const cardsPerRow = Math.max(1,
            Math.floor((laneWidth - firstCardWidth) / overlapPx) + 1
        );

        if (children.length <= cardsPerRow) {
            // All fit in one row — reset to single row if needed
            this.ensureSingleRow(row);
            return;
        }

        // Split into multiple rows
        this.splitIntoRows(row, children, cardsPerRow);
    }

    /**
     * Ensure a row group is a single row (collapse any extra rows).
     */
    ensureSingleRow(row) {
        // If there are extra sibling rows of the same type, move children back
        const rowType = row.tagName === 'UL' ? row.className : '';
        let sibling = row.nextElementSibling;
        while (sibling && sibling.matches?.('ul.' + row.className.split(' ').join('.'))) {
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
    splitIntoRows(originalRow, children, cardsPerRow) {
        const rows = [];

        // Create first row with first cardsPerRow children
        const firstRow = originalRow;
        firstRow.innerHTML = '';
        rows.push(firstRow);

        // Create additional rows for overflow
        for (let i = cardsPerRow; i < children.length; i += cardsPerRow) {
            const newRow = document.createElement('ul');
            newRow.className = firstRow.className;
            newRow.title = firstRow.title;
            rows.push(newRow);
        }

        // Distribute children across rows
        children.forEach((child, index) => {
            const rowIndex = Math.min(Math.floor(index / cardsPerRow), rows.length - 1);
            rows[rowIndex].appendChild(child);
        });

        // Insert additional rows after the first
        let refNode = firstRow.nextElementSibling;
        for (let i = 1; i < rows.length; i++) {
            if (refNode === rows[i]) {
                refNode = refNode.nextElementSibling;
                continue;
            }
            firstRow.parentNode.insertBefore(rows[i], refNode);
            if (refNode) {
                // refNode stays the same — the new row was inserted before it
            } else {
                refNode = rows[i].nextElementSibling;
            }
        }

        // Remove any remaining old extra rows
        this.ensureSingleRow(firstRow);
    }
}

// Initialize on DOMContentLoaded
document.addEventListener('DOMContentLoaded', () => {
    window.laneCardStacking = new LaneCardStacking();
});
